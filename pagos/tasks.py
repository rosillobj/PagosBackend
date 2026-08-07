import subprocess
import requests
from .views import login_airos_session,_is_login_html,_parse_reboot_form,urljoin,set_mikrotik_client_cut
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import subprocess
from .models import tokenExpo,Pagos,Cliente,SectorHealtModel



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
@shared_task
def autoReboot127():

    # Antenas que vamos a comprobar
    antenas = [
        "192.168.1.21",
        "192.168.1.175",
        "192.168.1.171",
        "192.168.1.152",
        "192.168.1.131",

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

@shared_task
def advicelist():
    today = timezone.localdate()
    limite = today - timedelta(days=40)

    cortes_qs = (
        Pagos.objects
        .filter(ultimo_pago=limite)
        .select_related("id_cliente", "id_user")
        .order_by("-ultimo_pago")
    )

    data = []

    for pago in cortes_qs:
        cliente = pago.id_cliente

        if cliente is None:
            continue

        data.append({
            "cliente_id": cliente.id,
            "cliente_nombre": getattr(cliente, "nombre", None),
            "cortado": getattr(cliente, "cortado", False),
            "ultimo_pago": pago.ultimo_pago.isoformat(),
            "ultimo_pago_p": pago.ultimo_pago_p,
            "ip": getattr(cliente, "ip_completa", None),
        })

    cantidad_clientes = len(data)

    # Si no se encontraron clientes, no se manda notificación
    if cantidad_clientes == 0:
        return {
            "ok": True,
            "notification_sent": False,
            "fecha_consultada": limite.isoformat(),
            "cantidad": 0,
            "clientes": [],
            "checked_at": timezone.now().isoformat(),
        }

    nombres = [
        cliente["cliente_nombre"] or f'Cliente #{cliente["cliente_id"]}'
        for cliente in data
    ]

    # Evita que la notificación sea demasiado larga
    nombres_mostrados = ", ".join(nombres[:5])

    if cantidad_clientes > 5:
        nombres_mostrados += f" y {cantidad_clientes - 5} más"

    push_result = enviar_notificacion_expo(
        title="⚠️ Nuevos clientes para corte",
        body=(
            f"{cantidad_clientes} cliente(s) llegaron a "
            f"40 días sin pago: {nombres_mostrados}"
        ),
        data={
            "type": "clientes_para_corte",
            "cantidad": cantidad_clientes,
            "fecha_limite": limite.isoformat(),
            "clientes": data,
        },
    )

    return {
        "ok": True,
        "notification_sent": True,
        "fecha_consultada": limite.isoformat(),
        "cantidad": cantidad_clientes,
        "clientes": data,
        "notification": push_result,
        "checked_at": timezone.now().isoformat(),
    }



@shared_task
def morososAdvice():
    limite = timezone.localdate() - timedelta(days=30)

    # Credenciales preferentemente desde variables de entorno/settings.py
    ip_router = "192.168.1.2"
    usuario = "admin"
    password = "Elmata30403.."

    clientes_morosos = Cliente.objects.filter(
        frecuencia_pago="MOROSO",
        cortado=False,
    )

    cortados = []
    errores = []
    omitidos = []

    for cliente in clientes_morosos:
        ultimo_pago = (
            Pagos.objects
            .filter(id_cliente=cliente)
            .exclude(ultimo_pago__isnull=True)
            .order_by("-ultimo_pago")
            .first()
        )

        # Cliente sin registro de pago
        if ultimo_pago is None:
            omitidos.append({
                "cliente_id": cliente.id,
                "cliente_nombre": cliente.nombre,
                "motivo": "No tiene registros de pago",
            })
            continue

        # Todavía no cumple 30 días
        if ultimo_pago.ultimo_pago > limite:
            continue

        client_ip = getattr(cliente, "ip_completa", None)

        if not client_ip:
            errores.append({
                "cliente_id": cliente.id,
                "cliente_nombre": cliente.nombre,
                "motivo": "No tiene una IP registrada",
            })
            continue

        resultado = set_mikrotik_client_cut(
            ip_router=ip_router,
            user=usuario,
            password=password,
            client_ip=client_ip,
            client_id=cliente.id,
            client_name=cliente.nombre,
            cut=True,
        )

        if resultado.get("ok") and resultado.get("confirmed"):
            # Actualizamos Django solamente después de confirmar el corte
            cliente.cortado = True
            cliente.save(update_fields=["cortado"])

            cortados.append({
                "cliente_id": cliente.id,
                "cliente_nombre": cliente.nombre,
                "ip": client_ip,
                "ultimo_pago": ultimo_pago.ultimo_pago.isoformat(),
                "resultado": resultado,
            })

        else:
            errores.append({
                "cliente_id": cliente.id,
                "cliente_nombre": cliente.nombre,
                "ip": client_ip,
                "ultimo_pago": ultimo_pago.ultimo_pago.isoformat(),
                "motivo": resultado.get(
                    "message",
                    "No fue posible confirmar el corte",
                ),
                "resultado": resultado,
            })

    cantidad_cortados = len(cortados)
    cantidad_errores = len(errores)

    # Mandar notificación si hubo cortes o errores
    push_result = None

    if cantidad_cortados > 0 or cantidad_errores > 0:
        nombres = [
            cliente["cliente_nombre"]
            for cliente in cortados[:5]
        ]

        nombres_texto = ", ".join(nombres)

        if cantidad_cortados > 5:
            nombres_texto += (
                f" y {cantidad_cortados - 5} más"
            )

        if cantidad_cortados > 0:
            body = (
                f"Se cortaron {cantidad_cortados} clientes: "
                f"{nombres_texto}."
            )
        else:
            body = "No se pudo cortar ningún cliente."

        if cantidad_errores > 0:
            body += (
                f" Se encontraron {cantidad_errores} errores."
            )

        push_result = enviar_notificacion_expo(
            title="⚠️ Corte automático de morosos",
            body=body,
            data={
                "type": "corte_automatico_morosos",
                "cantidad_cortados": cantidad_cortados,
                "cantidad_errores": cantidad_errores,
                "cortados": cortados,
                "errores": errores,
            },
        )

    return {
        "ok": cantidad_errores == 0,
        "fecha_limite": limite.isoformat(),
        "cantidad_cortados": cantidad_cortados,
        "cantidad_errores": cantidad_errores,
        "cantidad_omitidos": len(omitidos),
        "cortados": cortados,
        "errores": errores,
        "omitidos": omitidos,
        "notification": push_result,
        "checked_at": timezone.now().isoformat(),
    }
import json
import re
import subprocess

import urllib3
from celery import shared_task
from django.utils import timezone

from .models import SectorHealtModel


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


SECTORES_UBIQUITI = [
    "192.168.1.121",
    "192.168.1.122",
    "192.168.1.123",
    "192.168.1.124",
    "192.168.1.127",
    "192.168.1.126",
    "192.168.1.156",
    "192.168.1.129",
    "192.168.1.77",
]


def convertir_float(valor, default=0.0):
    """
    Convierte valores como:
    95, "95", "95.5", "65 Mbps", "65000 kbps"
    """
    if valor is None:
        return default

    if isinstance(valor, (int, float)):
        return float(valor)

    coincidencia = re.search(r"-?\d+(?:\.\d+)?", str(valor))

    if not coincidencia:
        return default

    return float(coincidencia.group())


def normalizar_ccq(valor):
    """
    Algunos equipos airOS entregan el CCQ como:
    95   -> 95 %
    950  -> 95 %
    9500 -> 95 %
    """
    ccq = convertir_float(valor)

    while ccq > 100:
        ccq /= 10

    return round(ccq, 2)


def normalizar_velocidad(valor):
    """
    Intenta convertir la velocidad a Mbps.

    Ejemplos:
    "65 Mbps"   -> 65
    "65000 Kbps" -> 65
    65          -> 65
    """
    velocidad = convertir_float(valor)
    texto = str(valor).lower()

    if "kbps" in texto or "kbit" in texto:
        velocidad /= 1000
    elif "gbps" in texto or "gbit" in texto:
        velocidad *= 1000
    elif "bps" in texto and "mbps" not in texto:
        velocidad /= 1_000_000

    return round(velocidad, 2)


def obtener_lista_antenas(data):
    """
    sta.cgi puede regresar directamente una lista o un diccionario
    que contiene stations.
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for llave in ("stations", "sta", "clients"):
            estaciones = data.get(llave)

            if isinstance(estaciones, list):
                return estaciones

    return []


def obtener_valor(antena, posibles_campos, default=None):
    for campo in posibles_campos:
        if campo in antena and antena[campo] is not None:
            return antena[campo]

    return default


def obtener_nombre_antena(antena):
    return (
        antena.get("hostname")
        or antena.get("name")
        or antena.get("mac")
        or antena.get("lastip")
        or "Antena desconocida"
    )


def obtener_ping_promedio(ip):
    """
    Envía tres pings y devuelve el promedio en milisegundos.
    Devuelve None cuando el sector no responde.
    """
    try:
        resultado = subprocess.run(
            ["ping", "-c", "3", "-W", "2", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )

        if resultado.returncode != 0:
            return None

        # Ejemplo:
        # rtt min/avg/max/mdev = 0.5/0.8/1.1/0.2 ms
        coincidencia = re.search(
            r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms",
            resultado.stdout,
        )

        if not coincidencia:
            return None

        return round(float(coincidencia.group(1)), 2)

    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def enviar_alerta_sector(resultado):
    """
    Sustituye el contenido de esta función por tu sistema actual
    de notificaciones Expo.
    """
    mensaje = (
        f"Alerta en {resultado['nombre_sector']} "
        f"({resultado['ip']}):\n- "
        + "\n- ".join(resultado["alertas"])
    )

    print(mensaje)

    # Aquí puedes llamar tu función existente:
    #
    # send_push_notification(
    #     title=f"Alerta: {resultado['nombre_sector']}",
    #     body=mensaje,
    # )


@shared_task
def analisisSector():
    resultados = []

    sectores = SectorHealtModel.objects.filter(
        sector__in=SECTORES_UBIQUITI
    ).order_by("id")

    usuario = "ubnt"
    password = "ubnt2"

    sectores_encontrados = set(sectores.values_list("sector", flat=True))

    # Detectar IP configurada en la tarea, pero ausente en la tabla.
    for ip in SECTORES_UBIQUITI:
        if ip not in sectores_encontrados:
            resultado = {
                "ip": ip,
                "nombre_sector": ip,
                "ok": False,
                "alertas": [
                    "El sector no está registrado en SectorHealtModel."
                ],
            }

            resultados.append(resultado)
            enviar_alerta_sector(resultado)

    for parametros in sectores:
        ip_sector = parametros.sector
        base = f"https://{ip_sector}"
        alertas = []

        resultado = {
            "ip": ip_sector,
            "nombre_sector": parametros.nombreSector or ip_sector,
            "ok": False,
            "alertas": alertas,
            "revisado_en": timezone.now().isoformat(),
        }

        # -----------------------------------------------------
        # 1. Comprobar ping
        # -----------------------------------------------------
        ping_promedio = obtener_ping_promedio(ip_sector)
        ping_maximo = convertir_float(parametros.ping)

        resultado["ping_ms"] = ping_promedio
        resultado["ping_maximo_ms"] = ping_maximo

        if ping_promedio is None:
            alertas.append("El sector no respondió al ping.")
        elif ping_maximo > 0 and ping_promedio > ping_maximo:
            alertas.append(
                f"Ping alto: {ping_promedio} ms; "
                f"máximo permitido: {ping_maximo} ms."
            )

        try:
            # -------------------------------------------------
            # 2. Iniciar sesión en airOS
            # -------------------------------------------------
            sesion = login_airos_session(
                ip_sector,
                usuario,
                password,
            )

            respuesta = sesion.get(
                f"{base}/sta.cgi",
                timeout=(3, 10),
                verify=False,
            )

            if respuesta.status_code != 200:
                alertas.append(
                    f"sta.cgi respondió HTTP {respuesta.status_code}."
                )

                resultados.append(resultado)
                enviar_alerta_sector(resultado)
                continue

            if _is_login_html(respuesta.text):
                alertas.append(
                    "La sesión de airOS no fue válida; "
                    "sta.cgi devolvió la pantalla de inicio de sesión."
                )

                resultados.append(resultado)
                enviar_alerta_sector(resultado)
                continue

            try:
                data = respuesta.json()
            except ValueError:
                data = json.loads(respuesta.text)

            antenas = obtener_lista_antenas(data)

            # -------------------------------------------------
            # 3. Comparar número de antenas
            # -------------------------------------------------
            numero_actual = len(antenas)
            numero_esperado = parametros.numeroAntenas or 0

            resultado["numero_antenas"] = numero_actual
            resultado["numero_antenas_esperado"] = numero_esperado

            if numero_actual < numero_esperado:
                alertas.append(
                    f"Antenas conectadas: {numero_actual}; "
                    f"esperadas: {numero_esperado}. "
                    f"Faltan {numero_esperado - numero_actual}."
                )
            elif numero_actual > numero_esperado:
                alertas.append(
                    f"Hay {numero_actual} antenas conectadas, "
                    f"pero en la tabla están registradas "
                    f"{numero_esperado}."
                )

            # -------------------------------------------------
            # 4. Comparar cada antena
            # -------------------------------------------------
            ccq_individual_minimo = convertir_float(
                parametros.ccqAntMin
            )
            tx_minimo = convertir_float(parametros.TxtMin)
            rx_minimo = convertir_float(parametros.RxtMin)

            ccq_encontrados = []

            for antena in antenas:
                nombre = obtener_nombre_antena(antena)

                ccq_raw = obtener_valor(
                    antena,
                    ["ccq", "txccq", "tx_ccq"],
                )
                tx_raw = obtener_valor(
                    antena,
                    ["tx", "txrate", "tx_rate"],
                )
                rx_raw = obtener_valor(
                    antena,
                    ["rx", "rxrate", "rx_rate"],
                )

                ccq = normalizar_ccq(ccq_raw)
                tx = normalizar_velocidad(tx_raw)
                rx = normalizar_velocidad(rx_raw)

                ccq_encontrados.append(ccq)

                if ccq < ccq_individual_minimo:
                    alertas.append(
                        f"{nombre}: CCQ {ccq}% menor al mínimo "
                        f"{ccq_individual_minimo}%."
                    )

                if tx < tx_minimo:
                    alertas.append(
                        f"{nombre}: TX {tx} Mbps menor al mínimo "
                        f"{tx_minimo} Mbps."
                    )

                # Si RxtMin es 0, no se valida RX.
                if rx_minimo > 0 and rx < rx_minimo:
                    alertas.append(
                        f"{nombre}: RX {rx} Mbps menor al mínimo "
                        f"{rx_minimo} Mbps."
                    )

            # -------------------------------------------------
            # 5. Comparar CCQ general del sector
            # -------------------------------------------------
            ccq_sector_minimo = convertir_float(
                parametros.ccqMin
            )

            if ccq_encontrados:
                ccq_promedio = round(
                    sum(ccq_encontrados) / len(ccq_encontrados),
                    2,
                )

                resultado["ccq_promedio"] = ccq_promedio
                resultado["ccq_minimo"] = ccq_sector_minimo

                if ccq_promedio < ccq_sector_minimo:
                    alertas.append(
                        f"CCQ promedio del sector: {ccq_promedio}%; "
                        f"mínimo requerido: {ccq_sector_minimo}%."
                    )
            else:
                alertas.append(
                    "sta.cgi no devolvió ninguna antena conectada."
                )

        except Exception as error:
            alertas.append(
                f"No fue posible consultar el sector: "
                f"{type(error).__name__}: {error}"
            )

        resultado["ok"] = len(alertas) == 0
        resultados.append(resultado)

        if alertas:
            enviar_alerta_sector(resultado)

    sectores_con_alerta = sum(
        1 for resultado in resultados if not resultado["ok"]
    )

    return {
        "ok": sectores_con_alerta == 0,
        "sectores_revisados": len(resultados),
        "sectores_con_alerta": sectores_con_alerta,
        "resultados": resultados,
        "revisado_en": timezone.now().isoformat(),
    }