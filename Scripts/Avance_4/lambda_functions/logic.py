"""Reglas puras y comprobables. Ejercicio académico FleetLogix, sin conectarse a AWS."""
from datetime import datetime, timezone, timedelta
from math import atan2, cos, radians, sin, sqrt


def validate_event(event):
    required = ('event_id', 'delivery_id', 'event_type', 'occurred_at')
    if not isinstance(event, dict) or any(not event.get(key) for key in required):
        raise ValueError('Faltan event_id, delivery_id, event_type u occurred_at')
    if event['event_type'] not in ('delivery_status', 'position'):
        raise ValueError('Tipo de evento no permitido')
    try:
        dt = datetime.fromisoformat(str(event['occurred_at']).replace('Z', '+00:00'))
    except (ValueError, TypeError) as exc:
        raise ValueError('Fecha de evento inválida') from exc
    if dt.tzinfo is None:
        raise ValueError('Fecha sin zona horaria')
    normalized = dict(event)
    normalized['delivery_id'] = str(event['delivery_id'])
    normalized['event_id'] = str(event['event_id'])
    normalized['occurred_at'] = dt.astimezone(timezone.utc).isoformat()
    return normalized


def check_delivery_completed(event):
    """Solo una actualización delivery_status=delivered marca completada la entrega."""
    return (event.get('event_type') == 'delivery_status'
            and event.get('status') in ('delivered', 'completed'))


def estimate_eta(event):
    """ETA simple: distancia restante / velocidad. No equivale a navegación GPS."""
    remaining = float(event['remaining_distance_km'])
    speed = float(event['average_speed_kmh'])
    if remaining < 0 or speed <= 0 or speed > 180:
        raise ValueError('Distancia/velocidad no válida')
    start = datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00'))
    result = start + timedelta(hours=remaining / speed)
    return {'eta_utc': result.astimezone(timezone.utc).isoformat(),
            'estimated_minutes': round(remaining / speed * 60, 2)}


def haversine_km(a, b):
    lat1, lon1 = float(a['lat']), float(a['lon'])
    lat2, lon2 = float(b['lat']), float(b['lon'])
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and
            -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError('Coordenadas fuera de rango')
    r = 6371.0
    h = sin(radians(lat2 - lat1) / 2)**2 + (cos(radians(lat1)) * cos(radians(lat2))
        * sin(radians(lon2 - lon1) / 2)**2)
    return 2 * r * atan2(sqrt(h), sqrt(max(0, 1 - h)))


def detect_route_deviation(event, threshold_km=2.0):
    """Demo: distancia a un waypoint; NO calcula desvío real a una polilínea."""
    d = haversine_km(event['current_position'], event['expected_waypoint'])
    return {'deviation_km': round(d, 3), 'threshold_km': threshold_km,
            'alert': d > threshold_km}
