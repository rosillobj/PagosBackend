import unittest
from .views import normalize_airos


class AirosAcTests(unittest.TestCase):
    def test_powerbeam_status(self):
        result = normalize_airos({
            'host': {'hostname': 'PowerBeam 5AC 300 ISO', 'uptime': 550508},
            'wireless': {'essid': 'ubnt_link7', 'mode': 'sta-ptmp', 'apmac': '78:8A:20:10:77:6C', 'frequency': 5445, 'noisef': -100,
                         'polling': {'dcap': 67860, 'ucap': 36660},
                         'sta': [{'mac': '78:8A:20:10:77:6C', 'signal': -58, 'uptime': 412254, 'remote': {'uptime': 550506, 'signal': -65}}]},
            'interfaces': [{'ifname': 'eth0', 'enabled': True, 'status': {'plugged': True, 'speed': 100, 'duplex': True}}],
        })
        self.assertEqual(result['device']['uptime'], 550508)
        self.assertEqual(result['link']['association_uptime'], 412254)
        self.assertEqual(result['link']['signal_dbm'], -58)
        self.assertEqual(result['link']['download_capacity_mbps'], 67.86)
        self.assertEqual(result['link']['upload_capacity_mbps'], 36.66)
        self.assertIsNone(result['link']['capacity_pct'])
        self.assertIsNone(result['link']['ccq'])
        self.assertEqual(result['interfaces']['eth0']['duplex'], 1)

    def test_ap_with_multiple_stations_does_not_guess(self):
        result = normalize_airos({'wireless': {'mode': 'ap-ptmp', 'sta': [{'signal': -58}, {'signal': -70}]}})
        self.assertIsNone(result['link']['signal_dbm'])

    def test_matching_mac_and_legacy_values(self):
        result = normalize_airos({'wireless': {'mode': 'sta', 'apmac': 'AA', 'signal': -54, 'ccq': 986, 'sta': [{'mac': 'BB', 'signal': -80}, {'mac': 'aa', 'signal': -58, 'uptime': 10}]}})
        self.assertEqual(result['link']['signal_dbm'], -54)
        self.assertEqual(result['link']['association_uptime'], 10)
        self.assertEqual(result['link']['ccq'], 986)
