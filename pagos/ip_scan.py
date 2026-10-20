"""On-demand background subnet inventory, authenticated and bounded to configured sectors."""
import json
import logging
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core import signing
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .ip_inventory import UBIQUITI_SECTORS, MIKROTIK_SECTORS, classify, valid_ip
from .models import Cliente
from .traffic import storage, release

logger = logging.getLogger(__name__)
TTL = 600
LOCK = 'ip-scan:network-lock'
SALT = 'ip-scan'


def ping_ip(ip):
    try:
        result = subprocess.run(['ping', '-n', '-c', '2', '-i', '0.2', '-W', '1', '-w', '2', ip],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                env={**os.environ, 'LC_ALL': 'C'}, timeout=3, check=False)
        received = re.search(r'(\d+)\s+(?:packets\s+)?received', result.stdout or '')
        answered = result.returncode == 0 or (received is not None and int(received.group(1)) > 0)
        return ip, 'reachable' if answered else 'no_response' if result.returncode == 1 else 'error'
    except (OSError, subprocess.TimeoutExpired):
        return ip, 'error'


def query_airos_peers(ip, user, password):
    # Share the same authenticated reader as SectorView, without re-querying the DB.
    from .views import fetch_airos_status_and_leases_https_with_session
    import requests
    try:
        data = fetch_airos_status_and_leases_https_with_session(ip, user, password, include_stations=True)
        if not data.get('ok'):
            return {'ok': False, 'stage': data.get('stage', 'login_failed'),
                    'message': 'El sector rechazó el inicio de sesión.'}
        if data.get('stations') is None:
            return {'ok': False, 'stage': 'stations',
                    'message': data.get('stations_error') or 'sta.cgi no devolvió una lista de asociaciones válida.'}
        peers = [{'mac': row.get('mac'), 'ip': row.get('ip'), 'name': row.get('name')} for row in data['stations']]
        return {'ok': True, 'peers': peers}
    except requests.exceptions.Timeout:
        return {'ok': False, 'stage': 'timeout', 'message': 'El sector agotó el tiempo de espera.'}
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        return {'ok': False, 'stage': 'http', 'message': f'El sector devolvió HTTP {code or "desconocido"}.'}
    except requests.exceptions.ConnectionError:
        return {'ok': False, 'stage': 'connection', 'message': 'El worker no pudo conectar por HTTPS con el sector.'}
    except Exception:
        logger.exception('Unexpected airOS inventory error on %s', ip)
        return {'ok': False, 'stage': 'unknown', 'message': 'Falló la consulta de asociaciones del sector.'}


def sector_peers(item):
    from .views import mt_connect
    from .antenna_credentials import sector_credentials, query_with_credentials
    family, number = item
    ip = f'192.168.1.{number}'
    connection = None
    try:
        if family == 'airos':
            result = query_with_credentials(query_airos_peers, ip, sector_credentials(number), 'airos')
            if not result.get('ok'):
                logger.warning('Cannot read sector %s: stage=%s', ip, result.get('stage'))
                return {'ip': ip, 'ok': False, 'peers': [], 'stage': result.get('stage'),
                        'detail': result.get('message') or 'No se pudo consultar el sector.'}
            peers = result['peers']
        else:
            connection = mt_connect(ip, 'admin', 'ubnt2')
            rows = list(connection('/interface/wireless/registration-table/print', stats=''))
            peers = [{'mac': row.get('mac-address'), 'ip': row.get('last-ip'), 'name': row.get('radio-name')} for row in rows]
        return {'ip': ip, 'ok': True, 'peers': peers, 'total': len(peers)}
    except Exception:
        logger.exception('Cannot read association list on sector %s', ip)
        return {'ip': ip, 'ok': False, 'peers': [], 'detail': 'No se pudo consultar el sector. Revisa los logs del worker.'}
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def router_arp():
    from .views import mt_connect
    connection = None
    try:
        password = os.environ.get('MIKROTIK_API_PASSWORD')
        if not password:
            return {}, False
        connection = mt_connect(os.environ.get('MIKROTIK_API_HOST', '192.168.1.2'),
                                os.environ.get('MIKROTIK_API_USER', 'admin'), password,
                                port=int(os.environ.get('MIKROTIK_API_PORT', '8728')))
        by_mac = {}
        for row in connection('/ip/arp/print'):
            mac = str(row.get('mac-address') or '').lower()
            ip = valid_ip(row.get('address'))
            if mac and ip:
                by_mac.setdefault(mac, set()).add(ip)
        return by_mac, True
    except Exception:
        logger.exception('Cannot read router ARP during IP inventory')
        return {}, False
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


@shared_task(name='pagos.scan_ip_inventory', ignore_result=True, soft_time_limit=240, time_limit=270)
def scan_ip_inventory(job, start, end):
    store = storage()
    key = f'ip-scan:result:{job}'
    if store.get(LOCK) != job:
        return
    try:
        store.setex(key, TTL, json.dumps({'state': 'running', 'phase': 'Consultando sectores y comprobando ping…'}))
        # Separate bounded pools allow ping and AP reads to run together.
        with ThreadPoolExecutor(max_workers=32) as ping_pool, ThreadPoolExecutor(max_workers=4) as sector_pool:
            pending_ping = ping_pool.map(ping_ip, [f'192.168.1.{number}' for number in range(start, end + 1)])
            sectors = list(sector_pool.map(sector_peers,
                [('airos', number) for number in UBIQUITI_SECTORS] + [('mikrotik', number) for number in MIKROTIK_SECTORS]))
            pings = dict(pending_ping)
        arp, arp_ok = router_arp()
        associated = set()
        unresolved = []
        for sector in sectors:
            for peer in sector['peers']:
                ip = valid_ip(peer.get('ip'))
                addresses = set(arp.get(str(peer.get('mac') or '').lower(), set()))
                if ip:
                    addresses.add(ip)
                associated.update(addresses)
                if not addresses:
                    unresolved.append({'sector': sector['ip'], 'mac': peer.get('mac')})
        complete = all(sector['ok'] for sector in sectors) and not unresolved and all(value != 'error' for value in pings.values())
        clients = list(Cliente.objects.values('id', 'nombre', 'ip_completa'))
        result = classify(start, end, clients, pings, associated, complete)
        result.update(sectores=[{k: v for k, v in sector.items() if k != 'peers'} for sector in sectors],
                      asociaciones_sin_ip=unresolved, arp_consultado=arp_ok,
                      consultado_en=timezone.now().isoformat(),
                      advertencia='Sin respuesta al ping no garantiza que una IP esté libre. Verifica antes de asignarla.')
        payload = {'state': 'completed', **result}
    except SoftTimeLimitExceeded:
        payload = {'state': 'failed', 'detail': 'La consulta excedió el tiempo permitido. Revisa el acceso a los sectores.'}
    except Exception:
        logger.exception('IP inventory failed')
        payload = {'state': 'failed', 'detail': 'No se pudo completar el inventario de IP.'}
    try:
        store.setex(key, TTL, json.dumps(payload))
    finally:
        release(store, LOCK, job)


class StartIpScanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Keep scan scope fixed; do not accept arbitrary network addresses.
        try:
            start = int(request.data.get('start', 21))
            end = int(request.data.get('end', 254))
            if not 21 <= start <= end <= 254:
                raise ValueError()
        except (TypeError, ValueError):
            return Response({'detail': 'Usa un rango entre 21 y 254.'}, status=400)
        store = None
        job = str(uuid4())
        try:
            store = storage()
            if not store.set(LOCK, job, nx=True, ex=300):
                return Response({'detail': 'Ya hay una consulta de red en curso. Intenta nuevamente al finalizar.'}, status=409)
            store.setex(f'ip-scan:result:{job}', TTL, json.dumps({'state': 'pending'}))
            scan_ip_inventory.apply_async(args=[job, start, end], expires=25, retry=False)
        except Exception:
            logger.exception('Unable to enqueue IP inventory')
            if store is not None:
                try:
                    release(store, LOCK, job)
                except Exception:
                    pass
            return Response({'detail': 'Redis o Celery no están disponibles para consultar la red.'}, status=503)
        token = signing.dumps({'job': job, 'user': request.user.pk}, salt=SALT)
        return Response({'scan_id': token}, status=202)


class IpScanResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=SALT, max_age=TTL)
            if data['user'] != request.user.pk:
                return Response({'detail': 'Consulta no encontrada.'}, status=404)
        except signing.BadSignature:
            return Response({'detail': 'La consulta expiró o es inválida.'}, status=404)
        try:
            raw = storage().get(f'ip-scan:result:{data["job"]}')
        except Exception:
            return Response({'detail': 'No se pudo consultar el resultado.'}, status=503)
        if raw is None:
            return Response({'detail': 'La consulta expiró.'}, status=404)
        return Response(json.loads(raw))
