import json
import os
import time

import pika
import psycopg2
from psycopg2.extras import Json

DLX_EXCHANGE = "tasks_dlx"
FAILED_QUEUE = "tasks_failed"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS task_error (
    id SERIAL PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    original_queue VARCHAR(120),
    reason VARCHAR(60),
    payload TEXT NOT NULL,
    payload_json JSONB
)
"""


def connect_to_database():
    while True:
        try:
            connection = psycopg2.connect(os.environ["DATABASE_URL"])
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(CREATE_TABLE)
            print("Error handler: conectado a PostgreSQL.")
            return connection
        except psycopg2.OperationalError:
            print("Error handler: PostgreSQL todavía no está disponible; reintento en 5 s.")
            time.sleep(5)


def connect_to_rabbitmq():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.URLParameters(os.environ["RABBITMQ_URL"])
            )
            print("Error handler: conectado a RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print("Error handler: RabbitMQ todavía no está disponible; reintento en 5 s.")
            time.sleep(5)


def death_info(properties):
    """Cola de origen y motivo del rechazo, según la cabecera x-death."""
    deaths = (properties.headers or {}).get("x-death") or []
    if not deaths:
        return None, None
    first = deaths[0]
    return first.get("queue"), first.get("reason")


def make_callback(db):
    def callback(channel, method, properties, body):
        payload = body.decode("utf-8", errors="replace")
        try:
            payload_json = json.loads(payload)
        except json.JSONDecodeError:
            payload_json = None
        queue, reason = death_info(properties)

        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO task_error (original_queue, reason, payload, payload_json) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (queue, reason, payload,
                 Json(payload_json) if payload_json is not None else None),
            )
            error_id = cursor.fetchone()[0]

        print(
            f"Error handler: mensaje fallido registrado (fila {error_id}): "
            f"cola={queue}, motivo={reason}, contenido={payload}"
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)

    return callback


def main():
    db = connect_to_database()
    connection = connect_to_rabbitmq()
    try:
        channel = connection.channel()
        channel.exchange_declare(
            exchange=DLX_EXCHANGE, exchange_type="direct", durable=True
        )
        channel.queue_declare(queue=FAILED_QUEUE, durable=True)
        channel.queue_bind(
            queue=FAILED_QUEUE, exchange=DLX_EXCHANGE, routing_key=FAILED_QUEUE
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=FAILED_QUEUE, on_message_callback=make_callback(db))

        print(f"Error handler: esperando mensajes en '{FAILED_QUEUE}'.")
        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Error handler: interrumpido.")
