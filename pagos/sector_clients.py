"""Normalize associated stations without inventing an IP or a client identity."""
import math
import re
from ipaddress import IPv4Address


def number(value):
    if value is None or isinstance(value, bool):
        return None
    match = re.match(r'^\s*(-?\d+(?:\.\d+)?)', str(value))
    if not match:
        return None
    value = float(match.group(1))
    return value if math.isfinite(value) else None


def ip_address(value):
    try:
        ip = IPv4Address(str(value))
        return str(ip) if not ip.is_unspecified and not ip.is_multicast else None
    except ValueError:
        return None


def normalize_stations(rows, family, arp=None):
    if not isinstance(rows, list):
        raise ValueError('La respuesta de asociaciones no es una lista.')
    by_mac = {}
    for entry in arp or []:
        ip = ip_address(entry.get('address'))
        if ip:
            by_mac.setdefault(str(entry.get('mac-address') or '').lower(), set()).add(ip)
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('La respuesta contiene una asociación inválida.')
        remote = row.get('remote') if isinstance(row.get('remote'), dict) else {}
        mac = row.get('mac') if family == 'airos' else row.get('mac-address')
        ip = ip_address(row.get('lastip') if family == 'airos' else row.get('last-ip'))
        matches = by_mac.get(str(mac or '').lower(), set())
        if ip is None and len(matches) == 1:
            ip = next(iter(matches))
        ccq = number(row.get('ccq') if family == 'airos' else row.get('tx-ccq'))
        if family == 'airos' and ccq is not None and ccq > 100:
            ccq /= 10
        if ccq is not None and not 0 <= ccq <= 100:
            ccq = None
        result.append({
            'mac': mac, 'ip': ip,
            'name': (row.get('name') or remote.get('hostname')) if family == 'airos' else row.get('radio-name'),
            'signal_dbm': number(row.get('signal') if family == 'airos' else row.get('signal-strength')),
            'ccq': ccq, 'rx_ccq': number(row.get('rx-ccq')) if family != 'airos' else None,
            'uptime': row.get('uptime'),
            'tx_rate': row.get('tx') if family == 'airos' else row.get('tx-rate'),
            'rx_rate': row.get('rx') if family == 'airos' else row.get('rx-rate'),
        })
    return result


def attach_clients(stations):
    from .models import Cliente
    ips = [row['ip'] for row in stations if row.get('ip')]
    clients = {row['ip_completa']: row for row in Cliente.objects.filter(ip_completa__in=ips).values('id', 'nombre', 'ip_completa')}
    return [{**row, 'cliente_id': clients.get(row.get('ip'), {}).get('id'),
             'cliente_nombre': clients.get(row.get('ip'), {}).get('nombre')} for row in stations]
