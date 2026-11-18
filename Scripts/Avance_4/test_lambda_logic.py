"""Prueba end-to-end LOCAL: API -> estado -> ETA -> alerta -> S3. Cero llamadas AWS."""
import json
import os
os.environ['LOCAL_DEMO'] = '1'
from lambda_functions.handlers import (
    CURRENT_STATE, SEEN_EVENTS, EVENT_BUS, ALERTS, ARCHIVE,
    lambda_ingest, lambda_eta, lambda_route_alert, lambda_archive,
)
from lambda_functions.logic import estimate_eta, check_delivery_completed


def main():
    CURRENT_STATE.clear(); SEEN_EVENTS.clear(); EVENT_BUS.clear()
    ALERTS.clear(); ARCHIVE.clear()
    position = {
        'event_id': 'ev-demo-pos-101', 'delivery_id': '101',
        'event_type': 'position', 'occurred_at': '2026-11-18T14:00:00Z',
        'status': 'in_transit', 'remaining_distance_km': 10,
        'average_speed_kmh': 40,
        'current_position': {'lat': 4.750, 'lon': -74.07},
        'expected_waypoint': {'lat': 4.710, 'lon': -74.07},
    }
    completion = {
        'event_id': 'ev-demo-done-101', 'delivery_id': '101',
        'event_type': 'delivery_status', 'occurred_at': '2026-11-18T14:20:00Z',
        'status': 'delivered',
    }
    assert json.loads(lambda_ingest({'httpMethod': 'POST', 'body': json.dumps(position)})['body'])['accepted']
    eta = lambda_eta({'detail': EVENT_BUS[-1]})
    alert = lambda_route_alert({'detail': EVENT_BUS[-1]})
    stored = lambda_archive({'detail': EVENT_BUS[-1]})
    assert eta['estimated_minutes'] == 15.0 and alert['alert']
    assert stored['s3_key'].startswith('events/2026/11/18/')
    assert len(ALERTS) == 1 and len(ARCHIVE) == 1
    get = lambda_ingest({'httpMethod': 'GET', 'pathParameters': {'id': '101'}})
    assert json.loads(get['body'])['estimated_minutes'] == 15.0
    assert lambda_ingest({'httpMethod': 'POST', 'body': json.dumps(completion)})['statusCode'] == 202
    assert CURRENT_STATE['101']['status'] == 'delivered'
    assert check_delivery_completed(completion)
    duplicate = lambda_ingest({'httpMethod': 'POST', 'body': json.dumps(completion)})
    assert json.loads(duplicate['body'])['duplicate'] is True
    assert len(EVENT_BUS) == 2
    assert lambda_eta({'detail': completion}) == {'skipped': True}
    assert len(ARCHIVE) == 1  # Archivador recibe el evento si EventBridge lo enruta; probamos la segunda entrega:
    lambda_archive({'detail': EVENT_BUS[-1]})
    assert len(ARCHIVE) == 2
    print('PRUEBA LOCAL AWS COMPLETA: OK')
    print('API -> DynamoDB simulado: estado final = delivered')
    print('ETA simple: 15.0 minutos | alerta de desvío: SI')
    print('Eventos archivados en S3 simulado: 2')
    print('Evento repetido rechazado sin duplicación: OK')
    print('0 conexiones AWS | 0 costos | 0 cambios a PostgreSQL/Snowflake')


if __name__ == '__main__':
    main()
