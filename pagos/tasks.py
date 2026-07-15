import subprocess
import requests
from .views import login_airos_session,_is_login_html,_parse_reboot_form,urljoin
from celery import shared_task
from django.utils import timezone
import subprocess
from .models import tokenExpo


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def reboot_via_https_confirm(
    ip: str,
    user: str,
    password: str,
) -> dict:

    base = f"https://{ip}"

    try:
        s = login_airos_session(
            ip,
            user,
            password,
        )

        # Abrir reboot.cgi
        r1 = s.get(
            f"{base}/reboot.cgi",
            timeout=(3, 6),
            verify=False,
        )

        if r1.status_code != 200:
            return {
                "ok": False,
                "stage": "open_reboot",
                "status_code": r1.status_code,
            }

        html = r1.text or ""

        if _is_login_html(html):
            return {
                "ok": False,
                "stage": "auth_lost",
            }

        action, hidden = _parse_reboot_form(html)

        post_url = urljoin(
            f"{base}/",
            action,
        )

        payload = dict(hidden)

        payload.setdefault("reboot", "1")
        payload.setdefault("action", "reboot")
        payload.setdefault("do_reboot", "1")
        payload.setdefault("confirm", "1")

        # Confirmar reboot
        r2 = s.post(
            post_url,
            data=payload,
            timeout=(3, 6),
            verify=False,
        )

        if r2.status_code in (200, 302, 204):
            return {
                "ok": True,
                "stage": "reboot_sent",
                "status_code": r2.status_code,
            }

        return {
            "ok": False,
            "stage": "unexpected_status",
            "status_code": r2.status_code,
        }

    except Exception as e:
        return {
            "ok": False,
            "stage": "error",
            "message": str(e),
        }
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
    



def comprobar_ping(ip: str) -> dict:
    """
    Hace 5 pings a una IP.
    Se considera ONLINE si responde al menos uno.
    """

    try:
        result = subprocess.run(
            [
                "ping",
                "-c", "5",
                "-W", "2",
                ip,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )

        online = result.returncode == 0

        return {
            "ip": ip,
            "online": online,
            "status": "online" if online else "offline",
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except Exception as e:
        return {
            "ip": ip,
            "online": False,
            "status": "error",
            "error": str(e),
        }


@shared_task
def autoReboot121():

    # Antenas que vamos a comprobar
    antenas = [
        "192.168.1.253",
        "192.168.1.84",
        "192.168.1.98",
        "192.168.1.213",
    ]

    # Antena principal del sector que se reiniciará
    ip_reboot = "192.168.1.121"

    usuario = "ubnt"
    password = "ubnt2"

    resultados = []

    # Comprobar las 4 antenas
    for ip in antenas:

        resultado = comprobar_ping(ip)
        resultados.append(resultado)

        if resultado["online"]:
            print(f"[OK] Antena {ip} respondió ping")
        else:
            print(
                f"[ALERTA] Antena {ip} no respondió "
                f"a ninguno de los 5 pings"
            )

    # Obtener antenas offline
    antenas_offline = [
        resultado["ip"]
        for resultado in resultados
        if not resultado["online"]
    ]

    cantidad_offline = len(antenas_offline)

    print(
        f"[SECTOR 121] Antenas sin ping: "
        f"{cantidad_offline}/{len(antenas)}"
    )

    # Si hay menos de 2 offline, no hacemos reboot
    if cantidad_offline < 2:

        return {
            "ok": True,
            "reboot": False,
            "sector": ip_reboot,
            "offline_count": cantidad_offline,
            "offline_ips": antenas_offline,
            "results": resultados,
            "checked_at": timezone.now().isoformat(),
        }

    # =========================================================
    # 2 O MÁS ANTENAS SIN PING -> REINICIAR SECTOR 121
    # =========================================================

    print(
        f"[REBOOT] {cantidad_offline} antenas sin conexión. "
        f"Reiniciando {ip_reboot}"
    )

    reboot_result = reboot_via_https_confirm(
        ip_reboot,
        usuario,
        password,
    )

    # Preparar lista de IPs para notificación
    ips_offline_texto = ", ".join(antenas_offline)

    if reboot_result.get("ok"):

        push_result = enviar_notificacion_expo(
            title="🔄 Reinicio automático Sector 121",
            body=(
                f"{cantidad_offline} de {len(antenas)} antenas "
                f"no respondieron. Se reinició {ip_reboot}. "
                f"Sin conexión: {ips_offline_texto}"
            ),
            data={
                "type": "auto_reboot_sector",
                "sector": "121",
                "ip_reboot": ip_reboot,
                "offline_count": cantidad_offline,
                "offline_ips": antenas_offline,
            },
        )

    else:

        push_result = enviar_notificacion_expo(
            title="❌ Error reiniciando Sector 121",
            body=(
                f"{cantidad_offline} antenas no respondieron, "
                f"pero no fue posible reiniciar {ip_reboot}."
            ),
            data={
                "type": "auto_reboot_error",
                "sector": "121",
                "ip_reboot": ip_reboot,
                "offline_ips": antenas_offline,
                "reboot_result": reboot_result,
            },
        )

    return {
        "ok": reboot_result.get("ok", False),
        "reboot": True,
        "sector": ip_reboot,
        "offline_count": cantidad_offline,
        "offline_ips": antenas_offline,
        "results": resultados,
        "reboot_result": reboot_result,
        "notification": push_result,
        "checked_at": timezone.now().isoformat(),
    }  

def autoReboot127():

    # Antenas que vamos a comprobar
    antenas = [
        "192.168.1.21",
        "192.168.1.175",
        "192.168.1.171",
        "192.168.1.152",
        "192.168.1.190",

    ]

    # Antena principal del sector que se reiniciará
    ip_reboot = "192.168.1.127"

    usuario = "ubnt"
    password = "ubnt2"

    resultados = []

    # Comprobar las 4 antenas
    for ip in antenas:

        resultado = comprobar_ping(ip)
        resultados.append(resultado)

        if resultado["online"]:
            print(f"[OK] Antena {ip} respondió ping")
        else:
            print(
                f"[ALERTA] Antena {ip} no respondió "
                f"a ninguno de los 5 pings"
            )

    # Obtener antenas offline
    antenas_offline = [
        resultado["ip"]
        for resultado in resultados
        if not resultado["online"]
    ]

    cantidad_offline = len(antenas_offline)

    print(
        f"[SECTOR 127] Antenas sin ping: "
        f"{cantidad_offline}/{len(antenas)}"
    )

    # Si hay menos de 2 offline, no hacemos reboot
    if cantidad_offline < 2:

        return {
            "ok": True,
            "reboot": False,
            "sector": ip_reboot,
            "offline_count": cantidad_offline,
            "offline_ips": antenas_offline,
            "results": resultados,
            "checked_at": timezone.now().isoformat(),
        }

    # =========================================================
    # 2 O MÁS ANTENAS SIN PING -> REINICIAR SECTOR 121
    # =========================================================

    print(
        f"[REBOOT] {cantidad_offline} antenas sin conexión. "
        f"Reiniciando {ip_reboot}"
    )

    reboot_result = reboot_via_https_confirm(
        ip_reboot,
        usuario,
        password,
    )

    # Preparar lista de IPs para notificación
    ips_offline_texto = ", ".join(antenas_offline)

    if reboot_result.get("ok"):

        push_result = enviar_notificacion_expo(
            title="🔄 Reinicio automático Sector 121",
            body=(
                f"{cantidad_offline} de {len(antenas)} antenas "
                f"no respondieron. Se reinició {ip_reboot}. "
                f"Sin conexión: {ips_offline_texto}"
            ),
            data={
                "type": "auto_reboot_sector",
                "sector": "121",
                "ip_reboot": ip_reboot,
                "offline_count": cantidad_offline,
                "offline_ips": antenas_offline,
            },
        )

    else:

        push_result = enviar_notificacion_expo(
            title="❌ Error reiniciando Sector 121",
            body=(
                f"{cantidad_offline} antenas no respondieron, "
                f"pero no fue posible reiniciar {ip_reboot}."
            ),
            data={
                "type": "auto_reboot_error",
                "sector": "127",
                "ip_reboot": ip_reboot,
                "offline_ips": antenas_offline,
                "reboot_result": reboot_result,
            },
        )

    return {
        "ok": reboot_result.get("ok", False),
        "reboot": True,
        "sector": ip_reboot,
        "offline_count": cantidad_offline,
        "offline_ips": antenas_offline,
        "results": resultados,
        "reboot_result": reboot_result,
        "notification": push_result,
        "checked_at": timezone.now().isoformat(),
    }  