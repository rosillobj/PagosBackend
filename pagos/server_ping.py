"""Authenticated, bounded background ping from the backend worker."""
import json
import logging
from uuid import uuid4
from celery import shared_task
from django.core import signing
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .ping_probe import normalize_address, run_probe
from .traffic import storage, release

logger = logging.getLogger(__name__)
SALT = 'server-ping'
LOCK = 'server-ping:lock'
TTL = 900


@shared_task(name='pagos.server_ping', ignore_result=True, soft_time_limit=35, time_limit=40)
def server_ping(job, address):
    store = storage()
    key = f'server-ping:result:{job}'
    if store.get(LOCK) != job:
        return
    try:
        store.setex(key, TTL, json.dumps({'state': 'running'}))
        result = run_probe(address)
        payload = {'state': 'completed', 'observed_at': timezone.now().isoformat(), **result}
    except Exception:
        logger.exception('Server ping failed')
        payload = {'state': 'failed', 'detail': 'No se pudo ejecutar ping. Revisa el worker, el comando ping y los permisos de red.'}
    try:
        store.setex(key, TTL, json.dumps(payload))
    finally:
        release(store, LOCK, job)


class StartServerPingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            address = normalize_address(request.data.get('address'))
        except (ValueError, TypeError):
            return Response({'detail': 'Escribe una dirección IPv4 o IPv6 válida de un equipo.'}, status=400)
        job = str(uuid4())
        store = None
        try:
            store = storage()
            if not store.set(LOCK, job, nx=True, ex=90):
                return Response({'detail': 'Ya hay un ping en curso. Espera a que termine.'}, status=409)
            store.setex(f'server-ping:result:{job}', TTL, json.dumps({'state': 'pending'}))
            server_ping.apply_async(args=[job, address], expires=30, retry=False)
        except Exception:
            logger.exception('Cannot enqueue server ping')
            if store is not None:
                try:
                    release(store, LOCK, job)
                except Exception:
                    pass
            return Response({'detail': 'No se pudo iniciar el ping. Revisa Redis y Celery.'}, status=503)
        token = signing.dumps({'id': job, 'user': request.user.pk}, salt=SALT)
        return Response({'ping_token': token}, status=202)


class ServerPingResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=SALT, max_age=TTL)
            if data['user'] != request.user.pk:
                raise signing.BadSignature()
        except (signing.BadSignature, TypeError, KeyError):
            return Response({'detail': 'Consulta inválida o expirada.'}, status=404)
        try:
            raw = storage().get(f'server-ping:result:{data["id"]}')
            return Response(json.loads(raw)) if raw else Response({'detail': 'La consulta expiró.'}, status=404)
        except Exception:
            return Response({'detail': 'No se pudo consultar el ping.'}, status=503)
