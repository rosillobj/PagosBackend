import unittest
from .antenna_credentials import query_with_credentials, FALLBACK_CREDENTIALS


class Cache:
    def __init__(self): self.values = {}
    def get(self, key): return self.values.get(key)
    def set(self, key, value, timeout): self.values[key] = value
    def delete(self, key): self.values.pop(key, None)


class CredentialFallbackTests(unittest.TestCase):
    def test_fallback_then_reuse_success(self):
        calls = []
        cache = Cache()
        def query(ip, user, password):
            calls.append((user, password))
            return {'ok': True} if (user, password) == FALLBACK_CREDENTIALS[2] else {'ok': False, 'stage': 'login_failed'}
        self.assertTrue(query_with_credentials(query, '192.168.1.146', FALLBACK_CREDENTIALS[0], 'airos', cache)['ok'])
        self.assertEqual(len(calls), 3)
        calls.clear()
        self.assertTrue(query_with_credentials(query, '192.168.1.146', FALLBACK_CREDENTIALS[0], 'airos', cache)['ok'])
        self.assertEqual(len(calls), 1)
        self.assertNotIn(FALLBACK_CREDENTIALS[2][1], str(cache.values))

    def test_network_and_permission_errors_do_not_retry(self):
        for stage, message in [('tcp_check', 'Connection refused'), ('api_error', 'not enough permissions'), ('unknown', 'timeout')]:
            calls=[]
            def query(*args):
                calls.append(args)
                return {'ok': False, 'stage': stage, 'message': message}
            query_with_credentials(query, '192.168.1.1', ('admin','original'), 'mikrotik', Cache())
            self.assertEqual(len(calls), 1)

    def test_mikrotik_exhaustion_and_cooldown(self):
        calls=[]
        cache=Cache()
        def query(*args):
            calls.append(args)
            return {'ok': False, 'stage': 'api_error', 'message': 'cannot log in'}
        result=query_with_credentials(query, '192.168.1.1', ('admin','original'), 'mikrotik', cache)
        self.assertEqual(result['stage'], 'authentication')
        self.assertEqual(len(calls), 7)
        query_with_credentials(query, '192.168.1.1', ('admin','original'), 'mikrotik', cache)
        self.assertEqual(len(calls), 7)
