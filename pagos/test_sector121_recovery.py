import ast
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from .sector121_recovery import (AirOSSSH, DEFAULT_IP, IdentityError, RecoveryConfig,
                                RecoveryError, RecoveryRunner, SECTOR_IP, validate_backup)

VALID = b'board.sysid=0xe868\nnetconf.2.ip=192.168.1.121\nwireless.1.ssid=sector121\n'


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class Device:
    def __init__(self):
        self.calls = []
        self.boot = 0
        self.ct = False
        self.applied = False
        self.default_online = True
        self.primary_back = False
        self.first_boot_timeout = False
        self.changed_key = False
        self.upload_error = False
        self.apply_error = False
        self.auth_error = False
        self.save_error = False
    def ping(self, ip, seconds):
        if ip == SECTOR_IP: return self.applied or self.primary_back
        return self.default_online and not (self.first_boot_timeout and self.boot == 1)
    def connect(self, ip, username, password, **kwargs):
        if self.auth_error: raise OSError('authentication failed')
        if self.changed_key and self.boot:
            raise IdentityError('changed key')
        self.calls.append(('connect', ip))
        return Session(self)


class Session:
    host_key = b'expected-ssh-key'
    def __init__(self, device): self.device = device
    def run(self, command):
        self.device.calls.append(('read', command))
        return 'factory_config=yes\n'
    def preflight(self, ct): self.device.calls.append(('preflight', ct))
    def ct_prepared(self): return self.device.ct
    def boot_id(self): return f'boot-{self.device.boot}'
    def prepare(self):
        self.device.calls.append(('prepare',))
        if self.device.save_error: raise RecoveryError('save failed')
        self.device.ct = True
    def reboot(self):
        self.device.calls.append(('reboot',))
        self.device.boot += 1
    def upload(self, data):
        self.device.calls.append(('upload', data))
        if self.device.upload_error: raise RecoveryError('checksum failed')
    def apply(self):
        self.device.calls.append(('apply',))
        if self.device.apply_error: raise RecoveryError('flash failed')
        self.device.applied = True
    def close(self): self.device.calls.append(('close',))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.device = Device()
        self.clock = Clock()
        self.status = []
        self.preserved = []
        self.runner = RecoveryRunner(
            RecoveryConfig('unused.cfg', prepare_ct=True, restored_password='test'),
            ping=self.device.ping, connect=self.device.connect,
            record=lambda **v: self.status.append(v), preserve=self.preserved.append,
            clock=self.clock, sleep=self.clock.sleep,
        )
    def actions(self): return [c[0] for c in self.device.calls]
    def test_complete_flow_verifies_both_reboots(self):
        self.assertEqual(self.runner.recover(VALID)['state'], 'recovered')
        self.assertEqual(self.actions().count('reboot'), 2)
        self.assertLess(self.actions().index('prepare'), self.actions().index('upload'))
        self.assertLess(self.actions().index('upload'), self.actions().index('apply'))
        self.assertEqual(self.preserved, ['factory_config=yes\n'])
        self.assertEqual(self.device.calls[-2], ('connect', SECTOR_IP))
    def test_first_reboot_can_take_forty_seconds(self):
        from dataclasses import replace
        self.runner.config = replace(self.runner.config, return_timeout=90, final_timeout=90)
        original_ping = self.device.ping
        def slow_boot(ip, seconds):
            if ip == DEFAULT_IP and self.device.boot == 1 and self.clock.now < 40:
                return False
            return original_ping(ip, seconds)
        self.runner.ping = slow_boot
        self.assertEqual(self.runner.recover(VALID)['state'], 'recovered')
        self.assertGreaterEqual(self.clock.now, 40)
    def test_default_not_found_never_connects_or_writes(self):
        self.device.default_online = False
        with self.assertRaises(RecoveryError): self.runner.recover(VALID)
        self.assertEqual(self.device.calls, [])
    def test_primary_returns_before_changes(self):
        self.device.primary_back = True
        self.assertEqual(self.runner.recover(VALID)['state'], 'cancelled')
        self.assertNotIn('prepare', self.actions())
        self.assertNotIn('upload', self.actions())
    def test_primary_returns_after_first_reboot_cancels_restore(self):
        original = self.device.ping
        self.runner.ping = lambda ip, seconds: (True if ip == SECTOR_IP and self.device.boot else original(ip, seconds))
        self.assertEqual(self.runner.recover(VALID)['state'], 'cancelled')
        self.assertNotIn('apply', self.actions())
    def test_first_boot_deadline_is_thirty_seconds(self):
        self.device.first_boot_timeout = True
        with self.assertRaises(RecoveryError): self.runner.recover(VALID)
        self.assertEqual(self.clock.now, 30)
        self.assertNotIn('upload', self.actions())
        self.assertEqual(self.actions().count('reboot'), 1)
    def test_upload_failure_never_writes_flash(self):
        self.device.upload_error = True
        with self.assertRaises(RecoveryError): self.runner.recover(VALID)
        self.assertNotIn('apply', self.actions())
    def test_failed_flash_never_sends_final_reboot(self):
        self.device.apply_error = True
        with self.assertRaises(RecoveryError): self.runner.recover(VALID)
        self.assertEqual(self.actions().count('reboot'), 1)
    def test_save_failure_never_reboots_or_restores(self):
        self.device.save_error = True
        with self.assertRaises(RecoveryError): self.runner.recover(VALID)
        self.assertNotIn('reboot', self.actions())
        self.assertNotIn('upload', self.actions())
    def test_preserving_config_failure_aborts_before_mutation(self):
        self.runner.preserve = Mock(side_effect=OSError('Redis unavailable'))
        with self.assertRaises(OSError): self.runner.recover(VALID)
        self.assertNotIn('prepare', self.actions())
    def test_authentication_failure_never_writes(self):
        self.device.auth_error = True
        with self.assertRaises(OSError): self.runner.recover(VALID)
        self.assertNotIn('prepare', self.actions())
    def test_changed_host_key_aborts_without_restore(self):
        self.device.changed_key = True
        with self.assertRaises(IdentityError): self.runner.recover(VALID)
        self.assertNotIn('upload', self.actions())
    def test_cooldown_never_mutates(self):
        self.runner.before_attempt = lambda: False
        self.assertEqual(self.runner.recover(VALID)['state'], 'cooldown')
        self.assertNotIn('prepare', self.actions())
        self.assertNotIn('upload', self.actions())
    def test_existing_ct_skips_redundant_first_reboot(self):
        self.device.ct = True
        self.assertEqual(self.runner.recover(VALID)['state'], 'recovered')
        self.assertNotIn('prepare', self.actions())
        self.assertEqual(self.actions().count('reboot'), 1)
    def test_ping_response_before_reboot_is_not_accepted(self):
        self.runner.connect = lambda *a, **k: Session(Device())
        with self.assertRaises(RecoveryError):
            self.runner.wait_boot(DEFAULT_IP, 'ubnt', 'test', 'boot-0', b'key', 30)
        self.assertEqual(self.clock.now, 30)
    def test_final_verification_required(self):
        original = self.device.ping
        self.runner.ping = lambda ip, seconds: False if ip == SECTOR_IP else original(ip, seconds)
        with self.assertRaises(RecoveryError): self.runner.recover(VALID)
        self.assertIn('apply', self.actions())
        self.assertEqual(self.clock.now, 60)


class BackupTests(unittest.TestCase):
    def check(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'backup.cfg'
            path.write_bytes(data)
            return validate_backup(path)
    def test_valid_backup_unchanged(self): self.assertEqual(self.check(VALID), VALID)
    def test_other_ip_rejected(self):
        with self.assertRaises(RecoveryError): self.check(VALID.replace(b'.121', b'.122'))
    def test_other_model_rejected(self):
        with self.assertRaises(RecoveryError): self.check(VALID.replace(b'0xe868', b'0x1234'))
    def test_other_mac_rejected(self):
        with self.assertRaises(RecoveryError): self.check(VALID + b'board.hwaddr=001122334455\n')
    def test_missing_wireless_rejected(self):
        with self.assertRaises(RecoveryError): self.check(b'netconf.1.ip=192.168.1.121\n')
    def test_binary_rejected(self):
        with self.assertRaises(RecoveryError): self.check(b'\xff\x00')
    def test_large_backup_rejected(self):
        with self.assertRaises(RecoveryError): self.check(b'A' * (1024 * 1024 + 1))


class SSHChecks(unittest.TestCase):
    def device(self, mac='B4FBE45A0E0D', model='Rocket M2', version='XW.v6.1.7'):
        ssh = object.__new__(AirOSSSH)
        ssh.run = Mock(side_effect=[f'board.hwaddr={mac}\nboard.name={model}\nboard.sysid=0xe868\n', version])
        return ssh
    def test_expected_identity(self): self.device().verify_identity()
    def test_architecture_in_version_string(self): self.device(version='XW.ar934x.v6.1.7.32555').verify_identity()
    def test_escaped_dot_in_device_firmware(self):
        self.device(version=r'XW\.v6.1.7').verify_identity()

    def test_prepare_persists_without_interactive_save(self):
        ssh = object.__new__(AirOSSSH)
        ssh.run = Mock()
        ssh.preflight(True)
        self.assertNotIn('command -v save', ssh.run.call_args.args[0])
        ssh.prepare()
        ssh.run.assert_called_with('touch /etc/persistent/ct && cfgmtd -w -p /etc/', timeout=20)

    def test_other_mac_never_accepted(self):
        with self.assertRaises(IdentityError): self.device(mac='001122334455').verify_identity()
    def test_other_model_never_accepted(self):
        with self.assertRaises(IdentityError): self.device(model='LiteBeam').verify_identity()
    def test_ac_firmware_never_accepted(self):
        with self.assertRaises(IdentityError): self.device(version='WA.v8.7.11').verify_identity()
    def test_remote_checksum_failure(self):
        ssh = object.__new__(AirOSSSH)
        ssh.run = Mock(side_effect=['', 'wronghash file'])
        with self.assertRaises(RecoveryError): ssh.upload(VALID)
    def test_remote_checksum_success(self):
        ssh = object.__new__(AirOSSSH)
        checksum = hashlib.md5(VALID, usedforsecurity=False).hexdigest()
        ssh.run = Mock(side_effect=['', checksum + ' file'])
        ssh.upload(VALID)


class PingTests(unittest.TestCase):
    def ping(self, code, output=''):
        # Load the actual pure ping function without Django/Celery imports.
        source = Path(__file__).with_name('sector121_tasks.py').read_text()
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sector_ping')
        import os, re
        runner = Mock(return_value=subprocess.CompletedProcess([], code, output))
        fake_subprocess = Mock(run=runner, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL,
                               TimeoutExpired=subprocess.TimeoutExpired)
        namespace = dict(subprocess=fake_subprocess, os=os, re=re, RecoveryError=RecoveryError)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<sector_ping>', 'exec'), namespace)
        return namespace['sector_ping'](SECTOR_IP)
    def test_permission_error_aborts_not_offline(self):
        with self.assertRaises(RecoveryError): self.ping(2)
    def test_no_response(self): self.assertFalse(self.ping(1, '2 packets transmitted, 0 received'))
    def test_one_response_is_online(self): self.assertTrue(self.ping(1, '2 packets transmitted, 1 received'))


class TaskCoordinationTests(unittest.TestCase):
    def setUp(self):
        import types
        self.store = Mock()
        self.store.set.return_value = True
        self.store.exists.return_value = False
        self.store.ttl.return_value = 120
        self.store.get.return_value = 'job'
        self.status = Mock()
        self.release = Mock()
        self.notify = Mock()
        self.ping = Mock(return_value=False)
        self.runner = Mock()
        self.runner.recover.return_value = {'state': 'recovered', 'detail': 'verified'}
        self.namespace = dict(
            settings=types.SimpleNamespace(SECTOR121_RECOVERY_ENABLED=True),
            storage=lambda: self.store, uuid4=lambda: 'job', OPERATION_LOCK='operation', LOCK_SECONDS=280,
            sector_ping=self.ping, SECTOR_IP=SECTOR_IP, DEFAULT_IP=DEFAULT_IP,
            ALERT='alert', COOLDOWN='cooldown', record_status=self.status,
            recovery_config=lambda: RecoveryConfig('fixture.cfg'), validate_backup=Mock(return_value=VALID),
            RecoveryRunner=Mock(return_value=self.runner), AirOSSSH=AirOSSSH,
            notify=self.notify, release=self.release, RecoveryError=RecoveryError,
            logger=Mock(), __package__=__package__,
        )
        source = Path(__file__).with_name('sector121_tasks.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'recover_sector121')
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<recover_sector121>', 'exec'), self.namespace)
        self.task = self.namespace['recover_sector121']
    def test_disabled_never_touches_redis_or_hardware(self):
        self.namespace['settings'].SECTOR121_RECOVERY_ENABLED = False
        self.assertEqual(self.task()['state'], 'disabled')
        self.store.set.assert_not_called()
        self.ping.assert_not_called()
    def test_busy_lock_never_probes_or_recovers(self):
        self.store.set.return_value = False
        self.assertEqual(self.task()['state'], 'busy')
        self.ping.assert_not_called()
        self.namespace['RecoveryRunner'].assert_not_called()
    def test_cooldown_never_repeats_mutation(self):
        self.store.exists.return_value = True
        self.assertEqual(self.task()['state'], 'cooldown')
        self.runner.recover.assert_not_called()
        self.release.assert_called_once_with(self.store, 'operation', 'job')
    def test_old_cooldown_is_shortened(self):
        self.store.exists.return_value = True
        self.store.ttl.return_value = 2154
        self.store.get.return_value = 'previous-job'
        self.assertEqual(self.task()['state'], 'cooldown')
        self.store.expire.assert_called_once_with('cooldown', 120)
    def test_failed_attempt_retries_two_minutes_after_completion(self):
        self.runner.recover.side_effect = RecoveryError('SSH timeout')
        self.assertEqual(self.task()['state'], 'failed')
        self.store.expire.assert_called_once_with('cooldown', 120)
    def test_success_keeps_long_cooldown(self):
        self.task()
        self.store.expire.assert_called_once_with('cooldown', 3600)
    def test_failed_backup_never_connects(self):
        self.namespace['validate_backup'].side_effect = RecoveryError('bad backup')
        self.assertEqual(self.task()['state'], 'failed')
        self.namespace['RecoveryRunner'].assert_not_called()
        self.release.assert_called_once()
    def test_success_records_and_notifies_then_releases(self):
        self.assertEqual(self.task()['state'], 'recovered')
        self.notify.assert_called_once_with(self.store, 'recovered', 'verified')
        self.release.assert_called_once()
    def test_unexpected_failure_still_releases_lock(self):
        self.runner.recover.side_effect = OSError('network problem')
        self.assertEqual(self.task()['state'], 'failed')
        self.release.assert_called_once()
    def test_healthy_during_cooldown_does_not_reboot_clients(self):
        self.ping.return_value = True
        self.store.exists.return_value = True
        self.assertEqual(self.task()['state'], 'healthy')
        self.runner.recover.assert_not_called()
    def test_healthy_calls_old_check_inside_same_lock(self):
        import sys, types
        name = __package__ + '.tasks'
        module = types.ModuleType(name)
        module._auto_reboot121_unlocked = Mock(return_value={'reboot': False})
        from unittest.mock import patch
        self.ping.return_value = True
        with patch.dict(sys.modules, {name: module}):
            self.assertEqual(self.task()['state'], 'healthy')
        module._auto_reboot121_unlocked.assert_called_once()
        self.runner.recover.assert_not_called()
        self.release.assert_called_once()


class ScheduleTests(unittest.TestCase):
    def schedule(self, enabled):
        import os
        from unittest.mock import patch
        path = Path(__file__).parents[1] / 'pagosNew/settings.py'
        tree = ast.parse(path.read_text())
        marker = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'SECTOR121_RECOVERY_ENABLED' for t in n.targets))
        namespace = dict(os=os, crontab=lambda **kwargs: kwargs,
                         CELERY_BEAT_SCHEDULE={'auto-reboot-sector-121': 'old', 'auto-reboot-sector-127': 'unchanged'})
        with patch.dict(os.environ, {'SECTOR121_RECOVERY_ENABLED': enabled}):
            exec(compile(ast.Module(body=tree.body[marker:], type_ignores=[]), '<schedule>', 'exec'), namespace)
        return namespace['CELERY_BEAT_SCHEDULE']
    def test_disabled_preserves_old_schedule(self):
        self.assertIn('auto-reboot-sector-121', self.schedule('false'))
    def test_enabled_has_one_coordinated_schedule(self):
        schedule = self.schedule('true')
        self.assertNotIn('auto-reboot-sector-121', schedule)
        self.assertEqual(schedule['auto-reboot-sector-127'], 'unchanged')
        self.assertEqual(schedule['recover-sector-121']['schedule'], 30.0)
        self.assertEqual(schedule['recover-sector-121']['options']['expires'], 25)


class NotificationScopeTests(unittest.TestCase):
    def send(self, user_id):
        source = Path(__file__).with_name('tasks.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'enviar_notificacion_expo')
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.values_list.return_value = ['test-token']
        model = Mock()
        model.objects.exclude.return_value = queryset
        requests = Mock()
        requests.RequestException = RuntimeError
        requests.post.return_value.json.return_value = {'data': [{'status': 'ok'}]}
        namespace = dict(tokenExpo=model, requests=requests, EXPO_PUSH_URL='https://example.invalid')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<push>', 'exec'), namespace)
        from unittest.mock import patch
        with patch('builtins.print'):
            result = namespace['enviar_notificacion_expo']('title', 'body', user_id=user_id)
        self.assertTrue(result['ok'])
        return queryset
    def test_recovery_can_target_admin_only(self):
        self.send(1).filter.assert_called_once_with(id_user_id=1)
    def test_existing_notifications_keep_their_scope(self):
        self.send(None).filter.assert_not_called()
