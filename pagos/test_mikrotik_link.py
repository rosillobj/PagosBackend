import unittest
from .mikrotik_link import read_wireless_link


class WirelessLinkTests(unittest.TestCase):
    def api(self, command, **kwargs):
        if command.endswith('/monitor'):
            self.assertEqual(kwargs, {'numbers': '*1', 'once': ''})
            return [{'signal-strength': '-58dBm@6Mbps', 'overall-tx-ccq': '95%', 'noise-floor': '-100dBm'}]
        return [{'interface': 'radio-cliente', 'tx-ccq': '99%', 'rx-ccq': 97, 'signal-strength': '-59', 'signal-to-noise': 41}]

    def test_monitor_and_registration(self):
        link, error = read_wireless_link(self.api, {'name': 'radio-cliente', '.id': '*1'})
        self.assertEqual(link['signal_dbm'], -58)
        self.assertEqual(link['ccq'], 99)
        self.assertEqual(link['rx_ccq'], 97)
        self.assertIsNone(error)

    def test_registration_survives_monitor_failure_and_zero_ccq(self):
        def api(command, **kwargs):
            if command.endswith('/monitor'):
                raise RuntimeError('unavailable')
            return [{'interface': 'wlan1', 'signal-strength': '-63', 'tx-ccq': 0}]
        link, error = read_wireless_link(api, {'name': 'wlan1'})
        self.assertEqual(link['signal_dbm'], -63)
        self.assertEqual(link['ccq'], 0)
        self.assertIsNotNone(error)

    def test_multiple_clients_are_not_mixed(self):
        def api(command, **kwargs):
            if command.endswith('/monitor'):
                return []
            return [{'interface': 'wlan1', 'signal-strength': -50}, {'interface': 'wlan1', 'signal-strength': -80}]
        link, error = read_wireless_link(api, {'name': 'wlan1'})
        self.assertIsNone(link['signal_dbm'])
        self.assertIsNotNone(error)
