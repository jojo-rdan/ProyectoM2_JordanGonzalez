"""FleetLogix - Avance 3: carga inicial e incremental de dimensiones maestras.

Ejecutar desde la raíz del repositorio:
    python Scripts/Avance_3/04_load_master_dimensions.py

Requiere los CSV producidos por 03_transform_master_data.py.
Usa OAuth interactivo para pruebas locales; NO apto para cron desatendido.
"""

from __future__ import annotations

import csv
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
PREPARED = ROOT / "data" / "staging" / "avance_3" / "prepared"

# Importante: las fechas de vigencia se guardan en UTC como TIMESTAMP_NTZ.
FIRST_KNOWN = "1900-01-01 00:00:00"

SPECS = {
    "vehicle": {
        "file": "dim_vehicle.csv",
        "temp": "STAGING.TMP_VEHICLE_LOAD",
        "fields": (
            "VEHICLE_ID", "LICENSE_PLATE", "VEHICLE_TYPE", "CAPACITY_KG",
            "FUEL_TYPE", "ACQUISITION_DATE", "VEHICLE_STATUS",
        ),
        "pk": "VEHICLE_ID", "count": 200,
        "required": ("VEHICLE_ID", "LICENSE_PLATE", "VEHICLE_TYPE"),
        "decimal": ("CAPACITY_KG",),
        "dates": ("ACQUISITION_DATE",),
    },
    "driver": {
        "file": "dim_driver.csv",
        "temp": "STAGING.TMP_DRIVER_LOAD",
        "fields": (
            "DRIVER_ID", "EMPLOYEE_CODE", "FIRST_NAME", "LAST_NAME",
            "LICENSE_EXPIRY", "HIRE_DATE", "DRIVER_STATUS",
            "ASSIGNED_ZONE", "ATTRIBUTE_HASH",
        ),
        "pk": "DRIVER_ID", "count": 400,
        "required": (
            "DRIVER_ID", "EMPLOYEE_CODE", "FIRST_NAME", "LAST_NAME", "ATTRIBUTE_HASH"
        ),
        "decimal": (), "dates": ("LICENSE_EXPIRY", "HIRE_DATE"),
    },
    "route": {
        "file": "dim_route.csv",
        "temp": "STAGING.TMP_ROUTE_LOAD",
        "fields": (
            "ROUTE_ID", "ROUTE_CODE", "ORIGIN_CITY", "DESTINATION_CITY",
            "DISTANCE_KM", "ESTIMATED_DURATION_HOURS", "TOLL_COST",
        ),
        "pk": "ROUTE_ID", "count": 50,
        "required": (
            "ROUTE_ID", "ROUTE_CODE", "ORIGIN_CITY", "DESTINATION_CITY"
        ),
        "decimal": ("DISTANCE_KM", "ESTIMATED_DURATION_HOURS", "TOLL_COST"),
        "dates": (),
    },
}


def read_and_validate(kind: str) -> list[tuple[str | None, ...]]:
    spec = SPECS[kind]
    path = PREPARED / spec["file"]
    if not path.is_file():
        raise FileNotFoundError(f"Falta archivo preparado: {path}")

    rows: list[tuple[str | None, ...]] = []
    ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != list(spec["fields"]):
            raise ValueError(f"{path.name}: columnas u orden inesperados: {reader.fieldnames}")
        for line_num, item in enumerate(reader, start=2):
            row = {k: (v or "").strip() for k, v in item.items()}
            for field in spec["required"]:
                if not row[field]:
                    raise ValueError(f"{path.name}:{line_num}: {field} obligatorio vacio")
            key = row[spec["pk"]]
            if not key.isdecimal() or int(key) <= 0:
                raise ValueError(f"{path.name}:{line_num}: identificador invalido: {key}")
            if key in ids:
                raise ValueError(f"{path.name}:{line_num}: identificador repetido: {key}")
            ids.add(key)

            for field in spec["decimal"]:
                if row[field]:
                    try:
                        number = Decimal(row[field])
                        if not number.is_finite() or number < 0:
                            raise ValueError()
                    except (InvalidOperation, ValueError) as exc:
                        raise ValueError(
                            f"{path.name}:{line_num}: {field} invalido"
                        ) from exc

            for field in spec["dates"]:
                if row[field]:
                    try:
                        date.fromisoformat(row[field])
                    except ValueError as exc:
                        raise ValueError(
                            f"{path.name}:{line_num}: {field} no es YYYY-MM-DD"
                        ) from exc

            if kind == "driver" and not re.fullmatch(
                r"[0-9a-f]{64}", row["ATTRIBUTE_HASH"]
            ):
                raise ValueError(f"{path.name}:{line_num}: hash SHA-256 invalido")

            rows.append(tuple(row[column] or None for column in spec["fields"]))

    if len(rows) != spec["count"]:
        raise ValueError(
            f"{path.name}: esperados {spec['count']} registros, obtenidos {len(rows)}"
        )
    print(f"Archivo validado: {path.name} ({len(rows)} filas)")
    return rows


def stage_rows(cursor, kind: str, rows: list[tuple[str | None, ...]]) -> None:
    spec = SPECS[kind]
    columns = ", ".join(f"{name} VARCHAR(500)" for name in spec["fields"])
    cursor.execute(f"CREATE TEMPORARY TABLE {spec['temp']} ({columns})")
    placeholders = ", ".join(["%s"] * len(spec["fields"]))
    cursor.executemany(
        f"INSERT INTO {spec['temp']} VALUES ({placeholders})", rows
    )
    cursor.execute(f"SELECT COUNT(*) FROM {spec['temp']}")
    (loaded,) = cursor.fetchone()
    if loaded != len(rows):
        raise RuntimeError(f"Stage {kind}: {loaded} filas, se esperaban {len(rows)}")


def assert_no_target_duplicates(cursor) -> None:
    checks = {
        "ANALYTICS.DIM_VEHICLE": "VEHICLE_ID",
        "ANALYTICS.DIM_ROUTE": "ROUTE_ID",
    }
    for table, key in checks.items():
        cursor.execute(
            f"SELECT COUNT(*) FROM (SELECT {key} FROM {table} "
            f"GROUP BY {key} HAVING COUNT(*) > 1)"
        )
        if cursor.fetchone()[0]:
            raise RuntimeError(f"Hay claves de origen duplicadas en {table}")
    cursor.execute(
        "SELECT COUNT(*) FROM (SELECT DRIVER_ID FROM ANALYTICS.DIM_DRIVER "
        "WHERE IS_CURRENT = TRUE GROUP BY DRIVER_ID HAVING COUNT(*) > 1)"
    )
    if cursor.fetchone()[0]:
        raise RuntimeError("Hay varias versiones actuales para un mismo conductor")


def apply_vehicle_merge(cursor) -> None:
    cursor.execute("""
        MERGE INTO ANALYTICS.DIM_VEHICLE t
        USING (
            SELECT TO_NUMBER(VEHICLE_ID) VEHICLE_ID,
                   LICENSE_PLATE, VEHICLE_TYPE,
                   TO_DECIMAL(CAPACITY_KG,18,3) CAPACITY_KG,
                   FUEL_TYPE, TO_DATE(ACQUISITION_DATE) ACQUISITION_DATE,
                   VEHICLE_STATUS
            FROM STAGING.TMP_VEHICLE_LOAD
        ) s
        ON t.VEHICLE_ID = s.VEHICLE_ID
        WHEN MATCHED AND (
             t.LICENSE_PLATE IS DISTINCT FROM s.LICENSE_PLATE
          OR t.VEHICLE_TYPE IS DISTINCT FROM s.VEHICLE_TYPE
          OR t.CAPACITY_KG IS DISTINCT FROM s.CAPACITY_KG
          OR t.FUEL_TYPE IS DISTINCT FROM s.FUEL_TYPE
          OR t.ACQUISITION_DATE IS DISTINCT FROM s.ACQUISITION_DATE
          OR t.VEHICLE_STATUS IS DISTINCT FROM s.VEHICLE_STATUS
        ) THEN UPDATE SET
            t.LICENSE_PLATE=s.LICENSE_PLATE,
            t.VEHICLE_TYPE=s.VEHICLE_TYPE,
            t.CAPACITY_KG=s.CAPACITY_KG,
            t.FUEL_TYPE=s.FUEL_TYPE,
            t.ACQUISITION_DATE=s.ACQUISITION_DATE,
            t.VEHICLE_STATUS=s.VEHICLE_STATUS,
            t.DW_LOADED_AT=CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
        WHEN NOT MATCHED THEN INSERT (
            VEHICLE_ID, LICENSE_PLATE, VEHICLE_TYPE, CAPACITY_KG,
            FUEL_TYPE, ACQUISITION_DATE, VEHICLE_STATUS
        ) VALUES (
            s.VEHICLE_ID,s.LICENSE_PLATE,s.VEHICLE_TYPE,s.CAPACITY_KG,
            s.FUEL_TYPE,s.ACQUISITION_DATE,s.VEHICLE_STATUS
        )
    """)


def apply_route_merge(cursor) -> None:
    cursor.execute("""
        MERGE INTO ANALYTICS.DIM_ROUTE t
        USING (
            SELECT TO_NUMBER(ROUTE_ID) ROUTE_ID,
                   ROUTE_CODE, ORIGIN_CITY, DESTINATION_CITY,
                   TO_DECIMAL(DISTANCE_KM,18,3) DISTANCE_KM,
                   TO_DECIMAL(ESTIMATED_DURATION_HOURS,12,3)
                       ESTIMATED_DURATION_HOURS,
                   TO_DECIMAL(TOLL_COST,18,2) TOLL_COST
            FROM STAGING.TMP_ROUTE_LOAD
        ) s
        ON t.ROUTE_ID = s.ROUTE_ID
        WHEN MATCHED AND (
             t.ROUTE_CODE IS DISTINCT FROM s.ROUTE_CODE
          OR t.ORIGIN_CITY IS DISTINCT FROM s.ORIGIN_CITY
          OR t.DESTINATION_CITY IS DISTINCT FROM s.DESTINATION_CITY
          OR t.DISTANCE_KM IS DISTINCT FROM s.DISTANCE_KM
          OR t.ESTIMATED_DURATION_HOURS IS DISTINCT FROM s.ESTIMATED_DURATION_HOURS
          OR t.TOLL_COST IS DISTINCT FROM s.TOLL_COST
        ) THEN UPDATE SET
            t.ROUTE_CODE=s.ROUTE_CODE,
            t.ORIGIN_CITY=s.ORIGIN_CITY,
            t.DESTINATION_CITY=s.DESTINATION_CITY,
            t.DISTANCE_KM=s.DISTANCE_KM,
            t.ESTIMATED_DURATION_HOURS=s.ESTIMATED_DURATION_HOURS,
            t.TOLL_COST=s.TOLL_COST,
            t.DW_LOADED_AT=CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
        WHEN NOT MATCHED THEN INSERT (
            ROUTE_ID, ROUTE_CODE, ORIGIN_CITY, DESTINATION_CITY,
            DISTANCE_KM, ESTIMATED_DURATION_HOURS, TOLL_COST
        ) VALUES (
            s.ROUTE_ID,s.ROUTE_CODE,s.ORIGIN_CITY,s.DESTINATION_CITY,
            s.DISTANCE_KM,s.ESTIMATED_DURATION_HOURS,s.TOLL_COST
        )
    """)


def apply_driver_scd2(cursor, changed_at: str) -> None:
    # Se cierra solo la version actual cuyo hash cambio.
    cursor.execute("""
        UPDATE ANALYTICS.DIM_DRIVER t
        SET VALID_TO=TO_TIMESTAMP_NTZ(%s), IS_CURRENT=FALSE
        FROM STAGING.TMP_DRIVER_LOAD s
        WHERE t.DRIVER_ID=TO_NUMBER(s.DRIVER_ID)
          AND t.IS_CURRENT=TRUE
          AND t.ATTRIBUTE_HASH IS DISTINCT FROM s.ATTRIBUTE_HASH
    """, (changed_at,))

    # Para nuevos conductores, fecha minima tecnica para compatibilidad
    # con hechos historicos; no demuestra atributos anteriores a la captura.
    # Para conductores modificados, una version nueva desde la deteccion.
    cursor.execute("""
        INSERT INTO ANALYTICS.DIM_DRIVER (
            DRIVER_ID, EMPLOYEE_CODE, FIRST_NAME, LAST_NAME,
            LICENSE_EXPIRY, HIRE_DATE, DRIVER_STATUS, ASSIGNED_ZONE,
            VALID_FROM, VALID_TO, IS_CURRENT, ATTRIBUTE_HASH
        )
        SELECT TO_NUMBER(s.DRIVER_ID), s.EMPLOYEE_CODE,
               s.FIRST_NAME, s.LAST_NAME,
               TO_DATE(s.LICENSE_EXPIRY), TO_DATE(s.HIRE_DATE),
               s.DRIVER_STATUS, s.ASSIGNED_ZONE,
               IFF(hist.DRIVER_ID IS NULL,
                   TO_TIMESTAMP_NTZ(%s), TO_TIMESTAMP_NTZ(%s)),
               NULL, TRUE, s.ATTRIBUTE_HASH
        FROM STAGING.TMP_DRIVER_LOAD s
        LEFT JOIN (
            SELECT DISTINCT DRIVER_ID FROM ANALYTICS.DIM_DRIVER
        ) hist ON hist.DRIVER_ID=TO_NUMBER(s.DRIVER_ID)
        WHERE NOT EXISTS (
            SELECT 1 FROM ANALYTICS.DIM_DRIVER cur
            WHERE cur.DRIVER_ID=TO_NUMBER(s.DRIVER_ID)
              AND cur.IS_CURRENT=TRUE
        )
    """, (FIRST_KNOWN, changed_at))


def check_final_counts(cursor) -> None:
    cursor.execute("SELECT COUNT(*) FROM ANALYTICS.DIM_VEHICLE")
    vehicle_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ANALYTICS.DIM_ROUTE")
    route_count = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM ANALYTICS.DIM_DRIVER WHERE IS_CURRENT=TRUE"
    )
    current_drivers = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ANALYTICS.DIM_DRIVER")
    all_driver_versions = cursor.fetchone()[0]
    assert_no_target_duplicates(cursor)
    if (vehicle_count, current_drivers, route_count) != (200, 400, 50):
        raise RuntimeError(
            "Conteos finales incorrectos: "
            f"vehicles={vehicle_count}, drivers actuales={current_drivers}, "
            f"routes={route_count}"
        )
    print(f"DIM_VEHICLE: {vehicle_count}")
    print(f"DIM_DRIVER: {current_drivers} actuales / {all_driver_versions} versiones")
    print(f"DIM_ROUTE: {route_count}")


def main() -> None:
    print("FleetLogix: validando archivos preparados...")
    batches = {kind: read_and_validate(kind) for kind in SPECS}

    required_env = (
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
    )
    missing = [name for name in required_env if not os.getenv(name)]
    if missing:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(missing))

    print("Conectando con Snowflake mediante navegador...")
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="OAUTH_AUTHORIZATION_CODE",
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        timezone="UTC",
        enable_server_session_keep_alive_auto_detection=False,
        login_timeout=120,
    )

    try:
        with conn.cursor() as cur:
            # DDL antes de BEGIN: DDL hace commit implicito en Snowflake.
            for kind, rows in batches.items():
                stage_rows(cur, kind, rows)
                print(f"Stage preparado: {kind}")

            assert_no_target_duplicates(cur)
            changed_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
            try:
                cur.execute("BEGIN")
                apply_vehicle_merge(cur)
                apply_route_merge(cur)
                apply_driver_scd2(cur, changed_at)
                check_final_counts(cur)
                cur.execute("COMMIT")
                print("CARGA CONFIRMADA (COMMIT)")
            except Exception:
                cur.execute("ROLLBACK")
                print("CARGA REVERTIDA (ROLLBACK)")
                raise
    finally:
        conn.close()
        print("Conexion Snowflake cerrada.")


if __name__ == "__main__":
    main()
