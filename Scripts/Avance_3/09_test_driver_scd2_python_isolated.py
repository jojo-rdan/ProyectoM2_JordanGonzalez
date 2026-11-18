"""FleetLogix Avance 3: prueba de integración aislada del SCD2 REAL de Python.

Uso: python Scripts/Avance_3/09_test_driver_scd2_python_isolated.py

Importa y ejecuta las funciones stage_rows() y apply_driver_scd2() del
04_load_master_dimensions.py ORIGINAL; intercepta el SQL de SCD2 para que
opere exclusivamente sobre una tabla TEMPORARY con IDENTITY independiente.

NO edita CSV, PostgreSQL, ANALYTICS.DIM_DRIVER ni FACT_DELIVERIES.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
LOADER_PATH = Path(__file__).with_name("04_load_master_dimensions.py")
TEMP_HISTORY = "STAGING.TMP_SCD2_DRIVER_PYTHON_TEST"
TEMP_INCOMING = "STAGING.TMP_DRIVER_LOAD"  # Nombre utilizado por el cargador original.
TEST_STATUS = "SCD2_TEST"
IDENTITY_START = 900_000_000_000

TRACKED_FIELDS = (
    "EMPLOYEE_CODE", "FIRST_NAME", "LAST_NAME", "LICENSE_EXPIRY",
    "HIRE_DATE", "DRIVER_STATUS", "ASSIGNED_ZONE",
)


@dataclass(frozen=True)
class Counts:
    versions: int
    current: int
    historic: int
    keys_unique: int
    invalid_windows: int
    current_with_end: int
    historic_without_end: int
    total_drivers: int


class GuardedSCD2Cursor:
    """Solo admite las dos operaciones SCD2 del cargador, redirigidas.

    Cualquier otra operación originada desde apply_driver_scd2() se rechaza,
    en vez de intentar ejecutarla sobre una tabla real.
    """

    def __init__(self, actual_cursor):
        self.actual = actual_cursor
        self.calls = 0

    def execute(self, statement: str, params=None, **kwargs):
        cleaned = statement.lstrip().upper()
        if not (
            cleaned.startswith("UPDATE ANALYTICS.DIM_DRIVER ")
            or cleaned.startswith("INSERT INTO ANALYTICS.DIM_DRIVER ")
        ):
            raise RuntimeError("Operación SQL no permitida en prueba aislada")

        rewritten, count = re.subn(
            r"\bANALYTICS\.DIM_DRIVER\b",
            TEMP_HISTORY,
            statement,
            flags=re.IGNORECASE,
        )
        if count == 0 or "ANALYTICS." in rewritten.upper():
            raise RuntimeError("SQL no redirigido por completo: ejecución bloqueada")

        # Protección adicional: ninguna operación escrita puede apuntar a
        # otra tabla. La sentencia sigue siendo el SQL original del loader.
        self.calls += 1
        if params is None:
            return self.actual.execute(rewritten, **kwargs)
        return self.actual.execute(rewritten, params, **kwargs)


def load_original_loader():
    if not LOADER_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró {LOADER_PATH}. Coloca este script junto al cargador."
        )
    spec = importlib.util.spec_from_file_location("fleetlogix_master_loader", LOADER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo importar el cargador original")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in ("read_and_validate", "stage_rows", "apply_driver_scd2", "SPECS"):
        if not hasattr(module, attr):
            raise RuntimeError(f"El cargador original no expone {attr}")
    if module.SPECS["driver"]["temp"] != TEMP_INCOMING:
        raise RuntimeError("El nombre del staging en 04 cambió; prueba cancelada")
    return module


def canonical_hash(driver_row: dict[str, str]) -> str:
    payload = json.dumps(
        {name.lower(): driver_row.get(name) or "" for name in TRACKED_FIELDS},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_test_rows(loader):
    rows = loader.read_and_validate("driver")
    columns = loader.SPECS["driver"]["fields"]
    first = dict(zip(columns, rows[0]))
    if canonical_hash(first) != first["ATTRIBUTE_HASH"]:
        raise RuntimeError(
            "El hash del CSV no coincide con el algoritmo del transformador; "
            "no se puede efectuar una prueba fidedigna."
        )
    changed = first.copy()
    changed["DRIVER_STATUS"] = TEST_STATUS
    changed["ATTRIBUTE_HASH"] = canonical_hash(changed)
    if changed["ATTRIBUTE_HASH"] == first["ATTRIBUTE_HASH"]:
        raise RuntimeError("El cambio no alteró el hash")

    result_rows = [tuple(changed[col] for col in columns)] + rows[1:]
    return result_rows, int(first["DRIVER_ID"]), first


def create_temp_history(cursor):
    # Se declara IDENTITY LOCAL: no CLONE de la tabla real. Es importante:
    # clonar tablas con un DEFAULT NEXTVAL puede mantener la secuencia original.
    cursor.execute(f"""
        CREATE TEMPORARY TABLE {TEMP_HISTORY} (
            DRIVER_KEY NUMBER(38,0) IDENTITY({IDENTITY_START},1) PRIMARY KEY,
            DRIVER_ID NUMBER(38,0) NOT NULL,
            EMPLOYEE_CODE VARCHAR(100) NOT NULL,
            FIRST_NAME VARCHAR(100) NOT NULL,
            LAST_NAME VARCHAR(100) NOT NULL,
            LICENSE_EXPIRY DATE,
            HIRE_DATE DATE,
            DRIVER_STATUS VARCHAR(30),
            ASSIGNED_ZONE VARCHAR(100),
            VALID_FROM TIMESTAMP_NTZ NOT NULL,
            VALID_TO TIMESTAMP_NTZ,
            IS_CURRENT BOOLEAN NOT NULL DEFAULT TRUE,
            ATTRIBUTE_HASH VARCHAR(64),
            DW_LOADED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """)
    cursor.execute("SELECT MAX(DRIVER_KEY) FROM ANALYTICS.DIM_DRIVER")
    max_real = cursor.fetchone()[0]
    if max_real is None or int(max_real) >= IDENTITY_START:
        raise RuntimeError("Las claves de origen se solaparían con la secuencia de prueba")
    cursor.execute(f"""
        INSERT INTO {TEMP_HISTORY} (
            DRIVER_KEY, DRIVER_ID, EMPLOYEE_CODE, FIRST_NAME, LAST_NAME,
            LICENSE_EXPIRY, HIRE_DATE, DRIVER_STATUS, ASSIGNED_ZONE,
            VALID_FROM, VALID_TO, IS_CURRENT, ATTRIBUTE_HASH, DW_LOADED_AT
        )
        SELECT DRIVER_KEY, DRIVER_ID, EMPLOYEE_CODE, FIRST_NAME, LAST_NAME,
               LICENSE_EXPIRY, HIRE_DATE, DRIVER_STATUS, ASSIGNED_ZONE,
               VALID_FROM, VALID_TO, IS_CURRENT, ATTRIBUTE_HASH, DW_LOADED_AT
        FROM ANALYTICS.DIM_DRIVER
    """)


def get_counts(cursor) -> Counts:
    cursor.execute(f"""
        SELECT COUNT(*),
               COUNT_IF(IS_CURRENT),
               COUNT_IF(NOT IS_CURRENT),
               COUNT(DISTINCT DRIVER_KEY),
               COUNT_IF(VALID_TO IS NOT NULL AND VALID_TO <= VALID_FROM),
               COUNT_IF(IS_CURRENT AND VALID_TO IS NOT NULL),
               COUNT_IF(NOT IS_CURRENT AND VALID_TO IS NULL),
               COUNT(DISTINCT DRIVER_ID)
        FROM {TEMP_HISTORY}
    """)
    return Counts(*(int(value or 0) for value in cursor.fetchone()))


def assert_expected(cursor, driver_id: int, before: dict[str, str], changed_at: str):
    result = get_counts(cursor)
    expected = Counts(401, 400, 1, 401, 0, 0, 0, 400)
    if result != expected:
        raise RuntimeError(f"Conteos SCD2 inválidos: {result}; esperado {expected}")
    cursor.execute(f"""
        SELECT DRIVER_KEY, DRIVER_STATUS, ATTRIBUTE_HASH,
               VALID_FROM, VALID_TO, IS_CURRENT
        FROM {TEMP_HISTORY}
        WHERE DRIVER_ID=%s
        ORDER BY VALID_FROM, DRIVER_KEY
    """, (driver_id,))
    versions = cursor.fetchall()
    if len(versions) != 2:
        raise RuntimeError("El conductor elegido no tiene exactamente dos versiones")
    old, new = versions
    if (
        old[1] != before["DRIVER_STATUS"]
        or old[2] != before["ATTRIBUTE_HASH"]
        or old[5] is not False
        or new[1] != TEST_STATUS
        or new[5] is not True
        or new[4] is not None
        or old[4] != new[3]
        or old[0] == new[0]
        or new[2] == old[2]
    ):
        raise RuntimeError("Versiones SCD2 no cumplen estado, hash o vigencia")
    return result, old[0], new[0]


def real_snapshot(cursor, driver_id: int):
    cursor.execute("""
        SELECT DRIVER_KEY, DRIVER_STATUS, ATTRIBUTE_HASH, VALID_FROM,
               VALID_TO, IS_CURRENT
        FROM ANALYTICS.DIM_DRIVER WHERE DRIVER_ID=%s
        ORDER BY DRIVER_KEY
    """, (driver_id,))
    one_driver = cursor.fetchall()
    cursor.execute("""
        SELECT (SELECT COUNT(*) FROM ANALYTICS.DIM_DRIVER),
               (SELECT COUNT_IF(IS_CURRENT) FROM ANALYTICS.DIM_DRIVER),
               (SELECT COUNT(*) FROM ANALYTICS.FACT_DELIVERIES),
               (SELECT COUNT(*) FROM ANALYTICS.DIM_DRIVER
                   WHERE DRIVER_STATUS='SCD2_TEST')
    """)
    totals = tuple(int(v or 0) for v in cursor.fetchone())
    return one_driver, totals


def main():
    print("Prueba Python SCD2 aislada — FleetLogix")
    loader = load_original_loader()
    rows, driver_id, original = prepare_test_rows(loader)
    required = (
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA"
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Variables faltantes en .env: " + ", ".join(missing))
    print(f"CSV validado. Cambio simulado en memoria: DRIVER_ID={driver_id}.")
    print("Abriendo OAuth de navegador para Snowflake...")
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
            cur.execute("SELECT CURRENT_DATABASE(), CURRENT_ROLE()")
            db, role = cur.fetchone()
            if db != "FLEETLOGIX_DWH" or role != "SYSADMIN":
                raise RuntimeError(
                    f"Contexto inesperado ({db}/{role}); prueba cancelada"
                )

            baseline = real_snapshot(cur, driver_id)
            if baseline[1] != (400, 400, 400000, 0):
                raise RuntimeError(
                    f"Las tablas reales no están en el estado esperado: {baseline[1]}"
                )
            if len(baseline[0]) != 1:
                raise RuntimeError("El conductor original debe tener una versión")

            # Todas las DDL ocurren ANTES de BEGIN: Snowflake auto-commit en DDL.
            create_temp_history(cur)
            loader.stage_rows(cur, "driver", rows)
            print("Tablas TEMPORARY creadas; 400 conductores de origen cargados.")

            initial = get_counts(cur)
            if initial != Counts(400, 400, 0, 400, 0, 0, 0, 400):
                raise RuntimeError(f"Copia temporal inicial inconsistente: {initial}")

            changed_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
            guarded = GuardedSCD2Cursor(cur)
            for passage in (1, 2):
                try:
                    cur.execute("BEGIN")
                    loader.apply_driver_scd2(guarded, changed_at)
                    results, old_key, new_key = assert_expected(
                        cur, driver_id, original, changed_at
                    )
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
                print(
                    f"PASADA {passage}: {results.versions} versiones, "
                    f"{results.current} actuales, "
                    f"{results.historic} históricas, "
                    f"{results.invalid_windows} vigencias inválidas."
                )
                print(f"  DRIVER_KEY histórico={old_key}; actual={new_key}")

            if guarded.calls != 4:
                raise RuntimeError("La función original no ejecutó exactamente 4 sentencias SCD2")

            after = real_snapshot(cur, driver_id)
            if baseline != after:
                raise RuntimeError("¡El estado real cambió durante la prueba!")
            print(
                "TABLAS REALES INTACTAS: DIM_DRIVER=400, "
                "CONDUCTORES_ACTUALES=400, FACT_DELIVERIES=400000, "
                "SCD2_TEST=0"
            )
            print("PRUEBA DE INTEGRACIÓN PYTHON SCD2 APROBADA")
    finally:
        conn.close()
        print("Conexión cerrada. Tablas temporales descartadas por la sesión.")


if __name__ == "__main__":
    main()
