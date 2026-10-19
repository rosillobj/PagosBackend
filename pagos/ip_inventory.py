"""Pure IP inventory classification. No missing response proves an address is free."""
from ipaddress import IPv4Address, ip_network

RESERVED_OCTETS = frozenset((99, 100, 156, 101, 127, 122, 124, 121, 129, 126,
                            123, 125, 110, 111, 120, 179, 77, 128, 254))
UBIQUITI_SECTORS = (121, 122, 123, 124, 126, 129, 156, 127, 110, 111, 125, 77)
MIKROTIK_SECTORS = (101, 120, 128)


def valid_ip(value):
    try:
        ip = IPv4Address(str(value).strip())
        return str(ip) if ip in ip_network('192.168.1.0/24') and int(str(ip).split('.')[-1]) not in (0, 255) else None
    except ValueError:
        return None


def classify(start, end, clients, pings, associated_ips, coverage_complete):
    assigned = {valid_ip(row.get('ip_completa')): row for row in clients}
    assigned.pop(None, None)
    associated = set(associated_ips)
    rows = []
    for number in range(start, end + 1):
        ip = f'192.168.1.{number}'
        client = assigned.get(ip)
        ping = pings.get(ip, 'error')
        reserved = number in RESERVED_OCTETS
        linked = ip in associated
        candidate = not client and not reserved and not linked and ping == 'no_response' and coverage_complete
        rows.append({
            'ip': ip, 'cliente_id': client.get('id') if client else None,
            'cliente_nombre': client.get('nombre') if client else None,
            'asignada': client is not None, 'reservada': reserved,
            'asociada': linked, 'ping': ping, 'candidata': candidate,
        })
    free_db = [row['ip'] for row in rows if not row['asignada'] and not row['reservada']]
    return {
        'subnet': '192.168.1.0/24', 'range': {'start': start, 'end': end},
        'disponibles': free_db, 'disponibles_count': len(free_db),
        'sin_respuesta_ping': [row['ip'] for row in rows if row['ping'] == 'no_response'],
        'candidatas_disponibles': [row['ip'] for row in rows if row['candidata']],
        'ocupadas_count': sum(row['asignada'] for row in rows),
        'reservadas_count': sum(row['reservada'] for row in rows),
        'bloqueadas_count': sum(row['asignada'] or row['reservada'] for row in rows),
        'verificacion_completa': coverage_complete and all(row['ping'] != 'error' for row in rows),
        'resultados': rows,
    }
