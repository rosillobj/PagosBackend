"""Local preflight only: no network requests, reboot, touch or flash write."""
import hashlib
import importlib.util
import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pagos.sector121_recovery import EXPECTED_MAC, RecoveryError, validate_backup
from pagos.sector121_tasks import recovery_config


class Command(BaseCommand):
    help = 'Verifica el respaldo y la configuración local de la recuperación 121, sin modificar antenas.'

    def handle(self, *args, **options):
        config = recovery_config()
        try:
            data = validate_backup(config.backup_path)
        except (RecoveryError, OSError) as exc:
            raise CommandError(f'No se pudo validar el respaldo: {exc}') from None
        if importlib.util.find_spec('paramiko') is None:
            raise CommandError('Falta instalar Paramiko en la imagen del worker.')
        try:
            user_id = int(os.environ.get('SECTOR121_NOTIFY_USER_ID', '1'))
            if user_id < 1:
                raise ValueError()
        except ValueError:
            raise CommandError('SECTOR121_NOTIFY_USER_ID debe ser un ID positivo.') from None
        self.stdout.write(f'Activada: {settings.SECTOR121_RECOVERY_ENABLED}')
        self.stdout.write(f'Respaldo legible: {config.backup_path}')
        self.stdout.write(f'Tamaño: {len(data)} bytes; SHA256: {hashlib.sha256(data).hexdigest()}')
        self.stdout.write(f'Rocket M2 XW; MAC esperada: {EXPECTED_MAC}; IP destino: 192.168.1.121')
        self.stdout.write(f'Preparación: /etc/persistent/ct; espera inicial: 30 s; verificación final: 60 s')
        self.stdout.write(f'Notificaciones: usuario {user_id}')
        self.stdout.write(self.style.SUCCESS('Validación local correcta. No se conectó ni modificó ninguna antena.'))
