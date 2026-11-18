"""Handler ilustrativo API Gateway -> Lambda -> DynamoDB/S3.
El modo local por defecto no escribe en AWS. La escritura requiere
DEMO_AWS_WRITE=enabled y variables de nombres de recursos reales.
"""
from __future__ import annotations
import json, os
from datetime import datetime,timezone
from .delivery_logic import validate_event, check_delivery_completed


def lambda_handler(event, context=None):
    body=event.get('body',event)
    if isinstance(body,str): body=json.loads(body)
    validated=validate_event(body)
    status=check_delivery_completed(body) if body.get('event_type')=='delivery_status' else {'completed':False}
    if os.getenv('DEMO_AWS_WRITE')!='enabled':
        return {'statusCode':200,'body':json.dumps({'mode':'dry-run','event':validated['event_id'],'status':status})}
    # Escritura DEMO en AWS: se requiere rol Lambda IAM específico, no credenciales en código.
    import boto3
    table_name=os.environ['FLEETLOGIX_DDB_TABLE']; bucket=os.environ['FLEETLOGIX_EVENTS_BUCKET']
    dynamo=boto3.resource('dynamodb').Table(table_name)
    s3=boto3.client('s3')
    # Idempotencia exacta de evento requiere registro condicional de EVENT_ID en tabla de eventos
    # (aquí solo es un ejemplo base; no afirmar garantía end-to-end).
    dynamo.put_item(Item={'delivery_id':validated['delivery_id'],
                          'event_id':validated['event_id'],
                          'last_event_type':validated['event_type'],
                          'occurred_at':validated['occurred_at']})
    date=validated['occurred_at'][:10].replace('-','/')
    key=f'events/{date}/{validated["event_id"]}.json'
    s3.put_object(Bucket=bucket,Key=key,Body=json.dumps(validated).encode('utf8'),
                  ContentType='application/json')
    return {'statusCode':202,'body':json.dumps({'accepted':True,'event_id':validated['event_id']})}
