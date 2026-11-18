"""FleetLogix · Avance 3 · Preparación segura de delta de FACT_DELIVERIES.

Ejecutar desde la raíz del repositorio:
  python Scripts/Avance_3/12_prepare_incremental_fact_delta.py --self-test
  python Scripts/Avance_3/12_prepare_incremental_fact_delta.py

Lee ANALYTICS.FACT_DELIVERIES (solo SELECT) y el CSV local completo.
Genera un CSV únicamente con filas nuevas o cambiadas y un JSON de auditoría.
NO inserta ni actualiza datos en Snowflake o PostgreSQL. NO cargar este delta
mediante el cargador 08, que exige una carga completa de 400.000 entregas.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
PREPARED_DIR = ROOT / 'data' / 'staging' / 'avance_3' / 'prepared'
SOURCE_CSV = PREPARED_DIR / 'fact_deliveries.csv'
SOURCE_AUDIT = PREPARED_DIR / 'fact_deliveries_audit.json'
DELTA_DIR = ROOT / 'data' / 'staging' / 'avance_3' / 'incremental'
DELTA_CSV = DELTA_DIR / 'fact_deliveries_delta.csv'
DELTA_AUDIT = DELTA_DIR / 'fact_deliveries_delta_audit.json'

EXPECTED_COLUMNS = [
    'DELIVERY_ID', 'TRIP_ID', 'TRACKING_NUMBER', 'DATE_KEY',
    'DELIVERY_HOUR', 'VEHICLE_ID', 'DRIVER_ID', 'ROUTE_ID',
    'CUSTOMER_BK', 'DEPARTURE_DATETIME', 'SCHEDULED_DATETIME',
    'DELIVERED_DATETIME', 'DELIVERY_COUNT', 'PACKAGE_WEIGHT_KG',
    'DELIVERY_DURATION_MINUTES', 'SCHEDULE_VARIANCE_MINUTES',
    'IS_ON_TIME', 'ALLOCATED_DISTANCE_KM', 'ALLOCATED_FUEL_LITERS',
    'ALLOCATION_METHOD', 'ESTIMATED_REVENUE_COP',
    'REVENUE_POLICY_VERSION', 'SOURCE_ROW_HASH',
]
REQUIRED_CONFIG = (
    'SNOWFLAKE_ACCOUNT', 'SNOWFLAKE_USER', 'SNOWFLAKE_ROLE',
    'SNOWFLAKE_WAREHOUSE', 'SNOWFLAKE_DATABASE', 'SNOWFLAKE_SCHEMA',
)
HASH_PATTERN = re.compile(r'[0-9a-f]{64}\Z')


def source_hash(row: dict[str, str]) -> str:
    """Misma codificación y función usadas en 07 y 08."""
    payload = json.dumps(
        {key: row[key] for key in EXPECTED_COLUMNS if key != 'SOURCE_ROW_HASH'},
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )
    return sha256(payload.encode('utf-8')).hexdigest()


def check_hash(value: object, label: str) -> str:
    result = str(value or '').strip().lower()
    if not HASH_PATTERN.fullmatch(result):
        raise ValueError(f'Hash inválido: {label}')
    return result


def load_snowflake_hashes() -> dict[int, str]:
    missing = [name for name in REQUIRED_CONFIG if not os.getenv(name)]
    if missing:
        raise RuntimeError(f'Faltan variables en .env: {", ".join(missing)}')

    print('Conectando a Snowflake con OAuth: únicamente SELECT...')
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
    current: dict[int, str] = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT DELIVERY_ID, SOURCE_ROW_HASH
                FROM FLEETLOGIX_DWH.ANALYTICS.FACT_DELIVERIES
            ''')
            while True:
                batch = cursor.fetchmany(10_000)
                if not batch:
                    break
                for delivery_id, row_hash in batch:
                    delivery_id = int(delivery_id)
                    if delivery_id <= 0 or delivery_id in current:
                        raise ValueError(f'ID inválido o duplicado en Snowflake: {delivery_id}')
                    current[delivery_id] = check_hash(row_hash, f'Snowflake {delivery_id}')
                if len(current) % 100_000 == 0:
                    print(f'  Snowflake leído: {len(current):,} entregas')
    finally:
        conn.close()
        print('Conexión Snowflake cerrada.')
    return current


def analyze_and_write_delta(source_csv: Path, current: dict[int, str], delta_csv: Path) -> dict:
    """Filtra filas cambiadas/nuevas con validación de hash; fail-closed si hay ausentes."""
    if not source_csv.is_file():
        raise FileNotFoundError(f'No existe CSV preparado: {source_csv}')
    before = source_csv.stat()
    delta_csv.parent.mkdir(parents=True, exist_ok=True)

    counts = {'source_rows': 0, 'unchanged': 0, 'new': 0, 'modified': 0, 'missing': 0}
    seen: set[int] = set()
    sample_new: list[int] = []
    sample_modified: list[int] = []
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', newline='', encoding='utf-8',
            prefix='.fact_delta_', suffix='.tmp',
            dir=delta_csv.parent, delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)
            writer = csv.DictWriter(temp_handle, fieldnames=EXPECTED_COLUMNS)
            writer.writeheader()

            with source_csv.open('r', encoding='utf-8-sig', newline='') as csv_handle:
                reader = csv.DictReader(csv_handle)
                if reader.fieldnames != EXPECTED_COLUMNS:
                    raise ValueError('El orden/estructura de columnas del CSV no coincide con el ETL V1')
                for line, row in enumerate(reader, start=2):
                    if None in row:
                        raise ValueError(f'Fila con columnas adicionales o mal formadas: {line}')
                    try:
                        delivery_id = int(row['DELIVERY_ID'])
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f'DELIVERY_ID inválido en línea {line}') from exc
                    if delivery_id <= 0 or delivery_id in seen:
                        raise ValueError(f'DELIVERY_ID duplicado o inválido en línea {line}')
                    seen.add(delivery_id)
                    row_hash = check_hash(row['SOURCE_ROW_HASH'], f'CSV línea {line}')
                    if row_hash != source_hash(row):
                        raise ValueError(f'SOURCE_ROW_HASH no coincide con el contenido: línea {line}')
                    counts['source_rows'] += 1
                    existing_hash = current.get(delivery_id)
                    if existing_hash is None:
                        writer.writerow(row)
                        counts['new'] += 1
                        if len(sample_new) < 5:
                            sample_new.append(delivery_id)
                    elif existing_hash != row_hash:
                        writer.writerow(row)
                        counts['modified'] += 1
                        if len(sample_modified) < 5:
                            sample_modified.append(delivery_id)
                    else:
                        counts['unchanged'] += 1
                    if counts['source_rows'] % 100_000 == 0:
                        print(f"  CSV inspeccionado: {counts['source_rows']:,} entregas")

        if before.st_size != source_csv.stat().st_size or before.st_mtime_ns != source_csv.stat().st_mtime_ns:
            raise RuntimeError('El CSV cambió durante la comparación. Regenera y repite la prueba.')
        missing_ids = current.keys() - seen
        counts['missing'] = len(missing_ids)
        if missing_ids:
            raise RuntimeError(
                f'{len(missing_ids):,} entregas de Snowflake ausentes del CSV. '
                f'Ejemplos: {sorted(missing_ids)[:5]}. '
                'La ausencia NO autoriza un borrado; delta NO publicado.'
            )
        if counts['unchanged'] + counts['new'] + counts['modified'] != counts['source_rows']:
            raise AssertionError('No coinciden los conteos de clasificación')
        os.replace(temp_path, delta_csv)
        temp_path = None
        return {
            **counts,
            'snowflake_rows_before': len(current),
            'delta_rows': counts['new'] + counts['modified'],
            'sample_new_ids': sample_new,
            'sample_modified_ids': sample_modified,
        }
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def save_audit(counts: dict) -> None:
    metadata = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'VALIDATED_NOT_LOADED',
        'source_csv': str(SOURCE_CSV),
        'delta_csv': str(DELTA_CSV),
        'method': 'DELIVERY_ID_AND_SOURCE_ROW_HASH',
        'revenue_policy': 'SYNTHETIC_REVENUE_V1',
        'snowflake_modified': False,
        **counts,
    }
    temp_path = DELTA_AUDIT.with_suffix('.json.tmp')
    temp_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp_path, DELTA_AUDIT)


def self_test() -> None:
    """Verifica altas, modificaciones, repeticiones y caso de ausencias, sin red."""
    print('AUTOPRUEBA: 3 entregas ficticias, sin conexión ni cambios reales...')

    def sample(delivery_id: int, weight: str) -> dict[str, str]:
        row = {name: '' for name in EXPECTED_COLUMNS}
        row.update({
            'DELIVERY_ID': str(delivery_id), 'TRIP_ID': '100',
            'PACKAGE_WEIGHT_KG': weight,
            'REVENUE_POLICY_VERSION': 'SYNTHETIC_REVENUE_V1',
        })
        row['SOURCE_ROW_HASH'] = source_hash(row)
        return row

    a = sample(1, '10.000')
    b = sample(2, '20.000')
    c = sample(3, '30.000')
    source_rows = [a, b, c]
    with tempfile.TemporaryDirectory(prefix='fleetlogix_incremental_test_') as temp:
        base = Path(temp)
        source = base / 'synthetic_source.csv'
        delta = base / 'synthetic_delta.csv'
        with source.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPECTED_COLUMNS)
            writer.writeheader()
            writer.writerows(source_rows)

        # ID 1 no cambió; ID 2 cambió; ID 3 es nuevo.
        initial = {1: a['SOURCE_ROW_HASH'], 2: sample(2, '15.000')['SOURCE_ROW_HASH']}
        counts = analyze_and_write_delta(source, initial, delta)
        assert (counts['unchanged'], counts['modified'], counts['new'], counts['delta_rows']) == (1, 1, 1, 2)
        with delta.open('r', encoding='utf-8', newline='') as handle:
            selected = {int(row['DELIVERY_ID']) for row in csv.DictReader(handle)}
        assert selected == {2, 3}, selected
        print('  Caso nuevos + modificados: 1 nueva, 1 modificada, 1 sin cambio — OK')

        updated = {int(row['DELIVERY_ID']): row['SOURCE_ROW_HASH'] for row in source_rows}
        repeat = analyze_and_write_delta(source, updated, delta)
        assert (repeat['unchanged'], repeat['modified'], repeat['new'], repeat['delta_rows']) == (3, 0, 0, 0)
        with delta.open('r', encoding='utf-8', newline='') as handle:
            assert sum(1 for _ in csv.DictReader(handle)) == 0
        print('  Caso idempotente: 0 filas de delta — OK')

        try:
            analyze_and_write_delta(source, {**updated, 4: 'a' * 64}, delta)
        except RuntimeError as exc:
            assert 'ausentes del CSV' in str(exc)
        else:
            raise AssertionError('Una ausencia debería bloquear la publicación')
        print('  Caso ausencia de origen: detectada y bloqueada — OK')
    print('AUTOPRUEBA APROBADA: ninguna tabla ni CSV de FleetLogix fue modificado.')


def main():
    parser = argparse.ArgumentParser(description='Prepara un delta de FACT_DELIVERIES sin cargarlo')
    parser.add_argument('--self-test', action='store_true', help='Solo ejemplos sintéticos locales')
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    print('FleetLogix | PREPARE_INCREMENTAL_FACT_DELTA | SIN MERGE')
    if not SOURCE_AUDIT.is_file():
        raise FileNotFoundError('Falta fact_deliveries_audit.json. Ejecuta antes 07_extract_transform_fact_deliveries.py')
    audit = json.loads(SOURCE_AUDIT.read_text(encoding='utf-8'))
    if audit.get('status') != 'VALIDATED' or audit.get('revenue_policy') != 'SYNTHETIC_REVENUE_V1':
        raise ValueError('Auditoría del CSV inválida o política de ingresos diferente')

    current = load_snowflake_hashes()
    stats = analyze_and_write_delta(SOURCE_CSV, current, DELTA_CSV)
    if audit.get('prepared_delivery_count') != stats['source_rows']:
        DELTA_CSV.unlink(missing_ok=True)
        raise ValueError('Filas del CSV no coinciden con la auditoría del transformador')
    save_audit(stats)
    print('\nRESULTADO DEL DELTA')
    print(f"CSV fuente: {stats['source_rows']:,}")
    print(f"Snowflake existente: {stats['snowflake_rows_before']:,}")
    print(f"Sin cambios: {stats['unchanged']:,}")
    print(f"Nuevas: {stats['new']:,}")
    print(f"Modificadas: {stats['modified']:,}")
    print(f"Ausentes: {stats['missing']:,}")
    print(f"Filas en delta: {stats['delta_rows']:,}")
    print(f'Delta: {DELTA_CSV}')
    print(f'Auditoría: {DELTA_AUDIT}')
    if stats['delta_rows'] == 0:
        print('DELTA VACÍO: el CSV contiene únicamente el encabezado.')
    print('SIN CAMBIOS EN SNOWFLAKE: no se ejecutó PUT, COPY INTO ni MERGE.')
    print('NO USES el cargador 08 para aplicar este archivo incremental.')


if __name__ == '__main__':
    main()
