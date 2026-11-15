import json
import os
import time

import pika


DLX_EXCHANGE = "tasks_dlx"
FAILED_QUEUE = "tasks_failed"
# Mismos argumentos que en web/app.py.
TASK_CREATED_ARGUMENTS = {
    "x-dead-letter-exchange": DLX_EXCHANGE,
    "x-dead-letter-routing-key": FAILED_QUEUE,
}


def connect_to_rabbitmq():
    rabbitmq_url = os.environ["RABBITMQ_URL"]
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.URLParameters(rabbitmq_url)
            )
            print("Worker: conectado a RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print("Worker: RabbitMQ todavía no está disponible; reintento en 5 s.")
            time.sleep(5)


def callback(channel, method, properties, body):
    try:
        task_data = json.loads(body)
        if not isinstance(task_data, dict) or not task_data.get("title"):
            raise ValueError("el mensaje no contiene un title válido")
    except (json.JSONDecodeError, ValueError) as error:
        print(f"Worker: mensaje inválido; se rechaza: {error}")
        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )
        return

    print(
        " [x] Tarea recibida: "
        f"ID={task_data.get('id')}, Título='{task_data['title']}'"
    )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def main():
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
        channel.queue_declare(
            queue="task_created",
            durable=True,
            arguments=TASK_CREATED_ARGUMENTS,
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue="task_created",
            on_message_callback=callback,
        )

        print(" [*] Esperando mensajes. Para salir presione CTRL+C")
        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Worker: interrumpido.")
