"""Read-only calculations for RouterOS Simple Queue statistics."""
from ipaddress import ip_network


def select_queue(rows, ip):
    matches = []
    for row in rows:
        targets = str(row.get('target', '')).split(',')
        if any(target.strip() and ip_network(target.strip(), strict=False).prefixlen == 32
               and str(ip_network(target.strip(), strict=False).network_address) == ip
               for target in targets):
            matches.append(row)
    if len(matches) != 1:
        raise ValueError('Debe existir exactamente una Simple Queue individual para esta IP.')
    row = matches[0]
    if str(row.get('disabled', False)).lower() in ('true', 'yes', '1'):
        raise ValueError('La cola del cliente está desactivada.')
    return row


def counters(row):
    values = str(row.get('bytes', '')).split('/')
    if len(values) != 2:
        raise ValueError('El router no devolvió contadores de bytes válidos.')
    upload, download = map(int, values)
    if min(upload, download) < 0:
        raise ValueError('Contadores inválidos.')
    return upload, download


def average(before, after, seconds):
    if seconds <= 0:
        raise ValueError('Duración inválida.')
    delta = [end - start for start, end in zip(before, after)]
    if min(delta) < 0:
        raise ValueError('Los contadores se reiniciaron durante la medición. Intenta nuevamente.')
    return {
        'duration_seconds': round(seconds, 3),
        'upload_mbps': round(delta[0] * 8 / seconds / 1_000_000, 4),
        'download_mbps': round(delta[1] * 8 / seconds / 1_000_000, 4),
        'upload_mb': round(delta[0] / 1_000_000, 4),
        'download_mb': round(delta[1] / 1_000_000, 4),
    }
