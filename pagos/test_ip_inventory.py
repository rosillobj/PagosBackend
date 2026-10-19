import unittest
from .ip_inventory import classify, valid_ip


class InventoryTests(unittest.TestCase):
    def test_assigned_offline_not_free(self):
        result = classify(21, 22, [{'id': 7, 'nombre': 'Cliente', 'ip_completa': '192.168.1.21'}],
                          {'192.168.1.21': 'no_response', '192.168.1.22': 'no_response'}, [], True)
        self.assertEqual(result['disponibles'], ['192.168.1.22'])
        self.assertEqual(result['sin_respuesta_ping'], ['192.168.1.21', '192.168.1.22'])
        self.assertEqual(result['candidatas_disponibles'], ['192.168.1.22'])
        self.assertEqual(result['resultados'][0]['cliente_nombre'], 'Cliente')

    def test_association_and_ping_exclude_candidates(self):
        result = classify(21, 23, [], {'192.168.1.21': 'no_response', '192.168.1.22': 'reachable', '192.168.1.23': 'error'}, ['192.168.1.21'], True)
        self.assertEqual(result['candidatas_disponibles'], [])
        self.assertTrue(result['resultados'][0]['asociada'])
        self.assertFalse(result['verificacion_completa'])

    def test_incomplete_sector_coverage_blocks_recommendations(self):
        result = classify(21, 21, [], {'192.168.1.21': 'no_response'}, [], False)
        self.assertEqual(result['candidatas_disponibles'], [])
        self.assertEqual(result['sin_respuesta_ping'], ['192.168.1.21'])

    def test_reserved_addresses_include_infrastructure(self):
        result = classify(110, 111, [], {'192.168.1.110': 'no_response', '192.168.1.111': 'no_response'}, [], True)
        self.assertEqual(result['disponibles'], [])
        self.assertEqual(result['candidatas_disponibles'], [])
        self.assertTrue(result['resultados'][0]['reservada'])
        self.assertEqual(classify(254, 254, [], {'192.168.1.254':'no_response'}, [], True)['disponibles'], [])

    def test_normalizes_only_target_network(self):
        self.assertEqual(valid_ip(' 192.168.1.21 '), '192.168.1.21')
        for value in ('bad', None, '192.168.2.21', '192.168.1.0', '192.168.1.255'):
            self.assertIsNone(valid_ip(value))
