"""Bounded ICMP probe using an argument list, never a shell."""
import ipaddress
import os
import re
import subprocess


def normalize_address(value):
    if not isinstance(value, str):
        raise ValueError('Escribe una dirección IP válida.')
    address = ipaddress.ip_address(value.strip())
    if address.is_multicast or address.is_unspecified:
        raise ValueError('Usa una dirección IP de un equipo, no multicast ni una dirección sin especificar.')
    return str(address)


def run_probe(value):
    address = normalize_address(value)
    completed = subprocess.run(
        ['ping', '-6' if ':' in address else '-4', '-n', '-i', '1', '-c', '20', '-W', '1', '-w', '20', address],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, 'LC_ALL': 'C'}, timeout=25, check=False)
    output = completed.stdout or ''
    packets = re.search(r'(\d+) packets transmitted,\s*(\d+) (?:packets )?received,.*?([\d.]+)% packet loss', output)
    latency = re.search(r'(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', output)
    return {'address': address, 'duration_seconds': 20,
            'status': 'error' if completed.returncode not in (0, 1) or not packets else 'completed',
            'transmitted': int(packets[1]) if packets else None,
            'received': int(packets[2]) if packets else None,
            'loss_percent': float(packets[3]) if packets else None,
            'latency_ms': dict(zip(('min', 'avg', 'max', 'mdev'), map(float, latency.groups()))) if latency else None,
            'output': output[-16000:]}
