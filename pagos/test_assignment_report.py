import copy
import unittest
from .assignment_report import build_audit

class AssignmentReportTests(unittest.TestCase):
    def setUp(self):
        self.clients = [{'id': 1, 'nombre': 'José Pérez', 'ip_completa': '192.168.1.30'}]
        self.sectors = [{'ip': '192.168.1.110', 'ok': True, 'peers': [{'mac': 'AA:BB:CC:DD:EE:FF', 'ip': '192.168.1.30', 'name': 'JOSE PEREZ'}]}]
        self.arp = {'aa:bb:cc:dd:ee:ff': {'192.168.1.30'}}
        self.queues = [{'name': 'José Pérez', 'target': '192.168.1.30/32'}]
    def report(self, **kwargs):
        values = dict(clients=self.clients, sectors=self.sectors, arp=self.arp, arp_ok=True, queues=self.queues, queues_ok=True)
        values.update(kwargs)
        return build_audit(**values)
    def test_matching_observations_and_accent_normalization(self):
        self.assertEqual(self.report()['items'][0]['category'], 'coinciden')
    def test_different_queue_name_requires_review(self):
        self.assertEqual(self.report(queues=[{'name': 'Otro', 'target': '192.168.1.30'}])['items'][0]['category'], 'revisar')
    def test_missing_sources_are_not_identity_mismatch(self):
        self.assertEqual(self.report(arp_ok=False, queues_ok=False)['items'][0]['category'], 'sin_informacion')
    def test_no_association_is_inconclusive(self):
        self.assertEqual(self.report(sectors=[])['items'][0]['category'], 'sin_informacion')
    def test_unknown_ip_remains_unresolved(self):
        self.sectors[0]['peers'][0]['ip'] = '0.0.0.0'
        result = self.report(arp={})
        self.assertEqual(result['items'][-1]['kind'], 'antena')
        self.assertEqual(result['items'][-1]['category'], 'sin_informacion')
    def test_multiple_macs_flag_possible_conflict(self):
        self.sectors[0]['peers'].append({'mac': '00:11:22:33:44:55', 'ip': '192.168.1.30'})
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')
    def test_unregistered_association(self):
        self.assertEqual(self.report(clients=[])['items'][0]['category'], 'revisar')
    def test_reserved_ip_not_flagged_as_unregistered(self):
        self.sectors[0]['peers'][0]['ip'] = '192.168.1.110'
        self.assertEqual(self.report(clients=[], arp={})['items'], [])
    def test_subnet_queue_not_individual_match(self):
        result = self.report(queues=[{'name': 'José Pérez', 'target': '192.168.1.0/24'}])
        self.assertEqual(result['items'][0]['queues'], [])
        self.assertEqual(result['items'][0]['category'], 'revisar')
    def test_duplicate_customer_ip(self):
        self.clients.append({'id': 2, 'nombre': 'Otro cliente', 'ip_completa': '192.168.1.30'})
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')
    def test_no_input_mutation(self):
        before = copy.deepcopy((self.clients, self.sectors, self.arp, self.queues))
        self.report()
        self.assertEqual(before, (self.clients, self.sectors, self.arp, self.queues))

    def test_name_with_private_street_and_punctuation(self):
        self.sectors[0]['peers'][0]['name'] = 'JOSE-PEREZ / Privada Las Flores 24'
        self.queues[0]['name'] = 'Jose Perez (Priv. Las Flores)'
        self.assertEqual(self.report()['items'][0]['category'], 'coinciden')

    def test_incomplete_name(self):
        self.clients[0]['nombre'] = 'José Antonio Pérez López'
        self.sectors[0]['peers'][0]['name'] = 'Jose Perez'
        self.assertEqual(self.report()['items'][0]['category'], 'coinciden')

    def test_single_name_when_unique(self):
        self.sectors[0]['peers'][0]['name'] = 'Jose'
        self.assertEqual(self.report()['items'][0]['category'], 'coinciden')

    def test_single_name_shared_by_customers_still_requires_review(self):
        self.clients.append({'id': 2, 'nombre': 'Jose Garcia', 'ip_completa': '192.168.1.31'})
        self.sectors[0]['peers'][0]['name'] = 'Jose'
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')

    def test_exact_other_customer_name_is_not_accepted_as_partial(self):
        self.clients[0]['nombre'] = 'Jose Antonio Perez'
        self.clients.append({'id': 2, 'nombre': 'Jose Perez', 'ip_completa': '192.168.1.31'})
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')

    def test_different_names_still_require_review(self):
        self.sectors[0]['peers'][0]['name'] = 'Maria Garcia Privada Flores'
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')

    def test_common_surname_is_not_enough_for_full_names(self):
        self.sectors[0]['peers'][0]['name'] = 'Luis Perez'
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')

    def test_location_only_is_not_a_customer_match(self):
        self.sectors[0]['peers'][0]['name'] = 'Privada 24'
        self.assertEqual(self.report()['items'][0]['category'], 'revisar')

    def test_short_name_plus_location_suffix(self):
        self.sectors[0]['peers'][0]['name'] = 'Jose / Privada Las Flores'
        self.queues[0]['name'] = 'Jose Priv. Las Flores 24'
        self.assertEqual(self.report()['items'][0]['category'], 'coinciden')
