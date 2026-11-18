"""Cuatro puntos de entrada AWS Lambda (demostración educativa).

Handlers para AWS: lambda_ingest, lambda_eta, lambda_route_alert, lambda_archive.
LOCAL_DEMO=1 (por defecto): almacena eventos en estructuras de memoria locales.
LOCAL_DEMO=0: requiere boto3, recursos AWS y permisos IAM. NO desplegado.

No ofrece consistencia transaccional entre DynamoDB y EventBridge en caso de
fallos parciales. Producción requiere patrón outbox/reintentos y seguridad adicional.
"""
import json
import os
from .logic import (validate_event, check_delivery_completed,
                    estimate_eta, detect_route_deviation)

CURRENT_STATE = {}
SEEN_EVENTS = set()
EVENT_BUS = []
ALERTS = []
ARCHIVE = {}


def local_mode():
    return os.getenv('LOCAL_DEMO', '1') != '0'


def response(code, payload):
    return {'statusCode': code, 'headers': {'content-type': 'application/json'},
            'body': json.dumps(payload, ensure_ascii=False)}


def extract_detail(event):
    return event.get('detail', event)


def lambda_ingest(event, context=None):
    """Lambda 1. API POST /events y GET /deliveries/{id}. Estado inmediato en DDB."""
    request = event.get('requestContext', {}).get('http', {})
    method = request.get('method', event.get('httpMethod', 'POST'))
    if method == 'GET':
        delivery_id = (event.get('pathParameters') or {}).get('id')
        if not delivery_id:
            return response(400, {'error': 'delivery id requerido'})
        if local_mode():
            state = CURRENT_STATE.get(str(delivery_id))
        else:
            import boto3
            table = boto3.resource('dynamodb').Table(os.environ['DDB_TABLE'])
            state = table.get_item(Key={'pk': f'DELIVERY#{delivery_id}', 'sk': 'STATE'}).get('Item')
        return response(200 if state else 404, state or {'error': 'no encontrada'})
    if method != 'POST':
        return response(405, {'error': 'método no admitido'})
    try:
        body = event.get('body', event)
        if isinstance(body, str):
            body = json.loads(body)
        msg = validate_event(body)
        completed = check_delivery_completed(msg)
        if msg['event_type'] == 'delivery_status' and msg.get('status') not in ('in_transit', 'delayed', 'delivered', 'completed'):
            return response(400, {'error': 'status no admitido'})
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return response(400, {'error': str(exc)})
    state = {'delivery_id': msg['delivery_id'],
             'status': 'delivered' if completed else msg.get('status', 'in_transit'),
             'updated_at': msg['occurred_at'], 'last_event_id': msg['event_id']}
    if local_mode():
        if msg['event_id'] in SEEN_EVENTS:
            return response(200, {'accepted': True, 'duplicate': True, 'event_id': msg['event_id']})
        SEEN_EVENTS.add(msg['event_id'])
        CURRENT_STATE[msg['delivery_id']] = state
        EVENT_BUS.append(msg)
    else:
        import boto3
        from botocore.exceptions import ClientError
        table = boto3.resource('dynamodb').Table(os.environ['DDB_TABLE'])
        try:
            table.put_item(Item={'pk': f'EVENT#{msg["event_id"]}', 'sk': 'SEEN',
                                 'delivery_id': msg['delivery_id']},
                           ConditionExpression='attribute_not_exists(pk)')
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
                return response(200, {'accepted': True, 'duplicate': True, 'event_id': msg['event_id']})
            raise
        table.put_item(Item={'pk': f'DELIVERY#{msg["delivery_id"]}', 'sk': 'STATE', **state})
        sent = boto3.client('events').put_events(Entries=[{
            'Source': 'fleetlogix.mobile', 'DetailType': 'DeliveryEvent',
            'Detail': json.dumps(msg), 'EventBusName': os.environ['EVENT_BUS']}])
        if sent.get('FailedEntryCount', 0):
            raise RuntimeError('Error parcial al publicar evento; reconciliar')
    return response(202, {'accepted': True, 'event_id': msg['event_id'],
                          'delivery_id': msg['delivery_id'], 'status': state['status']})


def lambda_eta(event, context=None):
    """Lambda 2. EventBridge -> ETA para eventos de posición."""
    msg = extract_detail(event)
    if msg.get('event_type') != 'position':
        return {'skipped': True}
    result = estimate_eta(msg)
    if local_mode():
        state = CURRENT_STATE.setdefault(str(msg['delivery_id']), {'delivery_id': str(msg['delivery_id'])})
        state.update(result)
    else:
        import boto3
        boto3.resource('dynamodb').Table(os.environ['DDB_TABLE']).update_item(
            Key={'pk': f'DELIVERY#{msg["delivery_id"]}', 'sk': 'STATE'},
            UpdateExpression='SET eta_utc=:eta, estimated_minutes=:mins',
            ExpressionAttributeValues={':eta': result['eta_utc'], ':mins': str(result['estimated_minutes'])})
    return result


def lambda_route_alert(event, context=None):
    """Lambda 3. Detecta distancia al waypoint y emite alerta SNS si > 2 km."""
    msg = extract_detail(event)
    if msg.get('event_type') != 'position':
        return {'skipped': True}
    result = detect_route_deviation(msg)
    if result['alert']:
        alert = {'delivery_id': str(msg['delivery_id']), 'event_id': msg['event_id'], **result}
        if local_mode():
            ALERTS.append(alert)
        else:
            import boto3
            boto3.client('sns').publish(TopicArn=os.environ['SNS_TOPIC_ARN'],
                Subject='FleetLogix: desvío de ruta', Message=json.dumps(alert))
    return result


def lambda_archive(event, context=None):
    """Lambda 4. Evento JSON en S3, particionado por fecha UTC."""
    msg = extract_detail(event)
    msg = validate_event(msg)
    date = msg['occurred_at'][:10].replace('-', '/')
    key = f'events/{date}/{msg["event_id"]}.json'
    content = json.dumps(msg, ensure_ascii=False, sort_keys=True).encode('utf-8')
    if local_mode():
        ARCHIVE[key] = content
    else:
        import boto3
        boto3.client('s3').put_object(Bucket=os.environ['EVENTS_BUCKET'],
            Key=key, Body=content, ContentType='application/json',
            ServerSideEncryption='AES256')
    return {'archived': True, 's3_key': key}
