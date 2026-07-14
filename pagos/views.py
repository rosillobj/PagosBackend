from django.shortcuts import render,get_object_or_404
from .models import Cliente,Pagos,tokenExpo
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework.generics import ListCreateAPIView,ListAPIView,DestroyAPIView,RetrieveAPIView,UpdateAPIView
from .serializers import ClienteSerializer,PagosSerializer,TokenSerializer
from rest_framework import status
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
import ipaddress
import re
import requests
import socket
import urllib3
from requests.auth import HTTPBasicAuth
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib.parse import urljoin
import json
from typing import Any, Dict, List, Tuple, Union
from librouteros import connect
from librouteros.exceptions import LibRouterosError
from bs4 import BeautifulSoup
from rest_framework.decorators import api_view
# Create your views here.



class ClientesListView(ListAPIView):
    
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class PagosListView(APIView):
    permission_classes = [IsAuthenticated]
    
    
    def get(self,request,pk):
        pagos = Pagos.objects.get(id_cliente = pk)
        if(pagos):
            print("uno")
            serializer = PagosSerializer(pagos)
            return Response(status=status.HTTP_200_OK,data =serializer.data)
        else:
            return Response(status= status.HTTP_204_NO_CONTENT)
        







MONTHS = {
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december"
}

class PagoNuevoListView(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Pagos.objects.all()

    def patch(self, request, *args, **kwargs):
        cliente_id = request.data.get("id")
        pago_raw = request.data.get("pago")
        fecha_raw = request.data.get("fecha")  # "2026-02-09"

        if not cliente_id or pago_raw is None or not fecha_raw:
            return Response(
                {"detail": "Requiere: id, pago, fecha (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            pago = int(pago_raw)
            if pago < 0:
                return Response(
                    {"detail": "El pago no puede ser negativo."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (TypeError, ValueError):
            return Response(
                {"detail": "El campo 'pago' debe ser un entero."},
                status=status.HTTP_400_BAD_REQUEST
            )

        fecha_pago = parse_date(str(fecha_raw))
        if not fecha_pago:
            return Response(
                {"detail": "Fecha inválida. Usa YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        mesFront = MONTHS[fecha_pago.month]

        try:
           pagos = Pagos.objects.get(id_cliente_id=cliente_id)
        except Pagos.DoesNotExist:
           return Response(
        {"detail": "No existe registro de pagos para ese cliente."},
        status=status.HTTP_404_NOT_FOUND
    )

# Validar que la fecha enviada no sea menor al último pago registrado
        if pagos.ultimo_pago and fecha_pago < pagos.ultimo_pago:
          return Response(
        {
            "detail": "La fecha enviada no puede ser menor al último pago registrado.",
            "ultimo_pago_actual": str(pagos.ultimo_pago),
            "fecha_enviada": str(fecha_pago),
        },
        status=status.HTTP_400_BAD_REQUEST
    )

        # por defecto usa el mes actual
        mes_nombre = MONTHS[timezone.now().month]
        mes_p = f"{mes_nombre}_p"
        mes_d = mes_nombre

        print("mes actual:", mes_nombre)
        print("mes front:", mesFront)

        # solo si es diferente, usar el mes enviado por el front
        if mes_nombre != mesFront:
            mes_p = f"{mesFront}_p"
            mes_d = mesFront

        total_anterior = getattr(pagos, mes_p, 0) or 0
        total_nuevo = total_anterior + pago

        setattr(pagos, mes_p, total_nuevo)
        setattr(pagos, mes_d, fecha_pago)

        pagos.ultimo_pago = fecha_pago
        pagos.ultimo_pago_p = pago
        pagos.id_user = request.user

        pagos.save(update_fields=[mes_p, mes_d, "ultimo_pago", "ultimo_pago_p", "id_user"])

        return Response(
            {
                "mes": mes_d,
                "campo_monto": mes_p,
                "total_mes": total_nuevo,
                "fecha": str(fecha_pago)
            },
            status=status.HTTP_200_OK
        )
class CortesView(ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Pagos.objects.all()

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()
        limite = today - timedelta(days=40)

        cortes_qs = (
            Pagos.objects
            .filter(ultimo_pago__lt=limite)
            .select_related("id_cliente", "id_user")
            .order_by("-ultimo_pago")
        )

        data = []
        for p in cortes_qs:
            c = p.id_cliente  # Cliente (o None si está null)
            data.append({
                "pago_id": p.id,
                "cliente_id": c.id if c else None,
                "cliente_nombre": getattr(c, "nombre", None),  # ajusta si tu campo se llama diferente
                 "cliente_direccion":getattr(c,"direccion",None),
                "ultimo_pago": p.ultimo_pago,                 # DateField -> DRF lo serializa a "YYYY-MM-DD"
                "ultimo_pago_p": p.ultimo_pago_p,
                "id_user": p.id_user_id,                       # quién registró el último movimiento
            })

        return Response(
            {
                "limite": str(limite),
                "usuarios_count": cortes_qs.count(),
                "results": data
            },
            status=status.HTTP_200_OK
        )
class CortarServicio(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()
    
    def patch(self, request, *args, **kwargs):
        id_ClienteRaw = request.data['cliente_id']
        print(id_ClienteRaw)
        cliente = Cliente.objects.get(id = id_ClienteRaw)
        if cliente:
            setattr(cliente,'cortado', True )
            cliente.save()
        return Response ( status=status.HTTP_200_OK)


class ActivarServicio(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()
    
    def patch(self, request, *args, **kwargs):
        id_ClienteRaw = request.data['cliente_id']
        print(id_ClienteRaw)
        cliente = Cliente.objects.get(id = id_ClienteRaw)
        if cliente:
            setattr(cliente,'cortado', False )
            cliente.save()
        return Response ( status=status.HTTP_200_OK)


class IpsAvaibleView(ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()

    def get(self, request, *args, **kwargs):
        start = int(request.query_params.get("start", 21))
        end = int(request.query_params.get("end", 254))
        limit = request.query_params.get("limit")
        limit = int(limit) if limit is not None else None

        if start < 0 or end > 255 or start > end:
            return Response(
                {"detail": "Rango inválido. Usa start<=end y 0..255."},
                status=status.HTTP_400_BAD_REQUEST
            )

        network = ipaddress.ip_network("192.168.1.0/24")

        # IPs reservadas / excluidas manualmente
        reserved_ips = {
            "192.168.1.99",
            "192.168.1.100",
            "192.168.1.156",
            "192.168.1.101",
            "192.168.1.127",
            "192.168.1.122",
            "192.168.1.124",
            "192.168.1.121",
            "192.168.1.129",
            "192.168.1.151",
            "192.168.1.123",
            "192.168.1.125",
            "192.168.1.110",
            "192.168.1.111",
            "192.168.1.120",
        }

        # Convertimos reservadas a último octeto
        reserved_octets = set()
        for ip_str in reserved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj in network:
                    reserved_octets.add(int(str(ip_obj).split(".")[-1]))
            except ValueError:
                pass

        ocupadas_raw = (
            Cliente.objects
            .exclude(ip_completa__isnull=True)
            .exclude(ip_completa__exact="")
            .values_list("ip_completa", flat=True)
        )

        ocupadas = set()
        invalidas = []

        for ip_str in ocupadas_raw:
            ip_str = str(ip_str).strip()

            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                invalidas.append(ip_str)
                continue

            if ip_obj in network:
                ocupadas.add(int(str(ip_obj).split(".")[-1]))

        # Unimos ocupadas + reservadas
        bloqueadas = ocupadas | reserved_octets

        disponibles = []
        for host in range(start, end + 1):
            if host in bloqueadas:
                continue

            ip_candidate = ipaddress.ip_address(f"192.168.1.{host}")
            if ip_candidate in network:
                disponibles.append(str(ip_candidate))

        if limit is not None:
            disponibles = disponibles[:limit]

        return Response(
            {
                "subnet": str(network),
                "range": {"start": start, "end": end},
                "ocupadas_count": len(ocupadas),
                "reservadas_count": len(reserved_octets),
                "bloqueadas_count": len(bloqueadas),
                "disponibles_count": len(disponibles),
                "disponibles": disponibles,
                "ips_invalidas_en_db": invalidas[:50],
            },
            status=status.HTTP_200_OK
        )




def _to_number_if_possible(v: str):
    v = v.strip()
    # quita comillas
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]

    # bool
    if v.lower() in ("true", "false"):
        return v.lower() == "true"

    # int
    if re.fullmatch(r"-?\d+", v):
        try:
            return int(v)
        except:
            return v

    # float
    if re.fullmatch(r"-?\d+\.\d+", v):
        try:
            return float(v)
        except:
            return v

    return v


def parse_airos_status_text(text: str) -> Dict[str, Any]:
    """
    Convierte el status.cgi “tipo texto” de airOS (como el que pegaste)
    en un diccionario anidado.
    """
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # ignora basura típica si aparece
        if line.startswith("<!--") or line.startswith("<!DOCTYPE"):
            continue
        lines.append(line)

    # La estructura viene como pares: key en una línea, valor en otra.
    # Cuando la “siguiente” línea no parece valor, se interpreta como sub-sección.
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(0, root)]  # (indent_level, current_dict)

    def current_dict() -> Dict[str, Any]:
        return stack[-1][1]

    i = 0
    while i < len(lines):
        key = lines[i]
        # mira si hay "valor" inmediatamente después
        nxt = lines[i + 1] if i + 1 < len(lines) else None

        # Heurística: si la siguiente línea parece valor (tiene comillas, número, true/false, o contiene espacios tipo "2352 MHz")
        def looks_like_value(s: str) -> bool:
            if s is None:
                return False
            if s.startswith('"') or s.startswith("'"):
                return True
            if re.fullmatch(r"-?\d+(\.\d+)?", s):
                return True
            if s.lower() in ("true", "false"):
                return True
            # cosas tipo: 2352 MHz, v6.1.7, NanoStation loco M2
            if any(ch.isdigit() for ch in s) and " " in s:
                return True
            # MAC
            if re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", s):
                return True
            # tokens con puntos/guiones
            if re.fullmatch(r"[A-Za-z0-9._:-]+", s):
                return True
            return False

        if nxt is not None and looks_like_value(nxt):
            # set key:value
            current_dict()[key] = _to_number_if_possible(nxt)
            i += 2
            continue

        # Si no hay valor, interpretamos como sección (dict) y seguimos
        # A veces hay índices tipo "0", "1" dentro de "interfaces" → lo tratamos como subsección dict también
        new_section: Dict[str, Any] = {}
        current_dict()[key] = new_section
        stack.append((len(stack), new_section))
        i += 1

        # Truco: si la próxima línea parece “otra sección al mismo nivel” y no llenamos nada,
        # el parser se autoacomoda por la secuencia natural. (Funciona bien con tu formato.)
        # Para evitar stack infinito, si detectamos que la sección quedó vacía y la siguiente no es par,
        # iremos cerrando más abajo cuando aparezcan pares.

        # Limpieza del stack: si la sección anterior no recibe nada y aparece una clave “superior”,
        # esto es difícil sin indent real. Lo dejamos simple y robusto:
        # cerramos secciones vacías cuando detectamos repetición de claves top-level comunes.
        # (Opcional: lo podemos mejorar si tu salida real trae tabs/indent.)
        # Por ahora, no cerramos aquí.

    return root


def extract_eth0(status: Dict[str, Any]) -> Dict[str, Any]:
    interfaces = status.get("interfaces")

    # Caso dict: {"0": {...}, "1": {...}}
    if isinstance(interfaces, dict):
        for _, iface in interfaces.items():
            if isinstance(iface, dict) and iface.get("ifname") == "eth0":
                return iface

    # Caso list: [{...}, {...}]
    if isinstance(interfaces, list):
        for iface in interfaces:
            if isinstance(iface, dict) and iface.get("ifname") == "eth0":
                return iface

    return {}


def normalize_airos(status: Dict[str, Any]) -> Dict[str, Any]:
    w = status.get("wireless", {}) if isinstance(status.get("wireless"), dict) else {}
    p = w.get("polling", {}) if isinstance(w.get("polling"), dict) else {}

    eth0 = extract_eth0(status)
    eth0_status = eth0.get("status", {}) if isinstance(eth0.get("status"), dict) else {}

    totalram = status.get("totalram")
    freeram = status.get("freeram")

    def pct_free_ram():
        try:
            return round((float(freeram) / float(totalram)) * 100, 1)
        except Exception:
            return None

    return {
        "device": {
            "hostname": status.get("hostname"),
            "devmodel": status.get("devmodel"),
            "fwversion": status.get("fwversion"),
            "fwprefix": status.get("fwprefix"),
            "netrole": status.get("netrole"),
            "time": status.get("time"),
            "uptime": status.get("uptime"),
        },
        "system": {
            "cpuload": status.get("cpuload"),
            "totalram": totalram,
            "freeram": freeram,
            "free_ram_pct": pct_free_ram(),
        },
        "wireless": {
            "mode": w.get("mode"),
            "essid": w.get("essid"),
            "apmac": w.get("apmac"),
            "frequency": w.get("frequency"),
            "opmode": w.get("opmode"),
            "security": w.get("security"),
            "antenna": w.get("antenna"),
            "chains": w.get("chains"),
        },
        "link": {
            "signal_dbm": w.get("signal"),
            "noise_dbm": w.get("noisef"),
            "txpower_dbm": w.get("txpower"),
            "distance_m": w.get("distance"),
            "ccq": w.get("ccq"),
            "txrate_mbps": w.get("txrate"),
            "rxrate_mbps": w.get("rxrate"),
            "quality_pct": p.get("quality"),
            "capacity_pct": p.get("capacity"),
        },
        "interfaces": {
            "eth0": {
                "ifname": eth0.get("ifname"),
                "enabled": eth0.get("enabled"),
                "plugged": eth0_status.get("plugged"),
                "speed": eth0_status.get("speed"),
                "duplex": eth0_status.get("duplex"),
            }
        }
    }

def _is_login_html(text: str) -> bool:
    t = (text or "").lower()
    return ("inicio de sesi" in t) or ("login.cgi" in t) or ("<title>inicio" in t) or ("<form" in t and "password" in t)

def fetch_airos_status_https_with_session(ip: str, user: str, password: str) -> str:
    """
    1) Abre login.cgi para setear cookies
    2) Postea credenciales
    3) Descarga status.cgi ya autenticado (misma sesión)
    """
    s = make_relaxed_https_session()  # tu session con TLSRelaxAdapter (SECLEVEL=1)

    base = f"https://{ip}"

    # 1) warm up / cookies
    s.get(f"{base}/login.cgi", timeout=(3, 6), verify=False, allow_redirects=True)

    # 2) login (probamos 2 payloads comunes en airOS)
    payloads = [
        {"username": user, "password": password},
        {"user": user, "password": password},  # algunos firmwares usan "user"
    ]

    logged_in = False
    last_preview = ""
    for data in payloads:
        resp = s.post(
            f"{base}/login.cgi",
            data=data,
            timeout=(3, 6),
            verify=False,
            allow_redirects=True,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        last_preview = (resp.text or "")[:300]
        # Si NO es HTML de login, o si ya nos dejó cookie, lo consideramos login ok
        if not _is_login_html(resp.text):
            logged_in = True
            break

        # A veces el login responde HTML igual, pero ya dejó cookie; entonces probamos status.cgi
        test = s.get(f"{base}/status.cgi", timeout=(3, 6), verify=False, allow_redirects=True)
        if not _is_login_html(test.text) and test.status_code == 200:
            logged_in = True
            return test.text

    if not logged_in:
        # Debug útil
        return f"__LOGIN_FAILED_HTML__\n{last_preview}"

    # 3) status.cgi autenticado
    r = s.get(
        f"{base}/status.cgi",
        timeout=(3, 6),
        verify=False,
        allow_redirects=True,
        headers={"Accept": "text/plain, application/json, */*"},
    )
    r.raise_for_status()
    return r.text

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class TLSRelaxAdapter(HTTPAdapter):
    """
    Adapter para conectarse a equipos legacy (airOS viejo).
    Baja SECLEVEL para permitir DH pequeño y habilita compatibilidad legacy.
    """
    def __init__(self, **kwargs):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

        # ✅ Este es el punto clave para DH_KEY_TOO_SMALL
        # (baja el nivel de seguridad)
        self.ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")

        # ✅ Compatibilidad extra con servidores legacy (OpenSSL 3)
        if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
            self.ssl_context.options |= ssl.OP_LEGACY_SERVER_CONNECT

        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["ssl_context"] = self.ssl_context
        self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs)


def make_relaxed_https_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", TLSRelaxAdapter())
    return s


def _try_airOS_status_https2(ip: str, user: str, password: str) -> dict:
    url = f"https://{ip}/status.cgi"
    print("Consultando URL (HTTPS):", url)

    try:
        raw_text = fetch_airos_status_https_with_session(ip, user, password)
        print(raw_text)
        # Si el helper devolvió un marcador de falla
        if raw_text.startswith("__LOGIN_FAILED_HTML__"):
            return {
                "ok": False,
                "stage": "login_failed",
                "message": "No se pudo iniciar sesión (sigue devolviendo HTML de login).",
                "raw_preview": raw_text.split("\n", 1)[-1][:400].replace("\n", "\\n"),
            }

        # Si todavía llega login, reporta
        if _is_login_html(raw_text):
            return {
                "ok": False,
                "stage": "unexpected_html",
                "message": "Aún devuelve HTML de login (sesión no válida).",
                "raw_preview": raw_text[:400].replace("\n", "\\n"),
            }

        parsed = parse_airos_smart(raw_text)      # usa el parser “smart” si lo tienes
        normalized = normalize_airos(parsed)

        return {"ok": True, "transport": "https", "source": "status.cgi", "normalized": normalized}

    except requests.exceptions.SSLError as e:
        return {"ok": False, "stage": "ssl", "message": f"SSL error: {e}"}
    except Exception as e:
        return {"ok": False, "stage": "unknown", "message": f"Error: {e}"}





class AntenaView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()

    def get(self, request, pk):
        usuario = "ubnt"
        password = "ubnt2"

        cliente = Cliente.objects.filter(id=pk).first()
        if not cliente:
            return Response({"detail": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        ip = (cliente.ip_completa or "").strip()
        if not ip:
            return Response({"detail": "Cliente sin ip_completa"}, status=status.HTTP_400_BAD_REQUEST)

        data = _try_airOS_status_https(ip, usuario, password)

        return Response(
            {"cliente_id": cliente.id, "ip": ip,"status_cortado":cliente.cortado,"antena":data},
            status=status.HTTP_200_OK
        )


def _clean_value(v: str):
    v = v.strip()

    # Quitar comillas
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]

    # Booleanos
    if v.lower() in ("true", "false"):
        return v.lower() == "true"

    # Enteros
    if re.fullmatch(r"-?\d+", v):
        try:
            return int(v)
        except:
            return v

    # Flotantes
    if re.fullmatch(r"-?\d+\.\d+", v):
        try:
            return float(v)
        except:
            return v

    return v


def parse_airos_smart(raw_text: str) -> Dict[str, Any]:
    """
    Parser flexible para status.cgi de airOS.
    Detecta JSON, JS embebido o texto tipo clave/valor.
    """

    if not raw_text:
        return {}

    text = raw_text.strip()

    # =====================================================
    # 1️⃣ Intentar JSON directo
    # =====================================================
    try:
        return json.loads(text)
    except Exception:
        pass

    # =====================================================
    # 2️⃣ Intentar extraer JSON dentro de JS
    #    Ej: var status = {...};
    # =====================================================
    js_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if js_match:
        candidate = js_match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # =====================================================
    # 3️⃣ Parse formato texto clásico airOS
    # =====================================================
    lines = [line.rstrip("\r") for line in raw_text.splitlines() if line.strip()]
    root: Dict[str, Any] = {}
    stack = [(0, root)]  # (indent_level, current_dict)

    def indent_level(s: str) -> int:
        level = 0
        for ch in s:
            if ch == "\t":
                level += 4
            elif ch == " ":
                level += 1
            else:
                break
        return level

    i = 0
    while i < len(lines):
        line = lines[i]
        ind = indent_level(line)
        stripped = line.strip()

        # Ajustar stack según indentación
        while stack and ind < stack[-1][0]:
            stack.pop()

        current_dict = stack[-1][1]

        # Caso key\tvalue
        if "\t" in stripped:
            parts = [p for p in stripped.split("\t") if p != ""]
            if len(parts) >= 2:
                key = parts[0].strip()
                value = "\t".join(parts[1:]).strip()
                current_dict[key] = _clean_value(value)
                i += 1
                continue

        # Caso clave en una línea y valor en la siguiente
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            next_stripped = next_line.strip()

            looks_like_value = (
                next_stripped.startswith(("'", '"')) or
                re.fullmatch(r"-?\d+(\.\d+)?", next_stripped) or
                next_stripped.lower() in ("true", "false") or
                re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", next_stripped)
            )

            if looks_like_value:
                current_dict[stripped] = _clean_value(next_stripped)
                i += 2
                continue

            # Si siguiente línea tiene más indentación → subsección
            if indent_level(next_line) > ind:
                new_dict = {}
                current_dict[stripped] = new_dict
                stack.append((indent_level(next_line), new_dict))
                i += 1
                continue

        # Si nada coincide, lo guardamos como sección vacía
        current_dict[stripped] = {}
        stack.append((ind + 1, current_dict[stripped]))
        i += 1

    return root


def _parse_reboot_form(html: str):
    """
    Extrae action del <form> y los inputs hidden {name: value}.
    """
    # action del primer form
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
    action = m.group(1) if m else "/reboot.cgi"

    # inputs hidden
    hidden = {}
    for name, value in re.findall(
        r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
        html,
        flags=re.IGNORECASE,
    ):
        hidden[name] = value

    # algunos firmwares traen hidden sin value explícito
    for name in re.findall(
        r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    ):
        hidden.setdefault(name, "")

    return action, hidden
class RebootAntenaView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        usuario = "ubnt"
        password = "ubnt2"

        cliente = Cliente.objects.filter(id=pk).first()
        if not cliente:
            return Response({"ok": False, "detail": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        ip = (cliente.ip_completa or "").strip()
        if not ip:
            return Response({"ok": False, "detail": "Cliente sin ip_completa"}, status=status.HTTP_400_BAD_REQUEST)

        result = reboot_via_https_confirm(ip, usuario, password)

        # Si falla, igual regreso 200 con ok:false para que el front lo maneje fácil
        return Response(
            {"cliente_id": cliente.id, "ip": ip, "reboot": result},
            status=status.HTTP_200_OK
        )
        
def login_airos_session(ip: str, user: str, password: str) -> requests.Session:
    """
    Devuelve una sesión autenticada lista para usar (cookies + TLS relax).
    """
    base = f"https://{ip}"
    s = make_relaxed_https_session()

    # Warm-up cookies
    s.get(f"{base}/login.cgi", timeout=(3, 6), verify=False, allow_redirects=True)

    # Intento login
    payloads = [
        {"username": user, "password": password},
        {"user": user, "password": password},
    ]

    for data in payloads:
        resp = s.post(
            f"{base}/login.cgi",
            data=data,
            timeout=(3, 6),
            verify=False,
            allow_redirects=True,
        )

        if not _is_login_html(resp.text):
            return s

        # probar acceso a status
        test = s.get(f"{base}/status.cgi", timeout=(3, 6), verify=False)
        if test.status_code == 200 and not _is_login_html(test.text):
            return s

    raise Exception("No se pudo iniciar sesión en la antena")
def reboot_via_https_confirm(ip: str, user: str, password: str) -> dict:
    base = f"https://{ip}"

    try:
        s = login_airos_session(ip, user, password)

        # 1️⃣ Abrir reboot.cgi
        r1 = s.get(f"{base}/reboot.cgi", timeout=(3, 6), verify=False)

        if r1.status_code != 200:
            return {"ok": False, "stage": "open_reboot", "status_code": r1.status_code}

        html = r1.text or ""

        if _is_login_html(html):
            return {"ok": False, "stage": "auth_lost"}

        action, hidden = _parse_reboot_form(html)
        post_url = urljoin(f"{base}/", action)

        payload = dict(hidden)
        payload.setdefault("reboot", "1")
        payload.setdefault("action", "reboot")
        payload.setdefault("do_reboot", "1")
        payload.setdefault("confirm", "1")

        # 2️⃣ Confirmar reboot
        r2 = s.post(
            post_url,
            data=payload,
            timeout=(3, 6),
            verify=False,
        )

        # Si responde 200/302 y luego se cae, es correcto
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
class RebootSectorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        usuario = "ubnt"
        password = "ubnt2"



        ip = (f"192.168.1.{pk}").strip()
        if not ip:
            return Response({"ok": False, "detail": "Cliente sin ip_completa"}, status=status.HTTP_400_BAD_REQUEST)

        result = reboot_via_https_confirm(ip, usuario, password)

        # Si falla, igual regreso 200 con ok:false para que el front lo maneje fácil
        return Response(
            { "ip": ip, "reboot": result},
            status=status.HTTP_200_OK
        )
        
class SectorView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()

    def get(self, request, pk):
        usuario = "ubnt"
        password = "ubnt2"

 

        ip = (f"192.168.1.{pk}").strip()
        print(ip)
        if not ip:
            return Response({"detail": "Cliente sin ip_completa"}, status=status.HTTP_400_BAD_REQUEST)

        data = _try_airOS_status_https(ip, usuario, password)

        return Response(
            { "ip": ip, "antena": data},
            status=status.HTTP_200_OK
        )


def _tcp_check(ip: str, port: int, timeout: float = 2.5) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return {"ok": True, "port": port}
    except Exception as e:
        return {"ok": False, "port": port, "error": str(e)}
    finally:
        try:
            s.close()
        except Exception:
            pass

def mt_connect(ip: str, user: str, password: str, port: int = 8728, timeout: int = 5):
    """
    Conecta a MikroTik RouterOS API (v6) y devuelve la conexión.
    """
    return connect(
        host=ip,
        username=user,
        password=password,
        port=port,
        timeout=timeout,
    )
def mt_status(ip: str, user: str, password: str) -> dict:
    # “ping real” al API
    tcp = _tcp_check(ip, 8728)
    if not tcp["ok"]:
        return {"ok": False, "stage": "tcp_check", "message": "No abre API 8728", "tcp": tcp}

    try:
        api = mt_connect(ip, user, password)

        # Identity
        ident = next(iter(api.path("/system/identity").select()), None)  # {'name': '...'}
        identity = ident.get("name") if isinstance(ident, dict) else None

        # Resource
        res = next(iter(api.path("/system/resource").select()), None)
        # RouterOS v6 suele traer keys: version, board-name, platform, uptime, cpu-load, free-memory, total-memory...
        version = res.get("version") if isinstance(res, dict) else None
        board = res.get("board-name") if isinstance(res, dict) else None
        uptime = res.get("uptime") if isinstance(res, dict) else None
        cpu_load = res.get("cpu-load") if isinstance(res, dict) else None
        free_mem = res.get("free-memory") if isinstance(res, dict) else None
        total_mem = res.get("total-memory") if isinstance(res, dict) else None

        free_pct = None
        try:
            if free_mem is not None and total_mem:
                free_pct = round((float(free_mem) / float(total_mem)) * 100, 1)
        except Exception:
            pass

        # Interfaces: buscamos ether1 por nombre (SXT Lite normalmente trae ether1)
        ether1 = None
        for it in api.path("/interface").select():
            if isinstance(it, dict) and it.get("name") == "ether1":
                ether1 = it
                break

        # running/disabled suelen venir como 'true'/'false' strings
        def to_bool(v):
            if isinstance(v, bool): return v
            if isinstance(v, str): return v.lower() == "true"
            return None

        eth = {
            "name": ether1.get("name") if ether1 else "ether1",
            "running": to_bool(ether1.get("running")) if ether1 else None,
            "disabled": to_bool(ether1.get("disabled")) if ether1 else None,
            "type": ether1.get("type") if ether1 else None,
            "mtu": ether1.get("mtu") if ether1 else None,
        }

        # Wireless (SXT Lite usual: wlan1)
        wlan = None
        for w in api.path("/interface/wireless").select():
            if isinstance(w, dict) and w.get("name") == "wlan1":
                wlan = w
                break

        wireless = {
            "name": wlan.get("name") if wlan else "wlan1",
            "mode": wlan.get("mode") if wlan else None,
            "ssid": wlan.get("ssid") if wlan else None,
            "band": wlan.get("band") if wlan else None,
            "frequency": wlan.get("frequency") if wlan else None,
            "tx_power": wlan.get("tx-power") if wlan else None,
            "disabled": to_bool(wlan.get("disabled")) if wlan else None,
        }

        # Monitor wireless (da señal, tx/rx, etc). En v6: /interface/wireless/monitor numbers=wlan1 once
        link = {}
        try:
            mon = list(api.path("/interface/wireless/monitor").call(numbers="wlan1", once=""))  # devuelve lista de dicts
            mon0 = mon[0] if mon else {}
            # keys típicas: signal-strength, tx-rate, rx-rate, noise-floor, snr, ccq, etc (varía)
            link = {
                "signal_dbm": mon0.get("signal-strength"),
                "noise_dbm": mon0.get("noise-floor"),
                "snr_db": mon0.get("snr"),
                "tx_rate": mon0.get("tx-rate"),
                "rx_rate": mon0.get("rx-rate"),
                "ccq": mon0.get("ccq"),
            }
        except Exception:
            # no pasa nada si no soporta/permiso
            link = {}

        return {
            "ok": True,
            "transport": "routeros_api",
            "normalized": {
                "device": {
                    "identity": identity,
                    "board": board,
                    "version": version,
                    "uptime": uptime,
                },
                "system": {
                    "cpu_load": cpu_load,
                    "free_memory": free_mem,
                    "total_memory": total_mem,
                    "free_ram_pct": free_pct,
                },
                "interfaces": {
                    "ether1": eth
                },
                "wireless": wireless,
                "link": link,
            }
        }

    except LibRouterosError as e:
        return {"ok": False, "stage": "api_error", "message": str(e)}
    except Exception as e:
        return {"ok": False, "stage": "unknown", "message": str(e)}
    


class MikrotikStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = "admin"
        password = "ubnt2"

        cliente = Cliente.objects.filter(id=pk).first()
        if not cliente:
            print("no esta Jhon")
            return Response({"detail": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        ip = (cliente.ip_completa or "").strip()
        if not ip:
            return Response({"detail": "Cliente sin ip_completa"}, status=status.HTTP_400_BAD_REQUEST)

        data = mt_status(ip, user, password)
        return Response({"cliente_id": cliente.id, "ip": ip, "mikrotik": data}, status=status.HTTP_200_OK)



class LastPayment(APIView):
    
    permission_classes=[IsAuthenticated]
    
    def get(self, request,pk):
        
        pagos = Pagos.objects.get(id_cliente = pk)
        
        if not pagos:
            return Response(status=status.HTTP_404_NOT_FOUND)
        else :
            lastPayment = pagos.ultimo_pago
            data={
                "ultimo_pago":lastPayment
            }
            return Response(status=status.HTTP_200_OK,data=data)
        
class DestroyCliente(DestroyAPIView):
    
    permission_classes = [IsAuthenticated]
    queryset=Cliente.objects.all()
    
    def destroy(self, request, *args, **kwargs):
        print("apunta Aqui ")
        return super().destroy(request, *args, **kwargs)

class EditAntenaView(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer  # asegúrate de tenerlo importado

    def patch(self, request, pk, *args, **kwargs):
        cliente = get_object_or_404(Cliente, id=pk)
        serializer = self.get_serializer(cliente, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def is_invalid_tx(station):
    tx = station.get("tx")

    if tx in (None, "", "-"):
        return True

    try:
        return float(tx) < 1
    except (TypeError, ValueError):
        return True
def should_reboot_by_tx(stations, threshold=0.80):
    total = len(stations)

    if total == 0:
        return False, {
            "total": 0,
            "invalid_tx": 0,
            "invalid_percent": 0,
            "reason": "sin estaciones asociadas"
        }

    invalid_count = sum(1 for s in stations if is_invalid_tx(s))
    invalid_percent = invalid_count / total

    return invalid_percent >= threshold, {
        "total": total,
        "invalid_tx": invalid_count,
        "invalid_percent": round(invalid_percent * 100, 2),
    }
class SectorTxHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        usuario = "ubnt"
        password = "ubnt2"
        ip = f"192.168.1.{pk}"

        try:
            s = login_airos_session(ip, usuario, password)

            r = s.get(
                f"https://{ip}/sta.cgi",
                timeout=(3, 8),
                verify=False,
                headers={"Accept": "application/json, text/plain, */*"},
            )

            if r.status_code != 200:
                return Response({
                    "ok": False,
                    "ip": ip,
                    "stage": "sta_request",
                    "status_code": r.status_code,
                    "detail": "No se pudo consultar sta.cgi",
                }, status=status.HTTP_200_OK)

            try:
                stations = r.json()
            except Exception:
                return Response({
                    "ok": False,
                    "ip": ip,
                    "stage": "json_parse",
                    "detail": "sta.cgi no devolvió JSON válido",
                    "preview": r.text[:300],
                }, status=status.HTTP_200_OK)

            def is_invalid_airmax_signal(station):
                airmax = station.get("airmax") or {}

                airmax_signal = airmax.get("signal")
                airmax_quality = airmax.get("quality")
                airmax_capacity = airmax.get("capacity")

                try:
                    signal_invalid = float(airmax_signal) == 0
                except (TypeError, ValueError):
                    signal_invalid = True

                try:
                    quality_invalid = float(airmax_quality) == 0
                except (TypeError, ValueError):
                    quality_invalid = True

                try:
                    capacity_invalid = float(airmax_capacity) == 0
                except (TypeError, ValueError):
                    capacity_invalid = True

                return signal_invalid or quality_invalid or capacity_invalid

            total = len(stations)
            invalid_stations = []

            for station in stations:
                airmax = station.get("airmax") or {}

                if is_invalid_airmax_signal(station):
                    invalid_stations.append({
                        "mac": station.get("mac"),
                        "name": station.get("name"),
                        "lastip": station.get("lastip"),

                        # Velocidad TX/RX Mbps
                        "tx_rate": station.get("tx"),
                        "rx_rate": station.get("rx"),

                        # Señal general del AP
                        "signal": station.get("signal"),
                        "ccq": station.get("ccq"),

                        # Datos clave para detectar TX Signal = "-"
                        "airmax_signal": airmax.get("signal"),
                        "airmax_quality": airmax.get("quality"),
                        "airmax_capacity": airmax.get("capacity"),
                    })

            invalid_count = len(invalid_stations)
            invalid_percent = round((invalid_count / total) * 100, 2) if total else 0

            should_reboot = total > 0 and invalid_percent >= 80

            return Response({
                "ok": True,
                "ip": ip,
                "endpoint": "sta.cgi",
                "total_stations": total,

                "invalid_airmax_count": invalid_count,
                "invalid_airmax_percent": invalid_percent,
                "threshold_percent": 80,
                "should_reboot": should_reboot,

                "criteria": {
                    "airmax_signal": "0, null o inválido",
                    "airmax_quality": "0, null o inválido",
                    "airmax_capacity": "0, null o inválido",
                    "logic": "si cualquiera de los 3 es inválido, la estación cuenta como falla",
                },

                "invalid_stations": invalid_stations,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "ok": False,
                "ip": ip,
                "stage": "error",
                "detail": str(e),
            }, status=status.HTTP_200_OK)




def fetch_airos_status_and_leases_https_with_session(
    ip: str,
    user: str,
    password: str,
) -> dict:
    """
    1) Abre login.cgi para setear cookies
    2) Postea credenciales
    3) Descarga status.cgi autenticado
    4) Si status.cgi fue exitoso, descarga leases.cgi con la misma sesión
    """

    s = make_relaxed_https_session()  # tu session con TLSRelaxAdapter (SECLEVEL=1)

    base = f"https://{ip}"

    # 1) warm up / cookies
    s.get(
        f"{base}/login.cgi",
        timeout=(3, 6),
        verify=False,
        allow_redirects=True,
    )

    # 2) login
    payloads = [
        {"username": user, "password": password},
        {"user": user, "password": password},
    ]

    logged_in = False
    last_preview = ""
    status_text = None

    for data in payloads:
        resp = s.post(
            f"{base}/login.cgi",
            data=data,
            timeout=(3, 6),
            verify=False,
            allow_redirects=True,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        last_preview = (resp.text or "")[:300]

        # Caso 1: login ya no devolvió HTML de login
        if not _is_login_html(resp.text):
            logged_in = True
            break

        # Caso 2: aunque login devuelva HTML, puede haber dejado cookie válida
        test = s.get(
            f"{base}/status.cgi",
            timeout=(3, 6),
            verify=False,
            allow_redirects=True,
        )

        if not _is_login_html(test.text) and test.status_code == 200:
            logged_in = True
            status_text = test.text
            break

    if not logged_in:
        return {
            "ok": False,
            "stage": "login_failed",
            "status_raw": f"__LOGIN_FAILED_HTML__\n{last_preview}",
            "leases_raw": None,
        }

    # 3) status.cgi autenticado
    if status_text is None:
        r_status = s.get(
            f"{base}/status.cgi",
            timeout=(3, 6),
            verify=False,
            allow_redirects=True,
            headers={
                "Accept": "text/plain, application/json, */*",
            },
        )
        r_status.raise_for_status()
        status_text = r_status.text

    if _is_login_html(status_text):
        return {
            "ok": False,
            "stage": "status_returned_login",
            "status_raw": status_text,
            "leases_raw": None,
        }

    # 4) leases.cgi con la misma sesión
    leases_text = None
    leases_error = None

    try:
        r_leases = s.get(
            f"{base}/leases.cgi",
            timeout=(3, 6),
            verify=False,
            allow_redirects=True,
            headers={
                "Accept": "text/plain, application/json, */*",
            },
        )

        r_leases.raise_for_status()
        leases_text = r_leases.text

        if _is_login_html(leases_text):
            leases_error = "leases.cgi devolvió HTML de login."
            leases_text = None

    except Exception as e:
        leases_error = f"No se pudo consultar leases.cgi: {e}"

    return {
        "ok": True,
        "stage": "success",
        "status_raw": status_text,
        "leases_raw": leases_text,
        "leases_error": leases_error,
    }
def _try_airOS_status_https(ip: str, user: str, password: str) -> dict:
    print("Consultando airOS HTTPS:", ip)

    try:
        result = fetch_airos_status_and_leases_https_with_session(
            ip=ip,
            user=user,
            password=password,
        )

        if not result.get("ok"):
            raw_status = result.get("status_raw") or ""

            return {
                "ok": False,
                "stage": result.get("stage", "login_failed"),
                "message": "No se pudo iniciar sesión o status.cgi devolvió login.",
                "raw_preview": raw_status[:400].replace("\n", "\\n"),
            }

        raw_status_text = result.get("status_raw") or ""
        raw_leases_text = result.get("leases_raw")
        leases_error = result.get("leases_error")

        print("Respuesta status.cgi:")
        print(raw_status_text)
        print(raw_leases_text,"hola")
        parsed = parse_airos_smart(raw_status_text)
        normalized = normalize_airos(parsed)

        leases = None

        if raw_leases_text:
            print("Respuesta leases.cgi:")
            print(raw_leases_text)

            try:
                leases = parse_airos_smart(raw_leases_text)
            except Exception as e:
                leases_error = f"No se pudo parsear leases.cgi: {e}"

        return {
            "ok": True,
            "transport": "https",
            "source": "status.cgi",
            "normalized": normalized,
            "leases": leases,
            "leases_error": leases_error,
        }

    except requests.exceptions.SSLError as e:
        return {
            "ok": False,
            "stage": "ssl",
            "message": f"SSL error: {e}",
        }

    except Exception as e:
        return {
            "ok": False,
            "stage": "unknown",
            "message": f"Error: {e}",
        }

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def extract_disable_net_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", {"name": "disableNet"})

    if not select:
        return None

    selected = select.find("option", selected=True)

    if selected:
        return selected.get("value")

    return None


def build_network_payload_for_disable_lan(html: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")

    disable_select = soup.find("select", {"name": "disableNet"})

    if not disable_select:
        raise Exception("No se encontró el select name='disableNet'.")

    form = disable_select.find_parent("form")

    if not form:
        raise Exception("El select disableNet no está dentro de un form.")

    form_action = form.get("action") or "network.cgi"
    post_url = urljoin(page_url, form_action)

    payload = {}

    for tag in form.find_all(["input", "select", "textarea", "button"]):
        name = tag.get("name")

        if not name:
            continue

        if tag.has_attr("disabled"):
            continue

        if tag.name == "input":
            input_type = (tag.get("type") or "").lower()

            if input_type in ["button", "reset"]:
                continue

            if input_type == "submit":
                payload[name] = tag.get("value", "")
                continue

            if input_type in ["checkbox", "radio"]:
                if tag.has_attr("checked"):
                    payload[name] = tag.get("value", "1")
                continue

            payload[name] = tag.get("value", "")

        elif tag.name == "select":
            selected = tag.find("option", selected=True)

            if selected:
                payload[name] = selected.get("value", "")
            else:
                first = tag.find("option")
                payload[name] = first.get("value", "") if first else ""

        elif tag.name == "textarea":
            payload[name] = tag.text or ""

        elif tag.name == "button":
            button_type = (tag.get("type") or "").lower()

            if button_type in ["submit", ""]:
                payload[name] = tag.get("value", "")

    payload["disableNet"] = "eth0"

    return post_url, payload
def replace_config_value(config_text: str, key: str, value: str) -> str:
    lines = config_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result = []
    found = False

    for line in lines:
        if line.startswith(f"{key}="):
            result.append(f"{key}={value}")
            found = True
        elif line.strip():
            result.append(line)

    if not found:
        result.append(f"{key}={value}")

    return "\n".join(result) + "\n"

class ToggleAirosLanAPIView(APIView):
    def post(self, request, pk=None):
        ip = request.data.get("ip")
        user = request.data.get("user", "ubnt")
        password = request.data.get("password", "ubnt2")
        is_plugged = request.data.get("is_plugged")
        if not ip:
            return Response(
                {"ok": False, "message": "Falta la IP del equipo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            s = login_airos_session(ip, user, password)
            base = f"https://{ip}"

            r_get = s.get(
                f"{base}/network.cgi",
                timeout=(3, 6),
                verify=False,
                allow_redirects=True,
            )
            r_get.raise_for_status()

            soup = BeautifulSoup(r_get.text, "html.parser")
            token_input = soup.find("input", {"name": "token"})
            token = token_input.get("value") if token_input else None

            if not token:
                return Response(
                    {"ok": False, "message": "No se encontró token en network.cgi."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            if is_plugged:
              network_data = replace_config_value(
                AIROS_FULL_NETWORK_DATA,
                "netconf.2.up",
                "disabled",
            )
            else:
                       network_data = replace_config_value(
                AIROS_FULL_NETWORK_DATA,
                "netconf.2.up",
                "disabled",
            )
             

            payload = {
                "token": token,
                "netmode": "router",
                "disableNet": "eth0",
                "cfgmode": "advancedMode",
                "network_data": network_data,
            }

            print("=== ENVIANDO NETWORK FULL DATA ===")
            print("token:", token)
            print("netmode:", payload["netmode"])
            print("disableNet:", payload["disableNet"])
            print("netconf.2.up:", "disabled")
            print("network_data length:", len(network_data))

            r_post = s.post(
                f"{base}/network.cgi",
                data=payload,
                timeout=(3, 10),
                verify=False,
                allow_redirects=False,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{base}/network.cgi",
                    "Origin": base,
                    "Accept": "*/*",
                },
            )
            r_post.raise_for_status()

            print("POST network.cgi:", r_post.status_code)
            print("POST preview:", (r_post.text or "")[:500])

            try:
                r_apply = s.get(
                    f"{base}/apply.cgi",
                    params={"testmode": ""},
                    timeout=(3, 10),
                    verify=False,
                    allow_redirects=False,
                    headers={
                        "Referer": f"{base}/network.cgi",
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "*/*",
                    },
                )

                apply_result = {
                    "called": True,
                    "status_code": r_apply.status_code,
                    "error": None,
                    "preview": (r_apply.text or "")[:300].replace("\n", "\\n"),
                }

            except Exception as apply_error:
                apply_result = {
                    "called": True,
                    "status_code": None,
                    "error": str(apply_error),
                }

            return Response(
                {
                    "ok": True,
                    "message": "Formulario completo enviado para desactivar LAN.",
                    "ip": ip,
                    "disableNet": "eth0",
                    "netconf_2_up": "disabled",
                    "network_post_status": r_post.status_code,
                    "apply": apply_result,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"ok": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
AIROS_FULL_NETWORK_DATA = """aaa.1.status=disabled
aaa.1.wpa.psk=Crystal9108..
aaa.status=disabled
bridge.status=disabled
dhcp6c.status=disabled
dhcp6d.status=disabled
dhcpc.status=enabled
dhcpc.1.devname=ath0
dhcpc.1.fallback=192.168.100.17
dhcpc.1.fallback_netmask=255.255.255.0
dhcpc.1.status=disabled
dhcpd.status=enabled
dhcpd.1.status=enabled
dhcpd.1.dns.1.server=8.8.8.8
dhcpd.1.dns.1.status=enabled
dhcpd.1.dns.2.server=8.8.4.4
dhcpd.1.dns.2.status=enabled
dhcpd.1.devname=eth0
dhcpd.1.dnsproxy=disabled
dhcpd.1.end=192.168.1.254
dhcpd.1.lease_time=600
dhcpd.1.netmask=255.255.255.0
dhcpd.1.start=192.168.1.2
dnsmasq.status=disabled
ebtables.status=disabled
ebtables.sys.status=disabled
ebtables.sys.vlan.status=disabled
httpd.https.port=443
httpd.https.status=enabled
httpd.status=enabled
ip6tables.status=disabled
ip6tables.sys.mgmt.1.devname=ath0
ip6tables.sys.mgmt.1.status=disabled
ip6tables.sys.mgmt.status=disabled
iptables.status=enabled
iptables.sys.dmz.status=disabled
iptables.sys.masq.status=enabled
iptables.sys.masq.1.devname=ath0
iptables.sys.masq.1.status=enabled
iptables.sys.mgmt.1.devname=ath0
iptables.sys.mgmt.1.status=disabled
iptables.sys.mgmt.status=disabled
iptables.sys.portfw.status=disabled
iptables.sys.status=enabled
iptables.sys.upnpd.status=disabled
iptables.sys.upnpd.devname=
netconf.status=enabled
netconf.1.status=enabled
netconf.1.devname=ath0
netconf.1.mtu=1500
netconf.1.role=wan
netconf.1.autoip.status=disabled
netconf.1.hwaddr.status=disabled
netconf.1.hwaddr.mac=
netconf.1.ip=192.168.100.17
netconf.1.netmask=255.255.255.0
netconf.1.promisc=enabled
netconf.1.up=enabled
netconf.2.status=enabled
netconf.2.devname=eth0
netconf.2.mtu=1500
netconf.2.role=lan
netconf.2.autoip.status=disabled
netconf.2.hwaddr.status=disabled
netconf.2.hwaddr.mac=
netconf.2.ip6.1.status=disabled
netconf.2.ip6.1.addr=
netconf.2.ip6.1.netmask=64
netconf.2.ip=192.168.1.1
netconf.2.netmask=255.255.255.0
netconf.2.promisc=enabled
netconf.2.up=enabled
netconf.3.status=disabled
netconf.3.devname=ath0
netconf.3.mtu=1500
netconf.3.role=mlan
netconf.3.autoip.status=disabled
netconf.3.hwaddr.status=disabled
netconf.3.hwaddr.mac=
netconf.3.up=enabled
netmode=router
ppp.status=disabled
radio.1.ack.auto=enabled
radio.1.ackdistance=600
radio.1.acktimeout=25
radio.1.antenna.gain=3
radio.1.antenna.id=1
radio.1.cable.loss=0
radio.1.chanbw=40
radio.1.countrycode=484
radio.1.cwm.enable=0
radio.1.cwm.mode=1
radio.1.devname=ath0
radio.1.dfs.status=enabled
radio.1.forbiasauto=0
radio.1.ieee_mode=11naht40
radio.1.mcastrate=0
radio.1.mode=managed
radio.1.obey=enabled
radio.1.polling=enabled
radio.1.pollingnoack=0
radio.1.pollingpri=
radio.1.rate.auto=enabled
radio.1.rate.mcs=7
radio.1.reg_obey=enabled
radio.1.status=enabled
radio.1.subsystemid=0xe865
radio.1.txpower=25
radio.countrycode=484
radio.countrylicense=0
radio.rate_module=atheros
radio.status=enabled
resolv.status=disabled
resolv.nameserver.1.ip=8.8.8.8
resolv.nameserver.1.status=enabled
resolv.nameserver.2.ip=8.8.4.4
resolv.nameserver.2.status=enabled
resolv.nameserver.3.ip=
resolv.nameserver.3.status=disabled
resolv.nameserver.4.ip=
resolv.nameserver.4.status=disabled
resolv.nameserver.status=enabled
route.status=enabled
route.1.ip=0.0.0.0
route.1.netmask=0
route.1.gateway=192.168.100.1
route.1.comment=
route.1.status=enabled
route.1.devname=ath0
route6.status=enabled
route6.1.ip=
route6.1.netmask=
route6.1.gateway=
route6.1.comment=
route6.1.status=disabled
sshd.port=22
sshd.status=enabled
system.cfg.version=65546
system.eirp.status=disabled
system.modules.blacklist.status=disabled
upnpd.status=disabled
upnpd.devname=
users.1.name=ubnt
users.1.password=$1$fNx7tTug$qiYOthKg4unGzCKERv8rv/
users.1.status=enabled
users.status=enabled
vlan.status=disabled
wireless.1.addmtikie=enabled
wireless.1.ap=
wireless.1.authmode=1
wireless.1.devname=ath0
wireless.1.hide_ssid=disabled
wireless.1.scan_list.channels=
wireless.1.scan_list.status=disabled
wireless.1.security.type=none
wireless.1.ssid=Totalplay-5G-d398
wireless.1.status=enabled
wireless.1.wds.status=disabled
wireless.hideindoor.status=disabled
wireless.status=enabled
wpasupplicant.device.1.devname=ath0
wpasupplicant.device.1.driver=madwifi
wpasupplicant.device.1.profile=WPA-PSK
wpasupplicant.device.1.status=enabled
wpasupplicant.profile.1.name=WPA-PSK
wpasupplicant.profile.1.network.1.bssid=
wpasupplicant.profile.1.network.1.eap.1.status=disabled
wpasupplicant.profile.1.network.1.key_mgmt.1.name=WPA-PSK
wpasupplicant.profile.1.network.1.pairwise.1.name=CCMP
wpasupplicant.profile.1.network.1.proto.1.name=RSN
wpasupplicant.profile.1.network.1.psk=Crystal9108..
wpasupplicant.profile.1.network.1.ssid=Totalplay-5G-d398
wpasupplicant.status=enabled
"""






class tokenObteinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("tokenExpo")

        if not token:
            return Response(
                {
                    "ok": False,
                    "message": "Falta el token de Expo",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        token_obj, created = tokenExpo.objects.update_or_create(
            id_user=request.user,
            defaults={
                "token": token,
            },
        )

        return Response(
            {
                "ok": True,
                "created": created,
                "token": token_obj.token,
            },
            status=status.HTTP_200_OK,
        )