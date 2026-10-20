"""Read-only evidence comparison; names and ARP are not validated equipment identities."""
import re
import unicodedata
from .ip_inventory import valid_ip, RESERVED_OCTETS
from .queue_names import target_ip


def canonical_name(value):
    value = unicodedata.normalize('NFD', str(value or ''))
    value = ''.join(c for c in value if not unicodedata.combining(c)).lower()
    return ' '.join(re.findall(r'[a-z0-9]+', value))


# Location labels and connectors do not identify a customer.
NAME_LABELS = frozenset(('de', 'del', 'la', 'las', 'el', 'los', 'y', 'privada',
                         'priv', 'privado', 'calle', 'colonia', 'col', 'fracc',
                         'fraccionamiento', 'casa', 'cliente', 'antena'))


def name_words(value):
    normalized = canonical_name(value)
    # A location suffix does not form part of the person's name.
    parts = re.split(r'\b(?:privada|priv|privado|calle|colonia|col|fracc|fraccionamiento)\b', normalized, maxsplit=1)
    if len(parts) > 1 and parts[0].strip():
        normalized = parts[0]
    return {word for word in normalized.split()
            if word not in NAME_LABELS and not word.isdigit() and len(word) > 1}


def partial_name_match(left, right):
    left, right = name_words(left), name_words(right)
    if not left or not right:
        return False
    common = left & right
    shorter = min(len(left), len(right))
    if shorter == 1:
        return bool(common) and len(next(iter(common))) >= 4
    return len(common) >= 2 and len(common) / shorter >= 2 / 3


def compatible_name(value, client, clients):
    """Tolerate partial names only when they do not identify another customer."""
    own = canonical_name(client.get('nombre'))
    observed = canonical_name(value)
    if observed and observed == own:
        return True
    if not partial_name_match(value, client.get('nombre')):
        return False
    # An exact match to another registered name takes precedence over a partial one.
    if any(c['id'] != client['id'] and canonical_name(c.get('nombre')) == observed
           and canonical_name(c.get('nombre')) != own for c in clients):
        return False
    # Partial/short names shared by several customers remain a review item.
    return not any(c['id'] != client['id'] and canonical_name(c.get('nombre')) != own
                   and partial_name_match(value, c.get('nombre')) for c in clients)


def canonical_mac(value):
    value = re.sub(r'[^0-9a-f]', '', str(value or '').lower())
    return ':'.join(value[i:i+2] for i in range(0, 12, 2)) if len(value) == 12 else None


def build_audit(clients, sectors, arp, arp_ok, queues, queues_ok):
    arp_by_mac = {}
    for mac, addresses in arp.items():
        key = canonical_mac(mac)
        if key:
            arp_by_mac.setdefault(key, set()).update(ip for ip in addresses if valid_ip(ip))
    observations = []
    for sector in sectors:
        if not sector['ok']:
            continue
        for peer in sector.get('peers', []):
            mac = canonical_mac(peer.get('mac'))
            addresses = set(arp_by_mac.get(mac, set()))
            reported = valid_ip(peer.get('ip'))
            if reported:
                addresses.add(reported)
            observations.append({'sector': sector['ip'], 'mac': mac, 'name': peer.get('name'),
                                 'reported_ip': reported, 'arp_ips': sorted(arp_by_mac.get(mac, set())),
                                 'ips': sorted(addresses)})
    by_ip = {}
    for observation in observations:
        for ip in observation['ips']:
            by_ip.setdefault(ip, []).append(observation)
    by_name = {}
    for client in clients:
        if canonical_name(client.get('nombre')):
            by_name.setdefault(canonical_name(client['nombre']), []).append(client)
    items = []
    sectors_complete = all(sector['ok'] for sector in sectors) and bool(sectors)
    for client in clients:
        ip = valid_ip(client.get('ip_completa'))
        observed = by_ip.get(ip, []) if ip else []
        queue_matches = [q for q in queues if ip and target_ip(q) == ip] if queues_ok else []
        findings, missing = [], []
        if not ip:
            missing.append('La IP del cliente es inválida o está fuera de 192.168.1.0/24.')
        other_clients = [c['nombre'] for c in clients if ip and valid_ip(c.get('ip_completa')) == ip and c['id'] != client['id']]
        if other_clients:
            findings.append(f'La misma IP está registrada en otros clientes: {", ".join(other_clients)}.')
        if not observed:
            missing.append('No se relacionó una asociación con esta IP. No confirma que la antena esté desconectada.')
        macs = {row['mac'] for row in observed if row['mac']}
        if len(macs) > 1:
            findings.append('Varias MAC asociadas aparecen relacionadas con esta IP. Revisar posibles interfaces del mismo equipo, ARP antiguo o conflicto de IP.')
        for mac in macs:
            locations = {row['sector'] for row in observations if row['mac'] == mac}
            if len(locations) > 1:
                findings.append(f'La MAC {mac} aparece en más de un sector: {", ".join(sorted(locations))}. Puede ser una observación transitoria.')
        for row in observed:
            if row['reported_ip'] and row['arp_ips'] and row['reported_ip'] not in row['arp_ips']:
                findings.append('La IP reportada por el sector no coincide con las IP observadas en ARP para esa MAC.')
            if row['name'] and not compatible_name(row['name'], client, clients):
                owners = [owner['nombre'] for owner in by_name.get(canonical_name(row['name']), []) if owner['id'] != client['id']]
                findings.append(f'El equipo se llama "{row["name"]}" y el cliente registrado "{client["nombre"]}".' + (f' El nombre coincide con otro cliente: {", ".join(owners)}.' if owners else ' No se pudo relacionar el nombre de forma suficiente o es ambiguo entre clientes.'))
        if not queues_ok:
            missing.append('No se pudieron consultar las Simple Queues.')
        elif not queue_matches:
            findings.append('No existe una Simple Queue con target individual para esta IP.')
        elif len(queue_matches) > 1:
            findings.append('Más de una Simple Queue individual usa esta IP.')
        elif not compatible_name(queue_matches[0].get('name'), client, clients):
            findings.append(f'La cola se llama "{queue_matches[0].get("name", "")}". Diferencia de nombre; no demuestra una asignación incorrecta.')
        if not arp_ok:
            missing.append('No se pudo consultar ARP del router principal.')
        if not sectors_complete:
            missing.append('No fue posible consultar todos los sectores.')
        category = 'revisar' if findings else 'sin_informacion' if missing else 'coinciden'
        items.append({'kind': 'cliente', 'cliente_id': client['id'], 'nombre': client['nombre'],
                      'ip': ip or client.get('ip_completa'), 'category': category,
                      'findings': list(dict.fromkeys(findings)), 'missing': missing,
                      'observations': observed,
                      'queues': [{'name': q.get('name'), 'target': q.get('target')} for q in queue_matches]})
    assigned_ips = {valid_ip(client.get('ip_completa')) for client in clients}
    for row in observations:
        unknown = [ip for ip in row['ips'] if ip not in assigned_ips and int(ip.split('.')[-1]) not in RESERVED_OCTETS]
        if not row['ips'] or unknown:
            items.append({'kind': 'antena', 'cliente_id': None, 'nombre': row['name'] or 'Antena sin nombre',
                          'ip': ', '.join(unknown) or None,
                          'category': 'revisar' if unknown else 'sin_informacion',
                          'findings': ['Antena asociada con IP sin cliente registrado.'] if unknown else [],
                          'missing': [] if unknown else ['La MAC está asociada, pero no se pudo relacionar con una IP.'],
                          'observations': [row], 'queues': []})
    return {
        'items': items,
        'summary': {category: sum(item['category'] == category for item in items) for category in ('coinciden', 'revisar', 'sin_informacion')},
        'sources': {'sectors': [{k: v for k, v in sector.items() if k != 'peers'} for sector in sectors], 'arp_ok': arp_ok, 'queues_ok': queues_ok},
        'notice': 'Reporte de observaciones, no identidad validada. Las MAC de radio y Ethernet pueden diferir. ARP puede contener entradas antiguas. Los nombres de colas pueden provenir de la sincronización del backend. No se modificó ningún registro ni equipo.',
    }
