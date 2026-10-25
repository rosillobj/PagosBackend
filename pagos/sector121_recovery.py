"""Bounded recovery of one known Rocket M2. No Django or Celery imports."""
from dataclasses import dataclass
import hashlib
import hmac
import re
import socket
import time
from pathlib import Path

SECTOR_IP = '192.168.1.121'
DEFAULT_IP = '192.168.1.20'
EXPECTED_MAC = 'B4FBE45A0E0D'
OPERATION_LOCK = 'sector121:operation-lock'
REMOTE_BACKUP = '/tmp/sector121-restore.cfg'


class RecoveryError(Exception):
    """Public, credential-free failure reason."""


class IdentityError(RecoveryError):
    """Never retry a different device or changed SSH key automatically."""


def mac_value(value):
    return re.sub(r'[^0-9A-F]', '', str(value).upper())


def properties(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"')
    return result


def validate_backup(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise RecoveryError('Falta el respaldo del sector 121 o supera 1 MB.')
    data = path.read_bytes()
    try:
        fields = properties(data.decode('utf-8-sig'))
    except UnicodeDecodeError:
        raise RecoveryError('El respaldo no es una configuración de texto airOS.') from None
    addresses = [v for k, v in fields.items() if re.fullmatch(r'netconf\.\d+\.ip', k)]
    if SECTOR_IP not in addresses:
        raise RecoveryError('El respaldo no contiene una interfaz con IP 192.168.1.121.')
    if fields.get('board.sysid', '0xe868').lower() not in ('0xe868', 'e868'):
        raise RecoveryError('El respaldo declara otro modelo de antena.')
    if 'board.hwaddr' in fields and mac_value(fields['board.hwaddr']) != EXPECTED_MAC:
        raise RecoveryError('El respaldo declara una MAC distinta a la del sector 121.')
    if not any(k.startswith('wireless.') for k in fields):
        raise RecoveryError('El respaldo no contiene configuración inalámbrica.')
    return data


@dataclass(frozen=True)
class RecoveryConfig:
    backup_path: str
    default_user: str = 'ubnt'
    default_password: str = 'ubnt'
    restored_user: str = 'ubnt'
    restored_password: str = ''
    prepare_ct: bool = False
    return_timeout: float = 30
    final_timeout: float = 60


class AirOSSSH:
    """Password SSH with legacy RSA support scoped to this connection.

    The first host key is enrolled only AFTER authenticated board/MAC checks.
    Subsequent connections during the recovery must have that same host key.
    No SFTP subsystem is required by the cat/stdin upload.
    """
    def __init__(self, ip, username, password, timeout=5, expected_key=None, deadline=None):
        import paramiko
        self.transport = None
        self.timeout = timeout
        self.deadline = deadline
        connection = socket.create_connection((ip, 22), timeout=self.remaining())
        try:
            self.transport = paramiko.Transport(connection)
            self.transport.banner_timeout = self.remaining()
            self.transport.auth_timeout = self.remaining()
            self.transport.start_client(timeout=self.remaining())
            self.host_key = self.transport.get_remote_server_key().asbytes()
            if expected_key is not None and not hmac.compare_digest(self.host_key, expected_key):
                raise IdentityError('Cambió la clave SSH durante la recuperación. Se detuvo la operación.')
            self.transport.auth_timeout = self.remaining()
            self.transport.auth_password(username, password)
            self.verify_identity()
        except Exception:
            if self.transport is not None:
                self.transport.close()
            connection.close()
            raise

    def remaining(self):
        remaining = self.timeout if self.deadline is None else min(self.timeout, self.deadline - time.monotonic())
        if remaining <= 0:
            raise RecoveryError('Se agotó el plazo de regreso de la antena.')
        return remaining

    def run(self, command, content=None, timeout=None):
        limit = self.remaining() if timeout is None else timeout
        if self.deadline is not None:
            limit = min(limit, self.remaining())
        deadline = time.monotonic() + limit
        channel = self.transport.open_session(timeout=limit)
        channel.settimeout(max(0.01, deadline - time.monotonic()))
        channel.set_combine_stderr(True)
        output = bytearray()
        try:
            channel.exec_command(command)
            if content is not None:
                channel.sendall(content)
            channel.shutdown_write()
            while True:
                if time.monotonic() >= deadline:
                    raise RecoveryError('El comando SSH agotó el tiempo de espera.')
                if channel.recv_ready():
                    output.extend(channel.recv(32768))
                    if len(output) > 1024 * 1024:
                        raise RecoveryError('La respuesta SSH superó el límite de tamaño.')
                elif channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.02)
            status = channel.recv_exit_status()
            if status != 0:
                raise RecoveryError('La antena rechazó un comando SSH; no se continuó.')
            return output.decode('utf-8', errors='strict')
        finally:
            channel.close()

    def verify_identity(self):
        fields = properties(self.run('cat /etc/board.info'))
        if mac_value(fields.get('board.hwaddr', '')) != EXPECTED_MAC:
            raise IdentityError('La IP responde, pero la MAC no es la del sector 121. No se modificó ese equipo.')
        if fields.get('board.name') != 'Rocket M2' or fields.get('board.sysid', '').lower() != '0xe868':
            raise IdentityError('El modelo de la antena no corresponde a la Rocket M2 esperada.')
        version = self.run('cat /etc/version').strip()
        if not re.match(r'^XW(?:\.[A-Za-z0-9_-]+)*\.v6\.', version):
            raise IdentityError('La versión airOS no es XW 6.x. Se requiere revisión manual.')

    def boot_id(self):
        value = self.run('cat /proc/sys/kernel/random/boot_id').strip()
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', value):
            raise RecoveryError('No fue posible identificar el arranque de la antena.')
        return value

    def preflight(self, prepare_ct):
        commands = 'command -v cfgmtd >/dev/null && command -v md5sum >/dev/null && command -v reboot >/dev/null'
        if prepare_ct:
            commands += ' && command -v save >/dev/null && test -d /etc/persistent'
        self.run(commands)

    def ct_prepared(self):
        return self.run('if test -f /etc/persistent/ct; then printf yes; else printf no; fi') == 'yes'

    def prepare(self):
        self.run('touch /etc/persistent/ct && save', timeout=20)

    def upload(self, data):
        self.run(f'umask 077; cat > {REMOTE_BACKUP}', content=data, timeout=10)
        checksum = self.run(f'md5sum {REMOTE_BACKUP}').split()[0]
        expected = hashlib.md5(data, usedforsecurity=False).hexdigest()
        if not hmac.compare_digest(checksum, expected):
            raise RecoveryError('La copia del respaldo no coincide; no se escribió en flash.')

    def apply(self):
        # Preserve /etc/persistent, including ct and SSH keys, in the same write.
        self.run(f'cfgmtd -f {REMOTE_BACKUP} -w -p /etc/', timeout=30)

    def reboot(self):
        channel = self.transport.open_session(timeout=self.remaining())
        channel.settimeout(self.remaining())
        try:
            # exec_command waits for SSH's command acceptance, not for reboot completion.
            channel.exec_command('reboot')
        finally:
            channel.close()

    def close(self):
        self.transport.close()


class RecoveryRunner:
    def __init__(self, config, ping, connect=AirOSSSH, record=lambda **values: None,
                 before_attempt=lambda: True, preserve=lambda data: None,
                 clock=time.monotonic, sleep=time.sleep):
        self.config = config
        self.ping = ping
        self.connect = connect
        self.record = record
        self.before_attempt = before_attempt
        self.preserve = preserve
        self.clock = clock
        self.sleep = sleep

    def wait_boot(self, ip, username, password, previous_boot, host_key, seconds):
        deadline = self.clock() + seconds
        while self.clock() < deadline:
            remaining = deadline - self.clock()
            if self.ping(ip, min(1, remaining)):
                remaining = deadline - self.clock()
                if remaining <= 0:
                    break
                session = None
                try:
                    session = self.connect(ip, username, password,
                                           timeout=min(3, remaining), expected_key=host_key, deadline=deadline)
                    boot = session.boot_id()
                    if boot != previous_boot and self.clock() <= deadline:
                        session.deadline = None
                        session.timeout = 10
                        return session
                except IdentityError:
                    if session is not None:
                        session.close()
                    raise
                except Exception:
                    pass  # TCP/SSH may still be starting after ICMP comes back.
                if session is not None:
                    session.close()
            remaining = deadline - self.clock()
            if remaining > 0:
                self.sleep(min(1, remaining))
        raise RecoveryError(f'La antena no regresó por SSH en {ip} dentro de {int(seconds)} segundos.')

    def recover(self, data=None):
        data = data if data is not None else validate_backup(self.config.backup_path)
        if not self.ping(DEFAULT_IP, 2):
            raise RecoveryError('El sector 121 no responde y tampoco se encontró 192.168.1.20.')
        session = None
        try:
            session = self.connect(DEFAULT_IP, self.config.default_user, self.config.default_password)
            needs_prepare = self.config.prepare_ct and not session.ct_prepared()
            session.preflight(needs_prepare)
            boot = session.boot_id()
            host_key = session.host_key
            # Preserve the reset device's config before any mutation (private Redis entry).
            self.preserve(session.run('cat /tmp/system.cfg'))
            if self.ping(SECTOR_IP, 2):
                return {'state': 'cancelled', 'detail': 'El sector 121 volvió antes de iniciar cambios.'}
            if not self.before_attempt():
                return {'state': 'cooldown', 'detail': 'Ya hubo un intento reciente; no se repitió.'}
            self.record(state='recovering', phase='Identidad y respaldo verificados')
            if needs_prepare:
                self.record(state='recovering', phase='Preparando /etc/persistent/ct y primer reinicio')
                session.prepare()
                session.reboot()
                session.close()
                session = None
                session = self.wait_boot(DEFAULT_IP, self.config.default_user, self.config.default_password,
                                         boot, host_key, self.config.return_timeout)
                boot = session.boot_id()
            # A late return of the normal sector cancels the restore to avoid duplicate IPs.
            if self.ping(SECTOR_IP, 2):
                return {'state': 'cancelled', 'detail': '192.168.1.121 volvió antes de restaurar; no se cargó el respaldo.'}
            self.record(state='recovering', phase='Transfiriendo y verificando el respaldo')
            session.upload(data)
            self.record(state='recovering', phase='Escribiendo configuración en flash')
            session.apply()
            self.record(state='recovering', phase='Respaldo aplicado; verificando regreso a 192.168.1.121')
            session.reboot()
            session.close()
            session = None
            session = self.wait_boot(SECTOR_IP, self.config.restored_user, self.config.restored_password,
                                     boot, host_key, self.config.final_timeout)
            return {'state': 'recovered', 'detail': 'Sector 121 recuperado: ping, SSH, MAC y nuevo arranque verificados.'}
        finally:
            if session is not None:
                session.close()
