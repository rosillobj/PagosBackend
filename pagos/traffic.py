"""Background, read-only traffic measurements on the main MikroTik."""
import json
import logging
import os
import time
from ipaddress import IPv4Address
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.core import signing
from librouteros import connect
from redis import Redis
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cliente
from .traffic_metrics import average, counters, select_queue

logger = logging.getLogger(__name__)
TTL = 300
SALT = 'traffic-measurement'


def storage():
    return Redis.from_url(settings.CELERY_RESULT_BACKEND, socket_timeout=3,
                          socket_connect_timeout=3, decode_responses=True)


def result_key(job):
    return f'traffic:result:{job}'


def release(store, key, job):
    store.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, key, job)


@shared_task(name='pagos.measure_client_traffic', soft_time_limit=65, time_limit=75, ignore_result=True)
def measure_client_traffic(job, client_id, ip):
    store = storage()
    lock = f'traffic:lock:{client_id}'
    api = None
    try:
        if store.get(lock) != job:
            return
        store.setex(result_key(job), TTL, json.dumps({'state': 'running'}))
        password = os.environ.get('MIKROTIK_API_PASSWORD')
        if not password:
            raise ValueError('Falta configurar MIKROTIK_API_PASSWORD en el worker.')
        api = connect(host=os.environ.get('MIKROTIK_API_HOST', '192.168.1.2'),
                      username=os.environ.get('MIKROTIK_API_USER', 'admin'),
                      password=password, port=int(os.environ.get('MIKROTIK_API_PORT', '8728')),
                      timeout=5)

        def read():
            return select_queue(list(api('/queue/simple/print', stats='',
                **{'.proplist': '.id,name,target,disabled,bytes'})), ip)

        first = read()
        before = counters(first)
        started = time.monotonic()
        time.sleep(30)
        last = read()
        elapsed = time.monotonic() - started
        if first['.id'] != last['.id'] or first.get('name') != last.get('name'):
            raise ValueError('La cola cambió durante la medición. Intenta nuevamente.')
        payload = {'state': 'completed', 'ip': ip, 'queue_name': last.get('name'),
                   **average(before, counters(last), elapsed)}
    except ValueError as exc:
        payload = {'state': 'failed', 'detail': str(exc)}
    except Exception:
        logger.exception('Traffic measurement failed for client %s', client_id)
        payload = {'state': 'failed', 'detail': 'No se pudo completar la lectura del MikroTik. Revisa la conexión y los permisos.'}
    finally:
        if api is not None:
            try:
                api.close()
            except Exception:
                logger.warning('Unable to close RouterOS connection')
        release(store, lock, job)
    store.setex(result_key(job), TTL, json.dumps(payload))


class StartTrafficMeasurement(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        client = Cliente.objects.filter(pk=pk).first()
        if client is None:
            return Response({'detail': 'Cliente no encontrado.'}, status=404)
        try:
            ip = str(IPv4Address((client.ip_completa or '').strip()))
        except ValueError:
            return Response({'detail': 'El cliente no tiene una IPv4 válida.'}, status=400)
        job = str(uuid4())
        lock = f'traffic:lock:{pk}'
        store = storage()
        try:
            if not store.set(lock, job, nx=True, ex=120):
                return Response({'detail': 'Ya hay una medición en curso para este cliente.'}, status=409)
            store.setex(result_key(job), TTL, json.dumps({'state': 'pending'}))
            measure_client_traffic.apply_async(args=[job, pk, ip], expires=60, retry=False)
        except Exception:
            try:
                release(store, lock, job)
            except Exception:
                pass
            return Response({'detail': 'El servicio de medición no está disponible.'}, status=503)
        token = signing.dumps({'job': job, 'user': request.user.pk}, salt=SALT)
        return Response({'measurement_id': token, 'duration_seconds': 30}, status=202)


class TrafficMeasurementResult(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=SALT, max_age=TTL)
            if data['user'] != request.user.pk:
                return Response({'detail': 'Medición no encontrada.'}, status=404)
        except signing.BadSignature:
            return Response({'detail': 'La medición expiró o es inválida.'}, status=404)
        try:
            raw = storage().get(result_key(data['job']))
        except Exception:
            return Response({'detail': 'No se pudo consultar la medición.'}, status=503)
        if raw is None:
            return Response({'detail': 'La medición expiró.'}, status=404)
        return Response(json.loads(raw))
