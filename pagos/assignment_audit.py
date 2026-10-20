"""Read-only background audit of customer assignments."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from celery import shared_task
from django.core import signing
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Cliente
from .assignment_report import build_audit
from .ip_inventory import UBIQUITI_SECTORS, MIKROTIK_SECTORS
from .ip_scan import sector_peers, router_arp
from .queue_name_sync import router
from .traffic import storage, release

logger = logging.getLogger(__name__)
SALT = 'assignment-audit'
LOCK = 'assignment-audit:lock'
TTL = 900


@shared_task(name='pagos.audit_assignments', ignore_result=True, soft_time_limit=240, time_limit=270)
def audit_assignments(job):
    store = storage()
    key = f'assignment-audit:result:{job}'
    if store.get(LOCK) != job:
        return
    try:
        store.setex(key, TTL, json.dumps({'state': 'running'}))
        with ThreadPoolExecutor(max_workers=4) as pool:
            sectors = list(pool.map(sector_peers,
                [('airos', n) for n in UBIQUITI_SECTORS] + [('mikrotik', n) for n in MIKROTIK_SECTORS]))
        arp, arp_ok = router_arp()
        queues, queues_ok = [], False
        api = None
        try:
            api = router()
            queues = list(api('/queue/simple/print'))
            queues_ok = True
        except Exception:
            logger.exception('Cannot read queues during assignment audit')
        finally:
            if api is not None:
                try:
                    api.close()
                except Exception:
                    pass
        clients = list(Cliente.objects.values('id', 'nombre', 'ip_completa'))
        report = build_audit(clients, sectors, arp, arp_ok, queues, queues_ok)
        payload = {'state': 'completed', 'observed_at': timezone.now().isoformat(), **report}
    except Exception:
        logger.exception('Assignment audit failed')
        payload = {'state': 'failed', 'detail': 'No se pudo completar la auditoría. Revisa los logs del worker.'}
    try:
        store.setex(key, TTL, json.dumps(payload))
    finally:
        release(store, LOCK, job)


class StartAssignmentAuditView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job = str(uuid4())
        store = None
        try:
            store = storage()
            if not store.set(LOCK, job, nx=True, ex=330):
                return Response({'detail': 'Ya hay una auditoría en curso. Espera a que termine.'}, status=409)
            store.setex(f'assignment-audit:result:{job}', TTL, json.dumps({'state': 'pending'}))
            audit_assignments.apply_async(args=[job], expires=30, retry=False)
        except Exception:
            logger.exception('Cannot enqueue assignment audit')
            if store is not None:
                try:
                    release(store, LOCK, job)
                except Exception:
                    pass
            return Response({'detail': 'No se pudo iniciar la auditoría. Revisa Redis y Celery.'}, status=503)
        token = signing.dumps({'id': job, 'user': request.user.pk}, salt=SALT)
        return Response({'audit_token': token}, status=202)


class AssignmentAuditResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=SALT, max_age=TTL)
            if data['user'] != request.user.pk:
                raise signing.BadSignature()
        except (signing.BadSignature, TypeError, KeyError):
            return Response({'detail': 'Auditoría inválida o expirada.'}, status=404)
        try:
            raw = storage().get(f'assignment-audit:result:{data["id"]}')
            return Response(json.loads(raw)) if raw else Response({'detail': 'La auditoría expiró.'}, status=404)
        except Exception:
            return Response({'detail': 'No se pudo consultar la auditoría.'}, status=503)
