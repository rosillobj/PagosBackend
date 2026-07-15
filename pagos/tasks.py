import subprocess
import requests

from celery import shared_task
from django.utils import timezone

from .models import tokenExpo


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def enviar_notificacion_expo(title, body, data=None):
    tokens = list(
        tokenExpo.objects.exclude(token="")
        .values_list("token", flat=True)
    )

    if not tokens:
        print("[PUSH] No hay tokens Expo registrados")
        return {
            "ok": False,
            "message": "No hay tokens Expo registrados",
        }

    mensajes = []

    for token in tokens:
        mensajes.append(
            {
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {},
            }
        )

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=mensajes,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

        response.raise_for_status()

        print(
            "[PUSH] Notificaciones enviadas:",
            response.json(),
        )

        return {
            "ok": True,
            "response": response.json(),
        }

    except requests.RequestException as e:
        print(
            f"[PUSH ERROR] Error enviando notificación: {e}"
        )

        return {
            "ok": False,
            "message": str(e),
        }


@shared_task
def ping_antena_192_168_1_117():
    ip = "192.168.1.253"
    
    try:
        result = subprocess.run(
            [
                "ping",
                "-c",
                "5",
                "-W",
                "2",
                ip,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            print(
                f"[OK] Antena {ip} respondió al menos 1 ping"
            )

            return {
                "ok": True,
                "ip": ip,
                "status": "online",
                "checked_at": timezone.now().isoformat(),
            }

        print(
            f"[ALERTA] Antena {ip} no respondió ninguno de los 5 pings"
        )

        push_result = enviar_notificacion_expo(
            title="⚠️ Antena sin conexión",
            body=f"La antena {ip} no respondió a los 5 pings.",
            data={
                "type": "antena_offline",
                "ip": ip,
            },
        )

        return {
            "ok": False,
            "ip": ip,
            "status": "offline",
            "message": "No respondió ninguno de los 5 pings",
            "notification": push_result,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "checked_at": timezone.now().isoformat(),
        }

    except Exception as e:
        print(
            f"[ERROR] Error haciendo ping a {ip}: {e}"
        )

        enviar_notificacion_expo(
            title="❌ Error monitoreando antena",
            body=f"Error al comprobar la antena {ip}.",
            data={
                "type": "antena_error",
                "ip": ip,
                "error": str(e),
            },
        )

        return {
            "ok": False,
            "ip": ip,
            "status": "error",
            "message": str(e),
            "checked_at": timezone.now().isoformat(),
        }
    
@shared_task
def autoReboot121():
    ip = "192.168.1.253"
    ip2 = "192.168.1.84"
    ip3 = "192.168.1.98"
    ip4 = "192.168.1.213"
    
    try:
        result = subprocess.run(
            [
                "ping",
                "-c",
                "5",
                "-W",
                "2",
                ip,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            print(
                f"[OK] Antena {ip} respondió al menos 1 ping"
            )

            return {
                "ok": True,
                "ip": ip,
                "status": "online",
                "checked_at": timezone.now().isoformat(),
            }

        print(
            f"[ALERTA] Antena {ip} no respondió ninguno de los 5 pings"
        )

        push_result = enviar_notificacion_expo(
            title="⚠️ Antena sin conexión",
            body=f"La antena {ip} no respondió a los 5 pings.",
            data={
                "type": "antena_offline",
                "ip": ip,
            },
        )

        return {
            "ok": False,
            "ip": ip,
            "status": "offline",
            "message": "No respondió ninguno de los 5 pings",
            "notification": push_result,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "checked_at": timezone.now().isoformat(),
        }

    except Exception as e:
        print(
            f"[ERROR] Error haciendo ping a {ip}: {e}"
        )

        enviar_notificacion_expo(
            title="❌ Error monitoreando antena",
            body=f"Error al comprobar la antena {ip}.",
            data={
                "type": "antena_error",
                "ip": ip,
                "error": str(e),
            },
        )

        return {
            "ok": False,
            "ip": ip,
            "status": "error",
            "message": str(e),
            "checked_at": timezone.now().isoformat(),
        }