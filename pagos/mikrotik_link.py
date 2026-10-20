"""Read wireless monitor and per-peer statistics on RouterOS wireless v6."""
import math
import re


def numeric(value):
    if isinstance(value, bool) or value is None:
        return None
    match = re.match(r'^\s*(-?\d+(?:\.\d+)?)', str(value))
    if not match:
        return None
    number = float(match.group(1))
    return number if math.isfinite(number) else None


def read_wireless_link(api, wlan, include_stations=False):
    if not wlan:
        return ({'stations': None, 'stations_error': 'No se encontró una interfaz inalámbrica.'} if include_stations else {}), 'No se encontró una interfaz inalámbrica.'
    name = wlan.get('name')
    monitor = {}
    errors = []
    try:
        rows = list(api('/interface/wireless/monitor', numbers=wlan.get('.id') or name, once=''))
        monitor = rows[0] if rows else {}
    except Exception:
        errors.append('No se pudo consultar el monitoreo inalámbrico.')
    peer = {}
    stations = None
    stations_error = None
    try:
        rows = list(api('/interface/wireless/registration-table/print', stats=''))
        matches = [row for row in rows if row.get('interface') == name]
        stations = matches
        if len(matches) == 1:
            peer = matches[0]
        elif len(matches) > 1:
            if not include_stations:
                errors.append('Hay varios enlaces registrados; no se seleccionó un cliente arbitrario.')
    except Exception:
        stations_error = 'No se pudo consultar la tabla de registros inalámbricos.'
        errors.append(stations_error)

    def first(*values):
        return next((v for v in values if v is not None and v != ''), None)

    def ccq(value):
        value = numeric(value)
        return value if value is not None and 0 <= value <= 100 else None

    link = {
        'signal_dbm': numeric(first(monitor.get('signal-strength'), peer.get('signal-strength'))),
        'noise_dbm': numeric(first(monitor.get('noise-floor'), peer.get('noise-floor'))),
        'snr_db': numeric(first(monitor.get('signal-to-noise'), monitor.get('snr'), peer.get('signal-to-noise'))),
        'tx_rate': first(monitor.get('tx-rate'), peer.get('tx-rate')),
        'rx_rate': first(monitor.get('rx-rate'), peer.get('rx-rate')),
        'tx_ccq': ccq(first(peer.get('tx-ccq'), monitor.get('overall-tx-ccq'))),
        'rx_ccq': ccq(peer.get('rx-ccq')),
        'ccq': ccq(first(peer.get('tx-ccq'), monitor.get('overall-tx-ccq'), monitor.get('ccq'), peer.get('rx-ccq'))),
    }
    if include_stations:
        link.update(stations=stations, stations_error=stations_error)
    return link, ' '.join(errors) or None
