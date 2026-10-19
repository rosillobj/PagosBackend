"""Credential fallback for read-only antenna status requests."""
FALLBACK_CREDENTIALS = (
    ('ubnt', 'ubnt2'),
    ('ubnt', 'mk3711..'),
    ('ubnt', 'ubnt3711'),
    ('ubnt', 'camaras1'),
    ('bercy', 'Elmata3711..'),
    ('ubnt', 'ubnt'),
)


def authentication_failed(result, family):
    if result.get('ok'):
        return False
    if family == 'airos':
        return result.get('stage') in ('login_failed', 'status_returned_login')
    if result.get('stage') != 'api_error':
        return False
    message = str(result.get('message', '')).lower()
    return any(text in message for text in (
        'cannot log in', 'invalid user name or password',
        'invalid username or password', 'authentication failed',
    ))


def query_with_credentials(query, ip, primary, family, cache_backend=None):
    if cache_backend is None:
        from django.core.cache import cache as cache_backend
    prefix = f'antenna-status-auth:{family}:{ip}'
    candidates = list(dict.fromkeys((primary, *FALLBACK_CREDENTIALS)))
    # Store only an index, never a password, in the cache.
    cache_key = prefix + ':' + primary[0] + ':' + str(len(primary[1]))
    cached = cache_backend.get(cache_key)
    if isinstance(cached, int) and 0 <= cached < len(candidates):
        candidates.insert(0, candidates.pop(cached))
    if cache_backend.get(prefix + ':failed'):
        return {'ok': False, 'stage': 'authentication',
                'message': 'Ninguna credencial configurada permitió consultar la antena. Se reintentará en un minuto.'}
    original = list(dict.fromkeys((primary, *FALLBACK_CREDENTIALS)))
    for username, password in candidates:
        result = query(ip, username, password)
        if result.get('ok'):
            cache_backend.set(cache_key, original.index((username, password)), timeout=3600)
            return result
        if not authentication_failed(result, family):
            return result
    cache_backend.delete(cache_key)
    cache_backend.set(prefix + ':failed', True, timeout=60)
    return {'ok': False, 'stage': 'authentication',
            'message': 'Ninguna credencial configurada permitió consultar la antena. Se reintentará en un minuto.'}
