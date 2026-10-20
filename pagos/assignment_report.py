"""Read-only evidence comparison; names and ARP are not validated equipment identities."""
import re
import unicodedata
from .ip_inventory import valid_ip, RESERVED_OCTETS
from .queue_names import target_ip


def canonical_name(value):
    value = unicodedata.normalize('NFD', str(value or ''))
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).lower().split())


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
            if row['name'] and canonical_name(row['name']) != canonical_name(client['nombre']):
                owners = [owner['nombre'] for owner in by_name.get(canonical_name(row['name']), []) if owner['id'] != client['id']]
                findings.append(f'El equipo se llama "{row["name"]}" y el cliente registrado "{client["nombre"]}".' + (f' El nombre coincide con otro cliente: {", ".join(owners)}.' if owners else ' Puede ser un nombre antiguo o abreviado.'))
        if not queues_ok:
            missing.append('No se pudieron consultar las Simple Queues.')
        elif not queue_matches:
            findings.append('No existe una Simple Queue con target individual para esta IP.')
        elif len(queue_matches) > 1:
            findings.append('Más de una Simple Queue individual usa esta IP.')
        elif canonical_name(queue_matches[0].get('name')) != canonical_name(client['nombre']):
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
