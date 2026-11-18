"""FleetLogix Avance #3 — cargador incremental de FACT_DELIVERIES.

Modo normal: valida solo el delta local, sin conectar con Snowflake.
  python Scripts/Avance_3/13_load_incremental_fact_delta.py --self-test
  python Scripts/Avance_3/13_load_incremental_fact_delta.py

Modo de escritura (NO usar hasta validar un ensayo aislado con cambios):
  python Scripts/Avance_3/13_load_incremental_fact_delta.py --execute

Sin filas de delta, --execute también termina SIN CONEXIÓN y SIN MERGE.
El pipeline todavía no implementa CDC ni control de concurrencia distribuido.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
INCREMENTAL_DIR = ROOT / "data" / "staging" / "avance_3" / "incremental"
DELTA_CSV = INCREMENTAL_DIR / "fact_deliveries_delta.csv"
DELTA_AUDIT = INCREMENTAL_DIR / "fact_deliveries_delta_audit.json"
FULL_CSV = ROOT / "data" / "staging" / "avance_3" / "prepared" / "fact_deliveries.csv"
FULL_AUDIT = ROOT / "data" / "staging" / "avance_3" / "prepared" / "fact_deliveries_audit.json"

COLUMNS = [
    "DELIVERY_ID", "TRIP_ID", "TRACKING_NUMBER", "DATE_KEY",
    "DELIVERY_HOUR", "VEHICLE_ID", "DRIVER_ID", "ROUTE_ID",
    "CUSTOMER_BK", "DEPARTURE_DATETIME", "SCHEDULED_DATETIME",
    "DELIVERED_DATETIME", "DELIVERY_COUNT", "PACKAGE_WEIGHT_KG",
    "DELIVERY_DURATION_MINUTES", "SCHEDULE_VARIANCE_MINUTES",
    "IS_ON_TIME", "ALLOCATED_DISTANCE_KM", "ALLOCATED_FUEL_LITERS",
    "ALLOCATION_METHOD", "ESTIMATED_REVENUE_COP",
    "REVENUE_POLICY_VERSION", "SOURCE_ROW_HASH",
]
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
DATETIME_FMT = "%Y-%m-%d %H:%M:%S.%f"
POLICY = "SYNTHETIC_REVENUE_V1"
REQUIRED_ENV = (
    "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
)


def load_full_loader():
    """Reutiliza la resolución y el MERGE ya validados en el cargador 08."""
    path = Path(__file__).with_name("08_load_fact_deliveries.py")
    if not path.exists():
        raise FileNotFoundError(f"Falta el cargador base 08: {path}")
    spec = importlib.util.spec_from_file_location("fleetlogix_fact_loader_08", path)
    if spec is None or spec.loader is None:
        raise ImportError("No se pudo importar el cargador 08")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.COLS != COLUMNS:
        raise RuntimeError("Incompatibilidad de columnas: actualiza 08 y 13 conjuntamente")
    if module.REVENUE_POLICY != POLICY:
        raise RuntimeError("El cargador 08 no tiene la política de ingresos V1")
    return module


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for piece in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def hash_record(row: dict[str, str]) -> str:
    payload = json.dumps(
        {key: row[key] for key in COLUMNS if key != "SOURCE_ROW_HASH"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def as_decimal(value: str, name: str, *, strictly_positive: bool = False) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Decimal inválido en {name}") from exc
    if not result.is_finite() or result < 0 or (strictly_positive and result == 0):
        raise ValueError(f"Valor negativo, nulo o no finito en {name}")
    return result


def validate_one(row: dict[str, str], line: int) -> int:
    if None in row or set(row) != set(COLUMNS):
        raise ValueError(f"CSV mal formado en línea {line}")
    required = [
        "DELIVERY_ID", "TRIP_ID", "DATE_KEY", "DELIVERY_HOUR",
        "VEHICLE_ID", "DRIVER_ID", "ROUTE_ID", "CUSTOMER_BK",
        "DEPARTURE_DATETIME", "SCHEDULED_DATETIME", "DELIVERED_DATETIME",
        "PACKAGE_WEIGHT_KG", "DELIVERY_DURATION_MINUTES",
        "SCHEDULE_VARIANCE_MINUTES", "ALLOCATED_DISTANCE_KM",
        "ALLOCATED_FUEL_LITERS", "ESTIMATED_REVENUE_COP", "SOURCE_ROW_HASH",
    ]
    if any(not row.get(column) for column in required):
        raise ValueError(f"Campos obligatorios vacíos en línea {line}")
    for column in ("DELIVERY_ID", "TRIP_ID", "VEHICLE_ID", "DRIVER_ID", "ROUTE_ID"):
        text_value = row[column]
        if not text_value.isascii() or not text_value.isdecimal() or int(text_value) <= 0:
            raise ValueError(f"{column} inválido en línea {line}")
    delivery_id = int(row["DELIVERY_ID"])
    if not HASH_RE.fullmatch(row["CUSTOMER_BK"]):
        raise ValueError(f"CUSTOMER_BK inválido en línea {line}")
    if not HASH_RE.fullmatch(row["SOURCE_ROW_HASH"]) or row["SOURCE_ROW_HASH"] != hash_record(row):
        raise ValueError(f"Hash no coincide en línea {line}")
    try:
        departed = datetime.strptime(row["DEPARTURE_DATETIME"], DATETIME_FMT)
        scheduled = datetime.strptime(row["SCHEDULED_DATETIME"], DATETIME_FMT)
        delivered = datetime.strptime(row["DELIVERED_DATETIME"], DATETIME_FMT)
    except ValueError as exc:
        raise ValueError(f"Fecha inválida en línea {line}") from exc
    if delivered < departed or not datetime(2024, 1, 1) <= delivered < datetime(2031, 1, 1):
        raise ValueError(f"Vigencia de fecha inválida en línea {line}")
    if row["DATE_KEY"] != delivered.strftime("%Y%m%d") or row["DELIVERY_HOUR"] != str(delivered.hour):
        raise ValueError(f"DATE_KEY/DELIVERY_HOUR no coincide en línea {line}")
    if row["DELIVERY_COUNT"] != "1" or row["ALLOCATION_METHOD"] != "WEIGHT_PROPORTIONAL_V1":
        raise ValueError(f"Regla de entrega/asignación inválida en línea {line}")
    if row["IS_ON_TIME"] not in {"TRUE", "FALSE"} or (row["IS_ON_TIME"] == "TRUE") != (delivered <= scheduled):
        raise ValueError(f"Puntualidad inconsistente en línea {line}")
    weight = as_decimal(row["PACKAGE_WEIGHT_KG"], "PACKAGE_WEIGHT_KG", strictly_positive=True)
    as_decimal(row["DELIVERY_DURATION_MINUTES"], "DELIVERY_DURATION_MINUTES")
    as_decimal(row["ALLOCATED_FUEL_LITERS"], "ALLOCATED_FUEL_LITERS")
    distance = as_decimal(row["ALLOCATED_DISTANCE_KM"], "ALLOCATED_DISTANCE_KM")
    revenue = as_decimal(row["ESTIMATED_REVENUE_COP"], "ESTIMATED_REVENUE_COP")
    try:
        variance = Decimal(row["SCHEDULE_VARIANCE_MINUTES"])
    except InvalidOperation as exc:
        raise ValueError(f"Variación horaria inválida en línea {line}") from exc
    if not variance.is_finite():
        raise ValueError(f"Variación horaria no finita en línea {line}")
    expected_revenue = (
        Decimal("7000") + weight * Decimal("20") + distance * Decimal("300")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if row["REVENUE_POLICY_VERSION"] != POLICY or revenue != expected_revenue:
        raise ValueError(f"Ingreso sintético inválido en línea {line}")
    return delivery_id


def validate_delta(csv_path: Path, audit_path: Path, *, verify_freshness: bool = True) -> dict:
    if not csv_path.is_file() or not audit_path.is_file():
        raise FileNotFoundError("Falta delta o auditoría. Ejecuta primero 12_prepare_incremental_fact_delta.py")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (
        audit.get("status") != "VALIDATED_NOT_LOADED"
        or audit.get("method") != "DELIVERY_ID_AND_SOURCE_ROW_HASH"
        or audit.get("revenue_policy") != POLICY
        or audit.get("missing") != 0
        or audit.get("snowflake_modified") is not False
    ):
        raise ValueError("El JSON de auditoría del delta no tiene un estado válido")
    for name in ("source_rows", "snowflake_rows_before", "unchanged", "new", "modified", "delta_rows"):
        if not isinstance(audit.get(name), int) or audit[name] < 0:
            raise ValueError(f"Conteo inválido en auditoría: {name}")
    if (
        audit["new"] + audit["modified"] != audit["delta_rows"]
        or audit["unchanged"] + audit["delta_rows"] != audit["source_rows"]
        or audit["unchanged"] + audit["modified"] != audit["snowflake_rows_before"]
    ):
        raise ValueError("Los conteos del delta no concilian con la auditoría")
    if verify_freshness:
        if audit.get("delta_csv") != str(csv_path) or audit.get("source_csv") != str(FULL_CSV):
            raise ValueError("La auditoría apunta a otro archivo fuente/delta")
        if not FULL_CSV.is_file() or not FULL_AUDIT.is_file():
            raise FileNotFoundError("Falta snapshot completo o auditoría del transformador")
        source_audit = json.loads(FULL_AUDIT.read_text(encoding="utf-8"))
        if (
            source_audit.get("status") != "VALIDATED"
            or source_audit.get("prepared_delivery_count") != audit["source_rows"]
            or source_audit.get("revenue_policy") != POLICY
        ):
            raise ValueError("El snapshot completo ya no concilia con el delta")
        if FULL_CSV.stat().st_mtime_ns > csv_path.stat().st_mtime_ns:
            raise RuntimeError("El CSV completo se modificó después del delta: regenera el delta")
    count = 0
    seen = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError("Cabecera/orden de columnas del delta incorrectos")
        for line, row in enumerate(reader, start=2):
            delivery_id = validate_one(row, line)
            if delivery_id in seen:
                raise ValueError(f"DELIVERY_ID duplicado en el delta: {delivery_id}")
            seen.add(delivery_id)
            count += 1
            if count % 100_000 == 0:
                print(f"  Delta validado: {count:,} filas")
    if count != audit["delta_rows"]:
        raise ValueError(f"Delta cuenta {count} filas pero auditoría indica {audit['delta_rows']}")
    return audit


def get_counts(cursor, table: str = "ANALYTICS.FACT_DELIVERIES") -> tuple:
    cursor.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT DELIVERY_ID),
               COALESCE(SUM(ALLOCATED_DISTANCE_KM),0),
               COALESCE(SUM(ALLOCATED_FUEL_LITERS),0),
               COALESCE(SUM(ESTIMATED_REVENUE_COP),0)
        FROM {table}
    """)
    return cursor.fetchone()


def require_valid_resolved(cursor, delta_rows: int):
    cursor.execute("""
        SELECT COUNT(*), COUNT(DISTINCT DELIVERY_ID),
               COUNT_IF(DATE_KEY IS NULL OR TIME_KEY IS NULL
                 OR VEHICLE_KEY IS NULL OR DRIVER_KEY IS NULL
                 OR ROUTE_KEY IS NULL OR CUSTOMER_KEY IS NULL),
               COUNT_IF(ESTIMATED_REVENUE_COP IS NULL
                 OR REVENUE_POLICY_VERSION <> 'SYNTHETIC_REVENUE_V1'
                 OR ESTIMATED_REVENUE_COP <> ROUND(
                      7000 + PACKAGE_WEIGHT_KG * 20 + ALLOCATED_DISTANCE_KM * 300, 2)),
               COUNT_IF(ALLOCATED_DISTANCE_KM < 0 OR ALLOCATED_FUEL_LITERS < 0)
        FROM TMP_FLEETLOGIX_FACT_RESOLVED
    """)
    count, distinct, missing, bad_revenue, negative = cursor.fetchone()
    if (count, distinct, missing, bad_revenue, negative) != (delta_rows, delta_rows, 0, 0, 0):
        raise RuntimeError("Delta resuelto tiene duplicados, referencias o métricas incorrectas")
    print(f"Resolución dimensional: {count:,} filas, 0 claves sin resolver")


def require_merged_rows(cursor, delta_rows: int):
    cursor.execute("""
        SELECT COUNT(*), COUNT_IF(
              t.DELIVERY_ID IS NULL
              OR t.SOURCE_ROW_HASH IS DISTINCT FROM s.SOURCE_ROW_HASH
              OR t.DATE_KEY IS DISTINCT FROM s.DATE_KEY
              OR t.TIME_KEY IS DISTINCT FROM s.TIME_KEY
              OR t.VEHICLE_KEY IS DISTINCT FROM s.VEHICLE_KEY
              OR t.DRIVER_KEY IS DISTINCT FROM s.DRIVER_KEY
              OR t.ROUTE_KEY IS DISTINCT FROM s.ROUTE_KEY
              OR t.CUSTOMER_KEY IS DISTINCT FROM s.CUSTOMER_KEY
              OR t.ESTIMATED_REVENUE_COP IS DISTINCT FROM s.ESTIMATED_REVENUE_COP
              OR t.ALLOCATED_DISTANCE_KM IS DISTINCT FROM s.ALLOCATED_DISTANCE_KM
              OR t.ALLOCATED_FUEL_LITERS IS DISTINCT FROM s.ALLOCATED_FUEL_LITERS
        ) AS BAD
        FROM TMP_FLEETLOGIX_FACT_RESOLVED s
        LEFT JOIN ANALYTICS.FACT_DELIVERIES t ON t.DELIVERY_ID=s.DELIVERY_ID
    """)
    count, bad = cursor.fetchone()
    if (count, bad) != (delta_rows, 0):
        raise RuntimeError("La verificación posterior al MERGE no coincide con el delta")


def apply_delta(audit: dict, delta_hash_before: str):
    import snowflake.connector

    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        raise RuntimeError("Faltan variables .env: " + ", ".join(missing))
    full = load_full_loader()
    uri = ("file://" + DELTA_CSV.resolve().as_posix()).replace("'", "''")
    print("Conectando con Snowflake mediante OAuth (carga de delta)...")
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
    in_tx = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ROLE()")
            if cur.fetchone() != ("FLEETLOGIX_DWH", "ANALYTICS", "SYSADMIN"):
                raise RuntimeError("Contexto Snowflake inesperado; sin cambios")
            time_expr = full.get_time_hour_expression(cur)
            full.check_dimension_business_keys(cur)

            raw_cols = ",\n".join(f"{name} VARCHAR(500)" for name in COLUMNS)
            cur.execute(f"CREATE TEMPORARY TABLE TMP_FLEETLOGIX_FACT_RAW ({raw_cols})")
            cur.execute("""
                CREATE TEMPORARY STAGE TMP_FLEETLOGIX_FACT_FILES
                FILE_FORMAT=(TYPE=CSV FIELD_DELIMITER=',' SKIP_HEADER=1
                 FIELD_OPTIONALLY_ENCLOSED_BY='"' MULTI_LINE=TRUE
                 ENCODING='UTF8' EMPTY_FIELD_AS_NULL=TRUE NULL_IF=('')
                 ESCAPE_UNENCLOSED_FIELD=NONE)
            """)
            if file_sha256(DELTA_CSV) != delta_hash_before:
                raise RuntimeError("El delta cambió antes del PUT")
            cur.execute(f"PUT '{uri}' @TMP_FLEETLOGIX_FACT_FILES AUTO_COMPRESS=TRUE OVERWRITE=TRUE PARALLEL=4")
            put_rows = cur.fetchall()
            if not put_rows or any(str(r[-2]).upper() != "UPLOADED" for r in put_rows):
                raise RuntimeError(f"PUT sin confirmación UPLOADED: {put_rows}")
            if file_sha256(DELTA_CSV) != delta_hash_before:
                raise RuntimeError("El delta cambió durante la transferencia")
            print("PUT confirmado: UPLOADED")
            cur.execute("""
                COPY INTO TMP_FLEETLOGIX_FACT_RAW FROM @TMP_FLEETLOGIX_FACT_FILES
                FILE_FORMAT=(TYPE=CSV FIELD_DELIMITER=',' SKIP_HEADER=1
                 FIELD_OPTIONALLY_ENCLOSED_BY='"' MULTI_LINE=TRUE
                 ENCODING='UTF8' EMPTY_FIELD_AS_NULL=TRUE NULL_IF=('')
                 ESCAPE_UNENCLOSED_FIELD=NONE)
                ON_ERROR='ABORT_STATEMENT' FORCE=TRUE
            """)
            copy_rows = cur.fetchall()
            loaded = sum(int(r[3]) for r in copy_rows)
            if not copy_rows or any(str(r[1]).upper() != "LOADED" for r in copy_rows) or loaded != audit["delta_rows"]:
                raise RuntimeError(f"COPY inesperado: {copy_rows}")
            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT DELIVERY_ID),
                       COUNT_IF(DELIVERY_ID IS NULL OR TRIP_ID IS NULL
                         OR SOURCE_ROW_HASH IS NULL)
                FROM TMP_FLEETLOGIX_FACT_RAW
            """)
            raw, uniques, missing_values = cur.fetchone()
            if (raw, uniques, missing_values) != (loaded, loaded, 0):
                raise RuntimeError("Staging RAW duplicado/incompleto")
            print(f"COPY confirmado: {loaded:,} filas")
            cur.execute(full.build_resolved_sql(time_expr))
            require_valid_resolved(cur, loaded)
            cur.execute("BEGIN")
            in_tx = True
            before = get_counts(cur)
            if before[0] != before[1]:
                raise RuntimeError("Tabla de hechos con IDs duplicados antes del MERGE")
            if not (audit["snowflake_rows_before"] <= before[0] <= audit["snowflake_rows_before"] + audit["new"]):
                raise RuntimeError("Conteo destino cambió inesperadamente: regenera el delta")

            # Medidas de referencia del delta antes de modificar.
            cur.execute("""
                SELECT
                    COUNT_IF(t.DELIVERY_ID IS NULL),
                    COUNT_IF(t.DELIVERY_ID IS NOT NULL AND (
                      t.SOURCE_ROW_HASH IS DISTINCT FROM s.SOURCE_ROW_HASH
                      OR t.DATE_KEY IS DISTINCT FROM s.DATE_KEY
                      OR t.TIME_KEY IS DISTINCT FROM s.TIME_KEY
                      OR t.VEHICLE_KEY IS DISTINCT FROM s.VEHICLE_KEY
                      OR t.DRIVER_KEY IS DISTINCT FROM s.DRIVER_KEY
                      OR t.ROUTE_KEY IS DISTINCT FROM s.ROUTE_KEY
                      OR t.CUSTOMER_KEY IS DISTINCT FROM s.CUSTOMER_KEY)),
                    COALESCE(SUM(s.ALLOCATED_DISTANCE_KM - COALESCE(t.ALLOCATED_DISTANCE_KM,0)),0),
                    COALESCE(SUM(s.ALLOCATED_FUEL_LITERS - COALESCE(t.ALLOCATED_FUEL_LITERS,0)),0),
                    COALESCE(SUM(s.ESTIMATED_REVENUE_COP - COALESCE(t.ESTIMATED_REVENUE_COP,0)),0)
                FROM TMP_FLEETLOGIX_FACT_RESOLVED s
                LEFT JOIN ANALYTICS.FACT_DELIVERIES t ON t.DELIVERY_ID=s.DELIVERY_ID
            """)
            expected_inserted, expected_updated, d_distance, d_fuel, d_revenue = cur.fetchone()
            inserted, updated = full.merge_facts(cur)
            print(f"MERGE incremental: {inserted:,} insertadas / {updated:,} actualizadas")
            if (inserted, updated) != (expected_inserted, expected_updated):
                raise RuntimeError("Contadores MERGE no coinciden con el delta")
            require_merged_rows(cur, loaded)
            after = get_counts(cur)
            if after[0] != before[0] + inserted or after[0] != after[1]:
                raise RuntimeError("Cantidad o unicidad del destino cambió incorrectamente")
            if (
                Decimal(str(after[2])) != Decimal(str(before[2])) + Decimal(str(d_distance))
                or Decimal(str(after[3])) != Decimal(str(before[3])) + Decimal(str(d_fuel))
                or Decimal(str(after[4])) != Decimal(str(before[4])) + Decimal(str(d_revenue))
            ):
                raise RuntimeError("Conciliación incremental de medidas no coincide")
            cur.execute("COMMIT")
            in_tx = False
            print(f"CARGA INCREMENTAL CONFIRMADA (COMMIT): {after[0]:,} entregas")
    except Exception:
        if in_tx:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK")
                print("CARGA INCREMENTAL REVERTIDA (ROLLBACK)")
            in_tx = False
        raise
    finally:
        conn.close()
        print("Conexión Snowflake cerrada")


def self_test() -> None:
    """Ensayo LOCAL: datos ficticios; no importa scripts con conectores ni usa red."""
    def make_row(delivery_id: int, weight: str) -> dict[str, str]:
        row = {col: "" for col in COLUMNS}
        row.update({
            "DELIVERY_ID": str(delivery_id), "TRIP_ID": "10", "TRACKING_NUMBER": f"TEST-{delivery_id}",
            "DATE_KEY": "20250101", "DELIVERY_HOUR": "12", "VEHICLE_ID": "1",
            "DRIVER_ID": "1", "ROUTE_ID": "1", "CUSTOMER_BK": "a" * 64,
            "DEPARTURE_DATETIME": "2025-01-01 09:00:00.000000",
            "SCHEDULED_DATETIME": "2025-01-01 13:00:00.000000",
            "DELIVERED_DATETIME": "2025-01-01 12:00:00.000000",
            "DELIVERY_COUNT": "1", "PACKAGE_WEIGHT_KG": weight,
            "DELIVERY_DURATION_MINUTES": "180.000",
            "SCHEDULE_VARIANCE_MINUTES": "-60.000", "IS_ON_TIME": "TRUE",
            "ALLOCATED_DISTANCE_KM": "2.000000", "ALLOCATED_FUEL_LITERS": "1.000000",
            "ALLOCATION_METHOD": "WEIGHT_PROPORTIONAL_V1",
            "REVENUE_POLICY_VERSION": POLICY,
        })
        row["ESTIMATED_REVENUE_COP"] = str((
            Decimal("7000") + Decimal(weight) * 20 + Decimal("2") * 300
        ).quantize(Decimal("0.01")))
        row["SOURCE_ROW_HASH"] = hash_record(row)
        return row

    with tempfile.TemporaryDirectory(prefix="fleetlogix_delta_loader_test_") as dirname:
        temp = Path(dirname)
        target = temp / "delta.csv"
        audit_file = temp / "audit.json"
        rows = [make_row(22, "10.000"), make_row(23, "20.000")]
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        audit = {
            "status": "VALIDATED_NOT_LOADED", "method": "DELIVERY_ID_AND_SOURCE_ROW_HASH",
            "revenue_policy": POLICY, "missing": 0, "snowflake_modified": False,
            "source_rows": 3, "snowflake_rows_before": 2,
            "unchanged": 1, "new": 1, "modified": 1, "delta_rows": 2,
        }
        audit_file.write_text(json.dumps(audit), encoding="utf-8")
        assert validate_delta(target, audit_file, verify_freshness=False)["delta_rows"] == 2
        print("AUTOPRUEBA: 1 nueva + 1 modificada (2 filas de delta) — OK")
        rows[0]["ESTIMATED_REVENUE_COP"] = "0.00"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        try:
            validate_delta(target, audit_file, verify_freshness=False)
        except ValueError:
            print("AUTOPRUEBA: fórmula/hash inconsistente bloqueados — OK")
        else:
            raise AssertionError("Una alteración indebida debe detener el cargador")
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerow(make_row(22, "10.000"))
        try:
            validate_delta(target, audit_file, verify_freshness=False)
        except ValueError:
            print("AUTOPRUEBA: cantidad distinta de la auditoría bloqueada — OK")
        else:
            raise AssertionError("La cantidad incorrecta debe detener el cargador")
    print("AUTOPRUEBA LOCAL APROBADA: PostgreSQL y Snowflake intactos")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cargador por diferencias FACT_DELIVERIES")
    parser.add_argument("--self-test", action="store_true", help="Pruebas ficticias locales, sin conexión")
    parser.add_argument("--execute", action="store_true", help="Solicita aplicar el delta (si está vacío, no hace nada)")
    parser.add_argument("--confirm-nonempty-write", action="store_true",
                        help="Confirmación adicional para cambios reales; NO usar antes de prueba aislada")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    print("FleetLogix | LOAD_INCREMENTAL_FACT_DELTA | VALIDACIÓN LOCAL")
    audit = validate_delta(DELTA_CSV, DELTA_AUDIT)
    print(
        f"Delta OK: {audit['delta_rows']:,} filas, "
        f"{audit['new']:,} nuevas, {audit['modified']:,} modificadas; "
        f"{audit['unchanged']:,} sin cambios"
    )
    if audit["delta_rows"] == 0:
        print("DELTA VACÍO — NO-OP: sin conexión a Snowflake ni operaciones PUT/COPY/MERGE")
        return
    if not args.execute:
        print("MODO VALIDACIÓN: no se modificó Snowflake. NO EJECUTAR --execute aún.")
        return
    if not args.confirm_nonempty_write:
        raise RuntimeError(
            "DELTA NO VACÍO: carga bloqueada preventivamente. "
            "Falta la prueba aislada con MERGE. No uses --confirm-nonempty-write todavía."
        )
    delta_digest = file_sha256(DELTA_CSV)
    apply_delta(audit, delta_digest)


if __name__ == "__main__":
    main()
