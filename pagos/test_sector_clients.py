import unittest
from .sector_clients import normalize_stations
from .mikrotik_link import read_wireless_link


class SectorStationTests(unittest.TestCase):
    def test_ubiquiti_all_clients_and_local_association_time(self):
        rows = normalize_stations([
            {'mac': 'AA', 'lastip': '192.168.1.21', 'name': '', 'signal': -58, 'ccq': 986, 'uptime': 100, 'remote': {'hostname': 'Cliente AC', 'uptime': 500}},
            {'mac': 'BB', 'lastip': '192.168.1.22', 'signal': -65, 'ccq': 0},
        ], 'airos')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['name'], 'Cliente AC')
        self.assertEqual(rows[0]['ccq'], 98.6)
        self.assertEqual(rows[0]['uptime'], 100)
        self.assertEqual(rows[1]['ccq'], 0)

    def test_mikrotik_arp_mapping_without_guessing(self):
        rows = normalize_stations([{'mac-address': 'AA', 'signal-strength': '-61dBm@6Mbps', 'tx-ccq': '95%', 'rx-ccq': '91%'}], 'mikrotik', [{'mac-address': 'aa', 'address': '192.168.1.21'}])
        self.assertEqual(rows[0]['ip'], '192.168.1.21')
        self.assertEqual(rows[0]['signal_dbm'], -61)
        self.assertEqual(rows[0]['ccq'], 95)
        rows = normalize_stations([{'mac-address': 'AA'}], 'mikrotik', [{'mac-address':'aa','address':'192.168.1.21'},{'mac-address':'aa','address':'192.168.1.22'}])
        self.assertIsNone(rows[0]['ip'])

    def test_ac_missing_ccq_does_not_become_zero(self):
        rows = normalize_stations([{'signal': -58, 'remote': {'signal': -70}}], 'airos')
        self.assertEqual(rows[0]['signal_dbm'], -58)
        self.assertIsNone(rows[0]['ccq'])
        self.assertIsNone(rows[0]['ip'])

    def test_invalid_station_payload_is_not_empty_success(self):
        for rows in ({'error':'login'}, ['bad']):
            with self.assertRaises(ValueError):
                normalize_stations(rows, 'airos')

    def test_multi_client_monitor_returns_entire_list(self):
        def api(command, **kwargs):
            return [] if command.endswith('/monitor') else [{'interface':'wlan1','signal-strength':-50},{'interface':'wlan1','signal-strength':-80}]
        link, error = read_wireless_link(api, {'name':'wlan1'}, include_stations=True)
        self.assertEqual(len(link['stations']),2)
        self.assertIsNone(link['signal_dbm'])
        self.assertIsNone(error)

    def test_registration_error_is_not_zero_clients(self):
        def api(*args, **kwargs):
            raise RuntimeError('unavailable')
        link, error = read_wireless_link(api, {'name':'wlan1'}, include_stations=True)
        self.assertIsNone(link['stations'])
        self.assertIsNotNone(link['stations_error'])
