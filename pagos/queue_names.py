"""Build and apply queue name changes by exact individual target IP."""
from ipaddress import IPv4Address, ip_network


def target_ip(queue):
    target = str(queue.get('target') or '').strip()
    if ',' in target:
        return None
    try:
        network = ip_network(target, strict=False)
        return str(network.network_address) if network.version == 4 and network.prefixlen == 32 else None
    except ValueError:
        return None


def plan_names(clients, queues):
    changes, skipped = [], []
    for client in clients:
        try:
            ip = str(IPv4Address(str(client.get('ip_completa') or '').strip()))
        except ValueError:
            skipped.append({'cliente_id': client['id'], 'reason': 'IP inválida'})
            continue
        name = str(client.get('nombre') or '').strip()
        matches = [q for q in queues if target_ip(q) == ip]
        if not name or len(matches) != 1:
            skipped.append({'cliente_id': client['id'], 'ip': ip, 'reason': 'Nombre vacío o cola individual inexistente/duplicada'})
            continue
        queue = matches[0]
        if queue.get('name') == name:
            continue
        if any(q.get('name') == name and q.get('.id') != queue.get('.id') for q in queues):
            skipped.append({'cliente_id': client['id'], 'ip': ip, 'reason': 'El nombre ya pertenece a otra cola'})
            continue
        if not queue.get('.id') or str(queue.get('dynamic', False)).lower() in ('true', 'yes', '1'):
            skipped.append({'cliente_id': client['id'], 'ip': ip, 'reason': 'Cola dinámica o sin identificador'})
            continue
        changes.append({'cliente_id': client['id'], 'ip': ip, 'queue_id': queue['.id'], 'old_name': queue.get('name'), 'new_name': name})
    return {'changes': changes, 'skipped': skipped}


def apply_names(api, changes, clients):
    queues = list(api('/queue/simple/print'))
    clients_by_id = {client['id']: client for client in clients}
    updated, skipped, failed = [], [], []
    for change in changes:
        client = clients_by_id.get(change['cliente_id'])
        queue = next((q for q in queues if q.get('.id') == change['queue_id']), None)
        if not client or str(client.get('ip_completa', '')).strip() != change['ip'] or str(client.get('nombre', '')).strip() != change['new_name']:
            skipped.append({**change, 'reason': 'El cliente cambió después de la vista previa'})
            continue
        if not queue or target_ip(queue) != change['ip'] or queue.get('name') != change['old_name']:
            skipped.append({**change, 'reason': 'La cola cambió después de la vista previa'})
            continue
        if any(q.get('name') == change['new_name'] and q.get('.id') != change['queue_id'] for q in queues):
            skipped.append({**change, 'reason': 'Nombre ocupado por otra cola'})
            continue
        try:
            # Only the name is sent. No limit, target, parent, order or disabled flag is changed.
            tuple(api('/queue/simple/set', **{'.id': change['queue_id'], 'name': change['new_name']}))
            queue['name'] = change['new_name']
            updated.append(change)
        except Exception:
            failed.append({**change, 'reason': 'El router rechazó el cambio o se perdió la conexión'})
            # Do not send a cascade of writes after a connection/permission failure.
            skipped.extend({**remaining, 'reason': 'Pendiente después de un error'} for remaining in changes[len(updated) + len(skipped) + 1:])
            break
    # Verify updates against the router instead of assuming every write was saved.
    if updated:
        try:
            current = {q['.id']: q for q in api('/queue/simple/print')}
            verified = []
            for change in updated:
                queue = current.get(change['queue_id'], {})
                if queue.get('name') == change['new_name'] and target_ip(queue) == change['ip']:
                    verified.append(change)
                else:
                    failed.append({**change, 'reason': 'No se confirmó el nombre en el router'})
            updated = verified
        except Exception:
            failed.extend({**change, 'reason': 'Cambio enviado, pero no se pudo verificar'} for change in updated)
            updated = []
    return {'updated': updated, 'skipped': skipped, 'failed': failed}
