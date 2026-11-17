"""FleetLogix Avance 3: validación y carga idempotente de FACT_DELIVERIES.

Uso desde la raíz del proyecto:
    python Scripts/Avance_3/08_load_fact_deliveries.py
    python Scripts/Avance_3/08_load_fact_deliveries.py --execute

Requiere CSV y auditoría generados por 07_extract_transform_fact_deliveries.py.
Sin --execute no abre conexión a Snowflake ni modifica datos.
OAuth mediante navegador: uso INTERACTIVO solamente, no programador desatendido.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
PREPARED = ROOT / "data" / "staging" / "avance_3" / "prepared"
CSV_PATH = PREPARED / "fact_deliveries.csv"
AUDIT_PATH = PREPARED / "fact_deliveries_audit.json"
EXPECTED_ROWS = 400_000
EXPECTED_TRIPS = 100_000
EXPECTED_DISTANCE = Decimal("4701486.980000")
EXPECTED_FUEL = Decimal("633064.820000")
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

COLS = [
    "DELIVERY_ID", "TRIP_ID", "TRACKING_NUMBER", "DATE_KEY",
    "DELIVERY_HOUR", "VEHICLE_ID", "DRIVER_ID", "ROUTE_ID",
    "CUSTOMER_BK", "DEPARTURE_DATETIME", "SCHEDULED_DATETIME",
    "DELIVERED_DATETIME", "DELIVERY_COUNT", "PACKAGE_WEIGHT_KG",
    "DELIVERY_DURATION_MINUTES", "SCHEDULE_VARIANCE_MINUTES",
    "IS_ON_TIME", "ALLOCATED_DISTANCE_KM", "ALLOCATED_FUEL_LITERS",
    "ALLOCATION_METHOD", "ESTIMATED_REVENUE_COP",
    "REVENUE_POLICY_VERSION", "SOURCE_ROW_HASH",
]

# Columnas de destino distintas de la surrogate DELIVERY_KEY y timestamps de auditoría.
FACT_COLS = [
    "DELIVERY_ID", "TRIP_ID", "TRACKING_NUMBER", "DATE_KEY", "TIME_KEY",
    "VEHICLE_KEY", "DRIVER_KEY", "ROUTE_KEY", "CUSTOMER_KEY",
    "DEPARTURE_DATETIME", "SCHEDULED_DATETIME", "DELIVERED_DATETIME",
    "DELIVERY_COUNT", "PACKAGE_WEIGHT_KG", "DELIVERY_DURATION_MINUTES",
    "SCHEDULE_VARIANCE_MINUTES", "IS_ON_TIME", "ALLOCATED_DISTANCE_KM",
    "ALLOCATED_FUEL_LITERS", "ALLOCATION_METHOD", "ESTIMATED_REVENUE_COP",
    "REVENUE_POLICY_VERSION", "SOURCE_ROW_HASH",
]

REQUIRED = [
    "DELIVERY_ID", "TRIP_ID", "DATE_KEY", "DELIVERY_HOUR", "VEHICLE_ID",
    "DRIVER_ID", "ROUTE_ID", "CUSTOMER_BK", "DEPARTURE_DATETIME",
    "SCHEDULED_DATETIME", "DELIVERED_DATETIME", "DELIVERY_COUNT",
    "PACKAGE_WEIGHT_KG", "DELIVERY_DURATION_MINUTES",
    "SCHEDULE_VARIANCE_MINUTES", "IS_ON_TIME", "ALLOCATED_DISTANCE_KM",
    "ALLOCATED_FUEL_LITERS", "ALLOCATION_METHOD", "SOURCE_ROW_HASH",
]


# Una única función de hash, compatible con el transformador previo.
def calculate_source_hash(record: dict[str, str]) -> str:
    payload = json.dumps(
        {key: record[key] for key in COLS if key != "SOURCE_ROW_HASH"},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def positive_int(value: str, label: str) -> int:
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError(f"{label}: identificador no válido")
    return int(value)


def decimal_value(value: str, label: str, nonnegative: bool = True) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label}: decimal inválido") from exc
    if not number.is_finite() or (number < 0 if nonnegative else number <= 0):
        raise ValueError(f"{label}: número fuera de rango")
    return number


def validate_local() -> int:
    """Control de calidad local, sin red; asume línea base de 400k/100k."""
    if not CSV_PATH.is_file() or not AUDIT_PATH.is_file():
        raise FileNotFoundError(
            "Falta el CSV o su auditoría. Ejecuta antes 07_extract_transform_fact_deliveries.py"
        )
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    if (
        audit.get("status") != "VALIDATED"
        or audit.get("prepared_delivery_count") != EXPECTED_ROWS
        or audit.get("processed_trip_count") != EXPECTED_TRIPS
        or Decimal(str(audit.get("allocated_distance_km", "-1"))) != EXPECTED_DISTANCE
        or Decimal(str(audit.get("allocated_fuel_liters", "-1"))) != EXPECTED_FUEL
    ):
        raise ValueError("La auditoría no coincide con la línea base verificada")

    seen = set()
    trips = 0
    last_trip = None
    total = 0
    distance = Decimal(0)
    fuel = Decimal(0)
    print("Validando CSV de FACT_DELIVERIES localmente (sin enviar datos)...")
    with CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLS:
            raise ValueError(f"Columnas inesperadas en fact_deliveries.csv: {reader.fieldnames}")
        for row in reader:
            total += 1
            if None in row or any(not row.get(k) for k in REQUIRED):
                raise ValueError(f"Fila {total}: campo obligatorio ausente")
            delivery_id = positive_int(row["DELIVERY_ID"], f"Fila {total}, DELIVERY_ID")
            trip_id = positive_int(row["TRIP_ID"], f"Fila {total}, TRIP_ID")
            for k in ("VEHICLE_ID", "DRIVER_ID", "ROUTE_ID"):
                positive_int(row[k], f"Fila {total}, {k}")
            if delivery_id in seen:
                raise ValueError(f"DELIVERY_ID duplicado: {delivery_id}")
            seen.add(delivery_id)
            if last_trip != trip_id:
                if last_trip is not None and trip_id <= last_trip:
                    raise ValueError("CSV fuera de orden por TRIP_ID")
                trips += 1
                last_trip = trip_id

            try:
                departed = datetime.strptime(row["DEPARTURE_DATETIME"], DATETIME_FORMAT)
                scheduled = datetime.strptime(row["SCHEDULED_DATETIME"], DATETIME_FORMAT)
                delivered = datetime.strptime(row["DELIVERED_DATETIME"], DATETIME_FORMAT)
            except ValueError as exc:
                raise ValueError(f"Fila {total}: fecha/hora inválida") from exc
            if not (datetime(2024, 1, 1) <= delivered < datetime(2031, 1, 1)):
                raise ValueError(f"Fila {total}: fecha fuera de DIM_DATE")
            if delivered < departed or delivered.strftime("%Y%m%d") != row["DATE_KEY"]:
                raise ValueError(f"Fila {total}: fecha de entrega o DATE_KEY inconsistente")
            if str(delivered.hour) != row["DELIVERY_HOUR"]:
                raise ValueError(f"Fila {total}: DELIVERY_HOUR inconsistente")
            if (
                row["DELIVERY_COUNT"] != "1"
                or row["IS_ON_TIME"] not in {"TRUE", "FALSE"}
                or (row["IS_ON_TIME"] == "TRUE") != (delivered <= scheduled)
                or row["ALLOCATION_METHOD"] != "WEIGHT_PROPORTIONAL_V1"
                or row["ESTIMATED_REVENUE_COP"]
                or row["REVENUE_POLICY_VERSION"]
            ):
                raise ValueError(f"Fila {total}: regla de negocio inconsistente")
            decimal_value(row["PACKAGE_WEIGHT_KG"], "PACKAGE_WEIGHT_KG", nonnegative=False)
            decimal_value(row["DELIVERY_DURATION_MINUTES"], "DELIVERY_DURATION_MINUTES")
            try:
                variance = Decimal(row["SCHEDULE_VARIANCE_MINUTES"])
            except InvalidOperation as exc:
                raise ValueError(f"Fila {total}: diferencia horaria no numérica") from exc
            if not variance.is_finite():
                raise ValueError(f"Fila {total}: diferencia horaria no finita")
            distance += decimal_value(row["ALLOCATED_DISTANCE_KM"], "ALLOCATED_DISTANCE_KM")
            fuel += decimal_value(row["ALLOCATED_FUEL_LITERS"], "ALLOCATED_FUEL_LITERS")
            if not SHA_PATTERN.fullmatch(row["CUSTOMER_BK"]):
                raise ValueError(f"Fila {total}: CUSTOMER_BK inválida")
            if not SHA_PATTERN.fullmatch(row["SOURCE_ROW_HASH"]) or (
                row["SOURCE_ROW_HASH"] != calculate_source_hash(row)
            ):
                raise ValueError(f"Fila {total}: SOURCE_ROW_HASH inválido")
            if total % 100_000 == 0:
                print(f"  Filas comprobadas: {total:,}")
    if (total, trips, distance, fuel) != (
        EXPECTED_ROWS, EXPECTED_TRIPS, EXPECTED_DISTANCE, EXPECTED_FUEL
    ):
        raise ValueError(
            f"CSV no concilia: {total} entregas, {trips} viajes, "
            f"{distance} km, {fuel} L"
        )
    print(
        f"CSV OK: {total:,} entregas únicas; {trips:,} viajes; "
        f"{distance:,.6f} km; {fuel:,.6f} L"
    )
    return total


def get_time_hour_expression(cursor) -> str:
    """Descubre de forma conservadora cómo enlazar DIM_TIME con horas 0-23."""
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM FLEETLOGIX_DWH.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='ANALYTICS' AND TABLE_NAME='DIM_TIME'
    """)
    columns = {name.upper(): dtype.upper() for name, dtype in cursor.fetchall()}
    if "TIME_KEY" not in columns:
        raise RuntimeError("DIM_TIME no contiene TIME_KEY")
    candidates = [
        "HOUR_24", "HOUR_OF_DAY", "HOUR_NUMBER", "HOUR", "HOUR_VALUE",
        "TIME_HOUR", "HOUR_NUM", "HOUR_OF_DAY_24", "HOUR_0_23",
        "HOUR_START", "START_HOUR", "DELIVERY_HOUR",
    ]
    found = next((c for c in candidates if c in columns), None)
    if found:
        expr = (
            f"EXTRACT(HOUR FROM tm.{found})"
            if columns[found] == "TIME"
            else f"TO_NUMBER(tm.{found})"
        )
    else:
        timed = next(
            (c for c in ("TIME_VALUE", "TIME_OF_DAY", "START_TIME")
             if c in columns and columns[c] == "TIME"), None
        )
        # TIME_KEY=hora solo se admite si el propio contenido lo demuestra.
        expr = f"EXTRACT(HOUR FROM tm.{timed})" if timed else "TO_NUMBER(tm.TIME_KEY)"

    cursor.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT {expr}), MIN({expr}),
               MAX({expr}), COUNT_IF({expr} IS NULL)
        FROM ANALYTICS.DIM_TIME tm
    """)
    count, distinct_count, min_hour, max_hour, nulls = cursor.fetchone()
    if (count, distinct_count, min_hour, max_hour, nulls) != (24, 24, 0, 23, 0):
        raise RuntimeError(
            "No se pudo verificar una correspondencia 0-23 con DIM_TIME. "
            "Ejecuta DESCRIBE TABLE ANALYTICS.DIM_TIME y revisa la columna de hora. "
            f"Columnas encontradas: {list(columns)}"
        )
    print(f"DIM_TIME: correspondencia de 24 horas verificada ({expr}).")
    return expr


def check_dimension_business_keys(cursor) -> None:
    checks = [
        ("ANALYTICS.DIM_CUSTOMER", "CUSTOMER_BK"),
        ("ANALYTICS.DIM_VEHICLE", "VEHICLE_ID"),
        ("ANALYTICS.DIM_ROUTE", "ROUTE_ID"),
        ("ANALYTICS.DIM_DATE", "DATE_KEY"),
        ("ANALYTICS.DIM_TIME", "TIME_KEY"),
    ]
    for table, business_key in checks:
        cursor.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT {business_key}
                FROM {table}
                GROUP BY {business_key}
                HAVING COUNT(*) > 1
            )
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError(f"Clave duplicada en {table}: {business_key}")
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT DRIVER_ID FROM ANALYTICS.DIM_DRIVER
            WHERE IS_CURRENT=TRUE GROUP BY DRIVER_ID HAVING COUNT(*)>1
        )
    """)
    if cursor.fetchone()[0]:
        raise RuntimeError("DIM_DRIVER presenta más de una versión actual por conductor")


def build_resolved_sql(time_expr: str) -> str:
    def ts(name: str) -> str:
        return f"TO_TIMESTAMP_NTZ(s.{name}, 'YYYY-MM-DD HH24:MI:SS.FF6')"

    return f"""
        CREATE TEMPORARY TABLE TMP_FLEETLOGIX_FACT_RESOLVED AS
        SELECT
            TO_NUMBER(s.DELIVERY_ID) AS DELIVERY_ID,
            TO_NUMBER(s.TRIP_ID) AS TRIP_ID,
            s.TRACKING_NUMBER,
            dt.DATE_KEY,
            tm.TIME_KEY,
            v.VEHICLE_KEY,
            dr.DRIVER_KEY,
            rt.ROUTE_KEY,
            cu.CUSTOMER_KEY,
            {ts('DEPARTURE_DATETIME')} AS DEPARTURE_DATETIME,
            {ts('SCHEDULED_DATETIME')} AS SCHEDULED_DATETIME,
            {ts('DELIVERED_DATETIME')} AS DELIVERED_DATETIME,
            TO_NUMBER(s.DELIVERY_COUNT) AS DELIVERY_COUNT,
            TO_DECIMAL(s.PACKAGE_WEIGHT_KG,18,3) AS PACKAGE_WEIGHT_KG,
            TO_DECIMAL(s.DELIVERY_DURATION_MINUTES,18,3) AS DELIVERY_DURATION_MINUTES,
            TO_DECIMAL(s.SCHEDULE_VARIANCE_MINUTES,18,3) AS SCHEDULE_VARIANCE_MINUTES,
            TO_BOOLEAN(s.IS_ON_TIME) AS IS_ON_TIME,
            TO_DECIMAL(s.ALLOCATED_DISTANCE_KM,20,6) AS ALLOCATED_DISTANCE_KM,
            TO_DECIMAL(s.ALLOCATED_FUEL_LITERS,20,6) AS ALLOCATED_FUEL_LITERS,
            s.ALLOCATION_METHOD,
            TRY_TO_DECIMAL(s.ESTIMATED_REVENUE_COP,18,2) AS ESTIMATED_REVENUE_COP,
            s.REVENUE_POLICY_VERSION,
            s.SOURCE_ROW_HASH
        FROM TMP_FLEETLOGIX_FACT_RAW s
        LEFT JOIN ANALYTICS.DIM_DATE dt
          ON dt.DATE_KEY=TO_NUMBER(s.DATE_KEY)
        LEFT JOIN ANALYTICS.DIM_TIME tm
          ON {time_expr}=TO_NUMBER(s.DELIVERY_HOUR)
        LEFT JOIN ANALYTICS.DIM_VEHICLE v
          ON v.VEHICLE_ID=TO_NUMBER(s.VEHICLE_ID)
        LEFT JOIN ANALYTICS.DIM_DRIVER dr
          ON dr.DRIVER_ID=TO_NUMBER(s.DRIVER_ID)
         AND {ts('DELIVERED_DATETIME')} >= dr.VALID_FROM
         AND (dr.VALID_TO IS NULL OR {ts('DELIVERED_DATETIME')} < dr.VALID_TO)
        LEFT JOIN ANALYTICS.DIM_ROUTE rt
          ON rt.ROUTE_ID=TO_NUMBER(s.ROUTE_ID)
        LEFT JOIN ANALYTICS.DIM_CUSTOMER cu
          ON cu.CUSTOMER_BK=s.CUSTOMER_BK
    """


def check_staging(cursor, expected: int) -> None:
    cursor.execute("""
        SELECT COUNT(*), COUNT(DISTINCT DELIVERY_ID), COUNT(DISTINCT TRIP_ID),
               COUNT_IF(DELIVERY_ID IS NULL OR TRIP_ID IS NULL OR DATE_KEY IS NULL
                  OR DELIVERY_HOUR IS NULL OR CUSTOMER_BK IS NULL OR SOURCE_ROW_HASH IS NULL)
        FROM TMP_FLEETLOGIX_FACT_RAW
    """)
    total, distinct_deliveries, trips, missing = cursor.fetchone()
    print(f"Staging RAW: {total:,} filas, {distinct_deliveries:,} entregas únicas, {trips:,} viajes")
    if (total, distinct_deliveries, trips, missing) != (expected, expected, EXPECTED_TRIPS, 0):
        raise RuntimeError("La tabla temporal RAW no pasó las validaciones")


def check_resolved(cursor, expected: int) -> None:
    cursor.execute("""
        SELECT
            COUNT(*), COUNT(DISTINCT DELIVERY_ID), COUNT(DISTINCT TRIP_ID),
            COUNT_IF(
                DATE_KEY IS NULL OR TIME_KEY IS NULL OR VEHICLE_KEY IS NULL
                OR DRIVER_KEY IS NULL OR ROUTE_KEY IS NULL OR CUSTOMER_KEY IS NULL
            ),
            SUM(ALLOCATED_DISTANCE_KM), SUM(ALLOCATED_FUEL_LITERS),
            COUNT_IF(ESTIMATED_REVENUE_COP IS NOT NULL OR REVENUE_POLICY_VERSION IS NOT NULL)
        FROM TMP_FLEETLOGIX_FACT_RESOLVED
    """)
    total, distinct_delivery, trips, unresolved, dist, fuel, revenue_present = cursor.fetchone()
    print(
        f"Relaciones dimensionales: {total:,} filas; {unresolved} sin clave; "
        f"{dist:,.6f} km; {fuel:,.6f} L"
    )
    if (
        total != expected or distinct_delivery != expected or trips != EXPECTED_TRIPS
        or unresolved != 0 or Decimal(str(dist)) != EXPECTED_DISTANCE
        or Decimal(str(fuel)) != EXPECTED_FUEL or revenue_present != 0
    ):
        raise RuntimeError(
            "Las dimensiones no cubren todas las entregas o no concilian métricas. "
            "No se modificó FACT_DELIVERIES."
        )


def merge_facts(cursor) -> tuple[int, int]:
    update_cols = [c for c in FACT_COLS if c != "DELIVERY_ID"]
    updates = ",\n                ".join(f"t.{c}=s.{c}" for c in update_cols)
    inserts = ", ".join(FACT_COLS)
    values = ", ".join(f"s.{c}" for c in FACT_COLS)
    cursor.execute(f"""
        MERGE INTO ANALYTICS.FACT_DELIVERIES t
        USING TMP_FLEETLOGIX_FACT_RESOLVED s
          ON t.DELIVERY_ID=s.DELIVERY_ID
        WHEN MATCHED AND (
             t.SOURCE_ROW_HASH IS DISTINCT FROM s.SOURCE_ROW_HASH
          OR t.DATE_KEY IS DISTINCT FROM s.DATE_KEY
          OR t.TIME_KEY IS DISTINCT FROM s.TIME_KEY
          OR t.VEHICLE_KEY IS DISTINCT FROM s.VEHICLE_KEY
          OR t.DRIVER_KEY IS DISTINCT FROM s.DRIVER_KEY
          OR t.ROUTE_KEY IS DISTINCT FROM s.ROUTE_KEY
          OR t.CUSTOMER_KEY IS DISTINCT FROM s.CUSTOMER_KEY
        ) THEN UPDATE SET
            {updates},
            t.DW_UPDATED_AT=CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
        WHEN NOT MATCHED THEN INSERT ({inserts})
        VALUES ({values})
    """)
    result = cursor.fetchone()
    return int(result[0]), int(result[1])


def check_target(cursor, expected: int) -> None:
    cursor.execute("""
        SELECT
            COUNT(*), COUNT(DISTINCT DELIVERY_ID),
            SUM(ALLOCATED_DISTANCE_KM), SUM(ALLOCATED_FUEL_LITERS),
            COUNT_IF(DATE_KEY IS NULL OR TIME_KEY IS NULL OR VEHICLE_KEY IS NULL
                 OR DRIVER_KEY IS NULL OR ROUTE_KEY IS NULL OR CUSTOMER_KEY IS NULL)
        FROM ANALYTICS.FACT_DELIVERIES
    """)
    total, uniques, distance, fuel, missing = cursor.fetchone()
    if (
        (total, uniques, missing) != (expected, expected, 0)
        or Decimal(str(distance)) != EXPECTED_DISTANCE
        or Decimal(str(fuel)) != EXPECTED_FUEL
    ):
        raise RuntimeError("La auditoría posterior al MERGE falló")
    print(f"FACT_DELIVERIES: {total:,} entregas, {distance:,.6f} km, {fuel:,.6f} L")


def load_to_snowflake(expected: int) -> None:
    import snowflake.connector

    required_env = [
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
    ]
    missing = [k for k in required_env if not os.getenv(k)]
    if missing:
        raise RuntimeError("Faltan variables del .env: " + ", ".join(missing))

    uri = ("file://" + CSV_PATH.resolve().as_posix()).replace("'", "''")
    print("Conectando con Snowflake mediante navegador...")
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="OAUTH_AUTHORIZATION_CODE",
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        login_timeout=120,
        enable_server_session_keep_alive_auto_detection=False,
    )
    in_transaction = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ROLE()")
            db, schema, role = cur.fetchone()
            if (db, schema, role) != ("FLEETLOGIX_DWH", "ANALYTICS", "SYSADMIN"):
                raise RuntimeError(f"Contexto Snowflake inesperado: {db}/{schema}/{role}")
            time_expr = get_time_hour_expression(cur)
            check_dimension_business_keys(cur)

            # Preparar TODOS los objetos DDL antes de BEGIN (Snowflake hace commit implícito con DDL).
            raw_columns = ",\n".join(f"{name} VARCHAR(500)" for name in COLS)
            cur.execute(f"CREATE TEMPORARY TABLE TMP_FLEETLOGIX_FACT_RAW ({raw_columns})")
            cur.execute("""
                CREATE TEMPORARY STAGE TMP_FLEETLOGIX_FACT_FILES
                FILE_FORMAT = (
                    TYPE=CSV FIELD_DELIMITER=',' SKIP_HEADER=1
                    FIELD_OPTIONALLY_ENCLOSED_BY='"' MULTI_LINE=TRUE
                    ENCODING='UTF8' EMPTY_FIELD_AS_NULL=TRUE NULL_IF=('')
                    ESCAPE_UNENCLOSED_FIELD=NONE
                )
            """)
            print("Staging temporal creado.")

            cur.execute(
                f"PUT '{uri}' @TMP_FLEETLOGIX_FACT_FILES "
                "AUTO_COMPRESS=TRUE OVERWRITE=TRUE PARALLEL=4"
            )
            put_results = cur.fetchall()
            statuses = [str(r[6]).upper() for r in put_results]
            if not statuses or any(x not in {"UPLOADED", "SKIPPED"} for x in statuses):
                raise RuntimeError(f"PUT no confirmado: {statuses}")
            print("PUT confirmado: " + ", ".join(statuses))

            cur.execute("""
                COPY INTO TMP_FLEETLOGIX_FACT_RAW
                FROM @TMP_FLEETLOGIX_FACT_FILES
                ON_ERROR=ABORT_STATEMENT
            """)
            copy_results = cur.fetchall()
            # COPY INTO devuelve (file, status, rows_parsed, rows_loaded, ...).
            if not copy_results or any(str(row[1]).upper() != "LOADED" for row in copy_results):
                raise RuntimeError("COPY INTO devolvió estados no satisfactorios")
            loaded = sum(int(row[3]) for row in copy_results)
            if loaded != expected:
                raise RuntimeError(f"COPY INTO transfirió {loaded} de {expected} filas")
            print(f"COPY INTO confirmado: {loaded:,} filas")
            check_staging(cur, expected)
            cur.execute(build_resolved_sql(time_expr))
            check_resolved(cur, expected)

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT DELIVERY_ID) FROM ANALYTICS.FACT_DELIVERIES")
            prior, prior_unique = cur.fetchone()
            if prior != prior_unique or prior not in (0, expected):
                raise RuntimeError("FACT_DELIVERIES presenta duplicados o volumen previo inesperado")
            print(f"FACT_DELIVERIES antes: {prior:,} filas")

            try:
                cur.execute("BEGIN")
                in_transaction = True
                inserted, updated = merge_facts(cur)
                print(f"MERGE: {inserted:,} insertadas, {updated:,} actualizadas")
                check_target(cur, expected)
                cur.execute("COMMIT")
                in_transaction = False
                print("CARGA CONFIRMADA (COMMIT)")
            except Exception:
                if in_transaction:
                    cur.execute("ROLLBACK")
                    print("CARGA REVERTIDA (ROLLBACK)")
                    in_transaction = False
                raise
    finally:
        if in_transaction:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK")
        conn.close()
        print("Conexión Snowflake cerrada.")


def main() -> None:
    parser = argparse.ArgumentParser(description="FleetLogix: carga validada FACT_DELIVERIES")
    parser.add_argument("--execute", action="store_true", help="Sube CSV y aplica MERGE en Snowflake")
    args = parser.parse_args()
    count = validate_local()
    if args.execute:
        load_to_snowflake(count)
    else:
        print("MODO VALIDACIÓN: Snowflake no se modificó.")
        print("Para cargar, ejecutar de nuevo con --execute.")


if __name__ == "__main__":
    main()
