"""FleetLogix Avance 4: cuatro funciones puras para demo académica.
No requiere AWS, red ni credenciales. UTC en ISO8601 con 'Z'.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from math import atan2, radians, sin, cos, sqrt


def check_delivery_completed(event: dict) -> dict:
    """1. Valida que una entrega marcada completed tenga identificación y fecha."""
    required = ('delivery_id', 'event_id', 'occurred_at')
    if not all(event.get(k) for k in required):
        raise ValueError('Faltan identificadores o fecha del evento')
    if event.get('status') not in {'completed', 'delivered'}:
        return {'completed': False, 'delivery_id': str(event['delivery_id'])}
    datetime.fromisoformat(event['occurred_at'].replace('Z','+00:00'))
    return {'completed': True, 'delivery_id': str(event['delivery_id'])}


def estimate_eta(event: dict) -> dict:
    """2. ETA ilustrativo: distancia restante / velocidad, no predicción ML."""
    distance = float(event['remaining_distance_km'])
    speed = float(event['average_speed_kmh'])
    if distance < 0 or speed <= 0: raise ValueError('Distancia/velocidad inválida')
    eta = datetime.now(timezone.utc) + timedelta(hours=distance/speed)
    return {'eta_utc': eta.isoformat(), 'estimated_minutes': round(60*distance/speed, 2)}


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    a = sin(radians(lat2-lat1)/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(radians(lon2-lon1)/2)**2
    return 2*r*atan2(sqrt(a),sqrt(max(0,1-a)))


def detect_route_deviation(event: dict, threshold_km=2.0) -> dict:
    """3. Demo: separación respecto a un waypoint, NO distancia a polilínea real."""
    p=event['current_position']; q=event['expected_waypoint']
    d=haversine_km(float(p['lat']),float(p['lon']),float(q['lat']),float(q['lon']))
    return {'deviation_km':round(d,3),'alert':d > threshold_km,'threshold_km':threshold_km}


def validate_event(event: dict) -> dict:
    """4. Normalización de evento; permite deduplicar por event_id."""
    required=('event_id','delivery_id','event_type','occurred_at')
    if not all(event.get(k) for k in required): raise ValueError('Faltan campos obligatorios')
    dt=datetime.fromisoformat(event['occurred_at'].replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Se requiere zona horaria')
    return {'event_id':str(event['event_id']), 'delivery_id':str(event['delivery_id']),
            'event_type':str(event['event_type']), 'occurred_at':dt.astimezone(timezone.utc).isoformat(),
            'payload':event}
