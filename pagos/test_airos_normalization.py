import unittest
from .views import normalize_airos


class AirosHostNormalizationTests(unittest.TestCase):
    def test_nested_host(self):
        result = normalize_airos({'host': {'uptime': 548634, 'hostname': 'Karolina bolonia', 'totalram': 100, 'freeram': 40, 'cpuload': 72.3}})
        self.assertEqual(result['device']['uptime'], 548634)
        self.assertEqual(result['device']['hostname'], 'Karolina bolonia')
        self.assertEqual(result['system']['free_ram_pct'], 40)
        self.assertEqual(result['system']['cpuload'], 72.3)

    def test_legacy_root_fallback_and_numeric_string(self):
        result = normalize_airos({'uptime': '548634', 'hostname': 'Legacy', 'host': {'hostname': None}})
        self.assertEqual(result['device']['uptime'], 548634)
        self.assertEqual(result['device']['hostname'], 'Legacy')

    def test_zero_and_invalid_uptime(self):
        self.assertEqual(normalize_airos({'host': {'uptime': 0}, 'uptime': 999})['device']['uptime'], 0)
        for value in (None, '', 'bad', -1, 'NaN', 'inf'):
            with self.subTest(value=value):
                self.assertIsNone(normalize_airos({'host': {'uptime': value}})['device']['uptime'])

    def test_preserves_link_and_interfaces(self):
        result = normalize_airos({'host': {'uptime': 10}, 'wireless': {'essid': 'ubnt_link7', 'ccq': 986}, 'interfaces': [{'ifname': 'eth0', 'enabled': True, 'status': {'plugged': 1, 'speed': 100}}]})
        self.assertEqual(result['wireless']['essid'], 'ubnt_link7')
        self.assertEqual(result['link']['ccq'], 986)
        self.assertEqual(result['interfaces']['eth0']['speed'], 100)
