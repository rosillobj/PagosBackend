import unittest
from .sector_clients import stations_from_status, normalize_stations


class AcStatusAssociationsTests(unittest.TestCase):
    def test_fourteen_active_peers_and_disconnected_excluded(self):
        peers=[{'mac':f'AA:BB:CC:DD:EE:{i:02X}', 'lastip':'0.0.0.0', 'signal':-58-i,
                'remote':{'hostname':f'Cliente {i}'}} for i in range(14)]
        status={'wireless':{'mode':'ap-ptmp','count':14,'sta':peers,'sta_disconnected':[{'lastip':'192.168.1.20'}]}}
        result=normalize_stations(stations_from_status(status),'airos')
        self.assertEqual(len(result),14)
        self.assertTrue(all(row['ip'] is None for row in result))
        self.assertEqual(result[0]['name'],'Cliente 0')

    def test_numeric_dictionary_is_sorted(self):
        rows=stations_from_status({'wireless':{'count':2,'sta':{'1':{'mac':'B'},'0':{'mac':'A'}}}})
        self.assertEqual([row['mac'] for row in rows],['A','B'])

    def test_missing_or_truncated_list_requires_fallback(self):
        for wireless in ({}, {'sta':[],'count':14}, {'sta':[{}],'count':2}, {'sta':{'bad':{}}}):
            self.assertIsNone(stations_from_status({'wireless':wireless}))

    def test_empty_active_list_is_valid(self):
        self.assertEqual(stations_from_status({'wireless':{'sta':[],'count':0,'sta_disconnected':[{'mac':'A'}]}}),[])
