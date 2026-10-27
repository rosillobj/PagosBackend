"""Celery/Redis integration for the authorized sector 121 recovery."""
import logging
import os
import re
import subprocess
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .antenna_credentials import sector_credentials
from .sector121_recovery import (AirOSSSH, DEFAULT_IP, EXPECTED_MAC, OPERATION_LOCK,
                                 RecoveryConfig, RecoveryError, RecoveryRunner,
                                 SECTOR_IP, validate_backup)
from .traffic import release, storage

logger = logging.getLogger(__name__)
STATUS = 'sector121:recovery:status'
COOLDOWN = 'sector121:recovery:cooldown'
ALERT = 'sector121:recovery:last-alert'
LOCK_SECONDS = 280


def recovery_config():
    user, password = sector_credentials(121)
    return RecoveryConfig(
        backup_path=os.environ.get('SECTOR121_BACKUP_PATH', str(settings.BASE_DIR / 'Respaldo121' / 'XW-B4FBE45A0E0D.cfg')),
        default_user=os.environ.get('SECTOR121_DEFAULT_USER', 'ubnt'),
        default_password=os.environ.get('SECTOR121_DEFAULT_PASSWORD', 'ubnt'),
        restored_user=os.environ.get('SECTOR121_RESTORED_USER', user),
        restored_password=os.environ.get('SECTOR121_RESTORED_PASSWORD', password),
        prepare_ct=True,
        return_timeout=90,
        final_timeout=90,
    )


def sector_ping(ip, seconds=2):
    try:
        result = subprocess.run(['ping', '-n', '-c', '2', '-i', '0.2', '-W', '1', '-w', '1', ip],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                env={**os.environ, 'LC_ALL': 'C'},
                                timeout=max(0.1, seconds), check=False)
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        raise RecoveryError('El worker no pudo ejecutar ping.') from None
    if result.returncode not in (0, 1):
        raise RecoveryError('Ping falló por un error de ejecución o permisos; no se modificó ninguna antena.')
    received = re.search(r'(\d+)\s+(?:packets\s+)?received', result.stdout or '')
    return result.returncode == 0 or (received is not None and int(received[1]) > 0)


def record_status(store, **values):
    import json
    values.update(sector=SECTOR_IP, mac=EXPECTED_MAC, checked_at=timezone.now().isoformat())
    store.setex(STATUS, 7 * 86400, json.dumps(values))
    logger.info('Sector 121 recovery: state=%s phase=%s', values.get('state'), values.get('phase', ''))


def notify(store, code, detail):
    """Suppress repeated identical alerts; a different state is sent immediately."""
    if store.get(ALERT) == code:
        return
    try:
        from .tasks import enviar_notificacion_expo
        user_id = int(os.environ.get('SECTOR121_NOTIFY_USER_ID', '1'))
        result = enviar_notificacion_expo(
            title='Sector 121: ' + ('recuperado' if code == 'recovered' else 'revisión requerida'),
            body=detail,
            data={'type': 'sector121_recovery', 'state': code, 'sector': '121', 'ip': SECTOR_IP},
            user_id=user_id,
        )
        if result.get('ok'):
            store.setex(ALERT, 3600, code)
    except Exception:
        logger.exception('Cannot deliver sector 121 recovery notification')


def run_legacy_sector121():
    """Preserve the existing task when the new recovery feature is disabled."""
    store = storage()
    token = str(uuid4())
    if not store.set(OPERATION_LOCK, token, nx=True, ex=LOCK_SECONDS):
        return {'state': 'busy', 'sector': SECTOR_IP}
    try:
        from .tasks import _auto_reboot121_unlocked
        return _auto_reboot121_unlocked()
    finally:
        release(store, OPERATION_LOCK, token)


@shared_task(name='pagos.recover_sector121', ignore_result=True,
             soft_time_limit=230, time_limit=250)
def recover_sector121():
    if not settings.SECTOR121_RECOVERY_ENABLED:
        return {'state': 'disabled'}
    store = storage()
    token = str(uuid4())
    if not store.set(OPERATION_LOCK, token, nx=True, ex=LOCK_SECONDS):
        return {'state': 'busy'}
    try:
        if sector_ping(SECTOR_IP):
            store.delete(ALERT)
            record_status(store, state='healthy', phase='192.168.1.121 responde')
            # Avoid an immediate legacy reboot after a recovery attempt.
            if not store.exists(COOLDOWN) and store.set(
                    "sector121:legacy-check", token, nx=True, ex=300):
                from .tasks import _auto_reboot121_unlocked
                return {'state': 'healthy', 'legacy': _auto_reboot121_unlocked()}
            return {'state': 'healthy'}
        if store.exists(COOLDOWN):
            # Shorten cooldowns left by the previous one-hour retry policy.
            if store.ttl(COOLDOWN) > 120 or store.ttl(COOLDOWN) == -1:
                store.expire(COOLDOWN, 120)
            record_status(store, state='cooldown', phase='Sin ping; esperando antes de otro intento',
                          retry_in_seconds=store.ttl(COOLDOWN))
            return {'state': 'cooldown'}
        config = recovery_config()
        data = validate_backup(config.backup_path)
        record_status(store, state='checking', phase='Sin ping en .121; buscando el equipo en .20')
        runner = RecoveryRunner(
            config=config,
            ping=sector_ping,
            connect=AirOSSSH,
            record=lambda **values: record_status(store, **values),
            before_attempt=lambda: bool(store.set(COOLDOWN, token, nx=True, ex=3600)),
            # Private copy with no HTTP endpoint, retained for seven days.
            preserve=lambda content: store.setex(f'sector121:pre-restore:{token}', 7 * 86400, content),
        )
        result = runner.recover(data)
        record_status(store, **result)
        if result['state'] in ('recovered', 'cancelled'):
            notify(store, result['state'], result['detail'])
        return result
    except RecoveryError as exc:
        detail = str(exc)
        record_status(store, state='failed', detail=detail)
        notify(store, 'failed:' + detail, detail)
        return {'state': 'failed', 'detail': detail}
    except Exception:
        logger.exception('Sector 121 recovery failed')
        detail = 'No se pudo completar la recuperación del sector 121. Revisa el log del worker; se reintentará tras una pausa de dos minutos si ya se inició un cambio.'
        record_status(store, state='failed', detail=detail)
        notify(store, 'failed', detail)
        return {'state': 'failed', 'detail': detail}
    finally:
        if store.get(COOLDOWN) == token:
            # Cool down from completion, rather than from the start of a long attempt.
            store.expire(COOLDOWN, 3600 if locals().get('result', {}).get('state') == 'recovered' else 120)
        release(store, OPERATION_LOCK, token)
