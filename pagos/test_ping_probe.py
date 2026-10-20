import subprocess
import unittest
from unittest.mock import patch
from .ping_probe import normalize_address, run_probe

class PingProbeTests(unittest.TestCase):
    def test_ip_validation(self):
        for value in ['8.8.8.8; reboot', '-c 1000', 'example.com', '', None, '224.0.0.1', '0.0.0.0']:
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_address(value)
        self.assertEqual(normalize_address(' 192.168.1.146 '), '192.168.1.146')
    @patch('subprocess.run')
    def test_success_and_bounded_arguments(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '20 packets transmitted, 20 received, 0% packet loss, time 19000ms\nrtt min/avg/max/mdev = 1.0/2.0/3.0/0.5 ms\n')
        result = run_probe('192.168.1.146')
        self.assertEqual(result['received'], 20)
        self.assertEqual(result['latency_ms']['avg'], 2)
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], '192.168.1.146')
        self.assertIn('-w', args[0])
        self.assertEqual(kwargs['timeout'], 25)
        self.assertNotIn('shell', kwargs)
    @patch('subprocess.run')
    def test_packet_loss_is_result(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '20 packets transmitted, 0 received, 100% packet loss, time 20000ms')
        result = run_probe('8.8.8.8')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['loss_percent'], 100)
        self.assertIsNone(result['latency_ms'])
    @patch('subprocess.run')
    def test_command_failure(self, run):
        run.return_value = subprocess.CompletedProcess([], 2, 'ping: Operation not permitted')
        self.assertEqual(run_probe('8.8.8.8')['status'], 'error')
    @patch('subprocess.run')
    def test_ipv6(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '')
        run_probe('2001:4860:4860::8888')
        self.assertEqual(run.call_args.args[0][1], '-6')
