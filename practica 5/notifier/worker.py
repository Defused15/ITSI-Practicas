import json
import os
import time

import pika
import requests

QUEUE_NAME = "task_completed"
WEBHOOK_URL = os.environ["WEBHOOK_URL"]


def connect_to_rabbitmq():
    rabbitmq_url = os.environ["RABBITMQ_URL"]
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.URLParameters(rabbitmq_url)
            )
            print("Notifier: conectado a RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print("Notifier: RabbitMQ todavía no está disponible; reintento en 5 s.")
            time.sleep(5)


def send_email(task_data):
    """Simula el envío de un email haciendo un POST a webhook.site."""
    email = {
        "to": "usuario@example.com",
        "subject": f"Tarea completada: {task_data['title']}",
        "body": (
            f"La tarea con ID={task_data.get('id')} "
            f"('{task_data['title']}') se ha marcado como completada."
        ),
        "task": task_data,
    }
    response = requests.post(WEBHOOK_URL, json=email, timeout=10)
    response.raise_for_status()
    return response.status_code


def callback(channel, method, properties, body):
    try:
        task_data = json.loads(body)
        if not isinstance(task_data, dict) or not task_data.get("title"):
            raise ValueError("el mensaje no contiene un title válido")
    except (json.JSONDecodeError, ValueError) as error:
        print(f"Notifier: mensaje inválido; se rechaza: {error}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    try:
        status = send_email(task_data)
    except requests.RequestException as error:
        # Fallo transitorio (red, webhook caído...): se devuelve el mensaje
        # a la cola para reintentarlo más tarde.
        print(f"Notifier: no se pudo enviar el email ({error}); reintento en 5 s.")
        time.sleep(5)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return

    print(
        f"Notifier: email simulado enviado (HTTP {status}) para la tarea "
        f"ID={task_data.get('id')}, Título='{task_data['title']}'"
    )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def main():
    connection = connect_to_rabbitmq()
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

        print(f"Notifier: esperando mensajes en '{QUEUE_NAME}'.")
        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Notifier: interrumpido.")
