"""Authenticated preview and background execution of queue name synchronization."""
import json
import logging
import os
from uuid import uuid4
from celery import shared_task
from django.core import signing
from librouteros import connect
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Cliente
from .queue_names import plan_names, apply_names
from .traffic import storage, release

logger = logging.getLogger(__name__)
SALT = 'queue-name-sync'
TTL = 600
LOCK = 'queue-name-sync:lock'


def router():
    password = os.environ.get('MIKROTIK_API_PASSWORD')
    if not password:
        raise ValueError('Falta configurar MIKROTIK_API_PASSWORD.')
    return connect(host=os.environ.get('MIKROTIK_API_HOST', '192.168.1.2'),
                   username=os.environ.get('MIKROTIK_API_USER', 'admin'), password=password,
                   port=int(os.environ.get('MIKROTIK_API_PORT', '8728')), timeout=5, encoding='UTF-8')


@shared_task(name='pagos.sync_queue_names', ignore_result=True, soft_time_limit=240, time_limit=270)
def sync_queue_names(job, changes):
    store = storage()
    key = f'queue-name-sync:result:{job}'
    if store.get(LOCK) != job:
        return
    api = None
    try:
        store.setex(key, TTL, json.dumps({'state': 'running'}))
        api = router()
        clients = list(Cliente.objects.values('id', 'nombre', 'ip_completa'))
        result = apply_names(api, changes, clients)
        payload = {'state': 'completed', **result}
    except Exception:
        logger.exception('Queue name synchronization failed')
        payload = {'state': 'failed', 'detail': 'La sincronización no terminó. Genera otra vista previa para comprobar qué nombres faltan.'}
    finally:
        if api is not None:
            try:
                api.close()
            except Exception:
                pass
    try:
        store.setex(key, TTL, json.dumps(payload))
    finally:
        release(store, LOCK, job)


class QueueNameSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        api = None
        try:
            api = router()
            plan = plan_names(list(Cliente.objects.values('id', 'nombre', 'ip_completa')),
                              list(api('/queue/simple/print')))
            plan_id = str(uuid4())
            storage().setex(f'queue-name-sync:plan:{plan_id}', TTL, json.dumps(plan['changes']))
            token = signing.dumps({'id': plan_id, 'user': request.user.pk}, salt=SALT)
            return Response({**plan, 'plan_token': token, 'router': os.environ.get('MIKROTIK_API_HOST', '192.168.1.2')})
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=503)
        except Exception:
            logger.exception('Cannot prepare queue name preview')
            return Response({'detail': 'No se pudo consultar el router o guardar la vista previa en Redis.'}, status=503)
        finally:
            if api is not None:
                try:
                    api.close()
                except Exception:
                    pass

    def post(self, request):
        try:
            token = signing.loads(request.data.get('plan_token', ''), salt=SALT, max_age=TTL)
            if token['user'] != request.user.pk:
                raise signing.BadSignature()
        except (signing.BadSignature, TypeError, KeyError):
            return Response({'detail': 'La vista previa es inválida o expiró. Vuelve a consultar.'}, status=400)
        store = None
        job = str(uuid4())
        try:
            store = storage()
            raw = store.get(f'queue-name-sync:plan:{token["id"]}')
            if raw is None:
                return Response({'detail': 'La vista previa expiró.'}, status=400)
            changes = json.loads(raw)
            if not changes:
                return Response({'detail': 'No hay nombres pendientes de sincronizar.'}, status=400)
            if not store.set(LOCK, job, nx=True, ex=330):
                return Response({'detail': 'Ya hay una sincronización en curso.'}, status=409)
            store.setex(f'queue-name-sync:result:{job}', TTL, json.dumps({'state': 'pending'}))
            sync_queue_names.apply_async(args=[job, changes], expires=30, retry=False)
        except Exception:
            logger.exception('Cannot enqueue queue name synchronization')
            if store is not None:
                try:
                    release(store, LOCK, job)
                except Exception:
                    pass
            return Response({'detail': 'No se pudo iniciar la sincronización. Revisa Redis y Celery.'}, status=503)
        job_token = signing.dumps({'id': job, 'user': request.user.pk}, salt=SALT)
        return Response({'job_token': job_token}, status=202)


class QueueNameSyncResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=SALT, max_age=TTL)
            if data['user'] != request.user.pk:
                raise signing.BadSignature()
        except (signing.BadSignature, TypeError, KeyError):
            return Response({'detail': 'Consulta inválida o expirada.'}, status=404)
        try:
            raw = storage().get(f'queue-name-sync:result:{data["id"]}')
            return Response(json.loads(raw)) if raw else Response({'detail': 'El resultado expiró.'}, status=404)
        except Exception:
            return Response({'detail': 'No se pudo consultar el resultado.'}, status=503)
