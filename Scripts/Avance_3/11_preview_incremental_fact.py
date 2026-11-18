"""FleetLogix Avance 3: previsualizacion SOLO LECTURA de cambios de hechos.

Compara DELIVERY_ID + SOURCE_ROW_HASH del CSV ya preparado con
ANALYTICS.FACT_DELIVERIES de Snowflake. No escribe en Snowflake ni en archivos.
Esta prueba NO es un pipeline incremental completo ni sustituye CDC.
"""

import csv
import os
import re
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / '.env')
CSV_PATH = PROJECT_ROOT / 'data' / 'staging' / 'avance_3' / 'prepared' / 'fact_deliveries.csv'
REQUIRED_CONFIG = (
    'SNOWFLAKE_ACCOUNT',
    'SNOWFLAKE_USER',
    'SNOWFLAKE_ROLE',
    'SNOWFLAKE_WAREHOUSE',
    'SNOWFLAKE_DATABASE',
    'SNOWFLAKE_SCHEMA',
)
HASH_PATTERN = re.compile(r'[0-9a-f]{64}\Z')


def read_snapshot():
    if not CSV_PATH.is_file():
        raise FileNotFoundError(f'No se encontró el CSV: {CSV_PATH}')

    rows = {}
    with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = {'DELIVERY_ID', 'SOURCE_ROW_HASH'} - columns
        if missing:
            raise ValueError(f'Faltan columnas en CSV: {sorted(missing)}')

        for line_number, record in enumerate(reader, start=2):
            try:
                delivery_id = int((record.get('DELIVERY_ID') or '').strip())
            except ValueError as exc:
                raise ValueError(f'DELIVERY_ID inválido en línea {line_number}') from exc
            if delivery_id <= 0:
                raise ValueError(f'DELIVERY_ID no positivo en línea {line_number}')
            row_hash = (record.get('SOURCE_ROW_HASH') or '').strip().lower()
            if not HASH_PATTERN.fullmatch(row_hash):
                raise ValueError(f'SOURCE_ROW_HASH inválido en línea {line_number}')
            if delivery_id in rows:
                raise ValueError(f'DELIVERY_ID duplicado en CSV: {delivery_id}')
            rows[delivery_id] = row_hash

            if len(rows) % 100_000 == 0:
                print(f'  CSV leído: {len(rows):,} entregas')

    if not rows:
        raise ValueError('El CSV está vacío.')
    return rows


def read_snowflake_snapshot():
    missing = [key for key in REQUIRED_CONFIG if not os.getenv(key)]
    if missing:
        raise RuntimeError(f'Faltan variables en .env: {", ".join(missing)}')

    print('Conectando a Snowflake con OAuth (solo SELECT)...')
    conn = snowflake.connector.connect(
        account=os.environ['SNOWFLAKE_ACCOUNT'],
        user=os.environ['SNOWFLAKE_USER'],
        authenticator='OAUTH_AUTHORIZATION_CODE',
        role=os.environ['SNOWFLAKE_ROLE'],
        warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
        database=os.environ['SNOWFLAKE_DATABASE'],
        schema=os.environ['SNOWFLAKE_SCHEMA'],
        login_timeout=120,
    )
    existing = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT DELIVERY_ID, SOURCE_ROW_HASH
                FROM ANALYTICS.FACT_DELIVERIES
            ''')
            while True:
                batch = cursor.fetchmany(10_000)
                if not batch:
                    break
                for delivery_id, row_hash in batch:
                    delivery_id = int(delivery_id)
                    if delivery_id in existing:
                        raise ValueError(f'DELIVERY_ID duplicado en Snowflake: {delivery_id}')
                    hash_value = str(row_hash or '').strip().lower()
                    if not HASH_PATTERN.fullmatch(hash_value):
                        raise ValueError(f'Hash inválido en Snowflake para DELIVERY_ID {delivery_id}')
                    existing[delivery_id] = hash_value
                if len(existing) % 100_000 == 0:
                    print(f'  Snowflake leído: {len(existing):,} entregas')
    finally:
        conn.close()
        print('Conexión Snowflake cerrada.')
    return existing


def main():
    print('FleetLogix | PREVIEW_INCREMENTAL_FACT | SOLO LECTURA')
    print('Comparando el CSV preparado con los hashes de FACT_DELIVERIES...')
    prepared = read_snapshot()
    current = read_snowflake_snapshot()

    new_ids = prepared.keys() - current.keys()
    missing_ids = current.keys() - prepared.keys()
    common_ids = prepared.keys() & current.keys()
    changed_ids = [key for key in common_ids if prepared[key] != current[key]]
    unchanged_count = len(common_ids) - len(changed_ids)

    print('\nRESULTADO DE COMPARACIÓN')
    print(f'CSV preparado: {len(prepared):,}')
    print(f'Snowflake: {len(current):,}')
    print(f'Sin cambios: {unchanged_count:,}')
    print(f'Nuevas: {len(new_ids):,}')
    print(f'Modificadas: {len(changed_ids):,}')
    print(f'Ausentes del CSV actual: {len(missing_ids):,}')

    if new_ids:
        print(f'  Ejemplos de nuevas: {sorted(new_ids)[:5]}')
    if changed_ids:
        print(f'  Ejemplos de modificadas: {sorted(changed_ids)[:5]}')
    if missing_ids:
        print(f'  Ejemplos ausentes: {sorted(missing_ids)[:5]}')
        print('  ATENCIÓN: ausencia en el CSV NO implica borrar una entrega.')

    if not new_ids and not changed_ids and not missing_ids:
        print('\nSNAPSHOT SIN CAMBIOS: no habría filas de hechos para aplicar.')
    else:
        print('\nHay diferencias: revisar antes de diseñar la aplicación del delta.')
    print('MODO SOLO LECTURA: ninguna tabla ni CSV fueron modificados.')


if __name__ == '__main__':
    main()
