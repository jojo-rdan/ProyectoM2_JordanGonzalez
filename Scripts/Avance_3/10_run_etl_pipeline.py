"""FleetLogix Avance #3: orquestador manual con auditoría en Snowflake.

Modos:
  --audit-test  Verifica datos del DWH y registra un RUN y dos STEPS.
                No modifica ANALYTICS ni PostgreSQL.
  --full        Reejecuta secuencialmente los 7 scripts existentes y
                registra sus resultados. No es aún una carga incremental,
                ni un servicio desatendido. NO ejecutar sin revisar primero.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Callable, TypeVar

import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "Scripts" / "Avance_3"
load_dotenv(ROOT / ".env")

RUNS = "FLEETLOGIX_DWH.CONTROL.ETL_RUNS"
STEPS = "FLEETLOGIX_DWH.CONTROL.ETL_RUN_STEPS"
EXPECTED_REVENUE = Decimal("6270850032.24")

# Orden validado durante la carga inicial del modelo dimensional.
# Los scripts 06 y 08 necesitan --execute; el 04 carga directamente.
PIPELINE = (
    ("EXTRACT_MASTERS", "02_extract_master_data.py", ()),
    ("TRANSFORM_MASTERS", "03_transform_master_data.py", ()),
    ("LOAD_MASTERS", "04_load_master_dimensions.py", ()),
    ("PREPARE_CUSTOMERS", "05_extract_transform_customers.py", ()),
    ("LOAD_CUSTOMERS", "06_load_dim_customer.py", ("--execute",)),
    ("PREPARE_FACTS", "07_extract_transform_fact_deliveries.py", ()),
    ("LOAD_FACTS", "08_load_fact_deliveries.py", ("--execute",)),
)

T = TypeVar("T")


def connect_audit():
    required = (
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(missing))

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="OAUTH_AUTHORIZATION_CODE",
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema="CONTROL",
        login_timeout=120,
        enable_server_session_keep_alive_auto_detection=False,
    )
    # Cada evento de auditoría se confirma independientemente.
    # Un fallo posterior del ETL no borra la información del intento.
    conn.autocommit(True)
    return conn


def bounded_error(exc: Exception) -> str:
    # No se almacenan volcados de entorno, stdout ni trazas extensas.
    return f"{type(exc).__name__}: {str(exc)}"[:1000]


class AuditLog:
    def __init__(self, conn, run_id: str):
        self.conn = conn
        self.run_id = run_id

    def start(self, run_mode: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {RUNS}
                    (RUN_ID, PIPELINE_NAME, RUN_MODE, STATUS, CREATED_BY)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    self.run_id, "FLEETLOGIX_ADVANCE_3",
                    run_mode, "RUNNING", os.environ["SNOWFLAKE_USER"],
                ),
            )

    def finish(self, status: str, error: str | None = None) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {RUNS}
                SET FINISHED_AT = CURRENT_TIMESTAMP(),
                    STATUS = %s,
                    ERROR_MESSAGE = %s
                WHERE RUN_ID = %s
                """,
                (status, error, self.run_id),
            )

    def execute_step(self, name: str, fn: Callable[[], T]) -> T:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {STEPS}
                    (RUN_ID, STEP_NAME, STATUS)
                VALUES (%s, %s, %s)
                """,
                (self.run_id, name, "RUNNING"),
            )

        try:
            result = fn()
        except Exception as exc:
            self._finish_step(name, "FAILED", {"error": bounded_error(exc)})
            raise
        else:
            details = result if isinstance(result, dict) else {"result": "OK"}
            self._finish_step(name, "SUCCESS", details)
            return result

    def _finish_step(self, name: str, status: str, details: dict) -> None:
        # DETAILS es VARIANT: el JSON se envía como parámetro.
        payload = json.dumps(details, ensure_ascii=False, default=str)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {STEPS}
                SET STATUS = %s,
                    FINISHED_AT = CURRENT_TIMESTAMP(),
                    DETAILS = PARSE_JSON(%s)
                WHERE RUN_ID = %s AND STEP_NAME = %s
                  AND STATUS = 'RUNNING'
                """,
                (status, payload, self.run_id, name),
            )


def check_dimensions(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
              (SELECT COUNT(*) FROM FLEETLOGIX_DWH.ANALYTICS.DIM_DRIVER),
              (SELECT COUNT(*) FROM FLEETLOGIX_DWH.ANALYTICS.DIM_CUSTOMER),
              (SELECT COUNT(*) FROM FLEETLOGIX_DWH.ANALYTICS.FACT_DELIVERIES)
        """)
        drivers, customers, deliveries = map(int, cur.fetchone())

    if (drivers, customers, deliveries) != (400, 389334, 400000):
        raise RuntimeError(
            "Conteos del DWH inesperados: "
            f"conductores={drivers}, clientes={customers}, entregas={deliveries}"
        )
    print(f"Dimensiones/hechos OK: {drivers} conductores, "
          f"{customers:,} clientes, {deliveries:,} entregas")
    return {"drivers": drivers, "customers": customers, "deliveries": deliveries}


def check_revenue(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*), COUNT(DISTINCT DELIVERY_ID),
                   COUNT_IF(REVENUE_POLICY_VERSION = 'SYNTHETIC_REVENUE_V1'),
                   COALESCE(SUM(ESTIMATED_REVENUE_COP), 0)
            FROM FLEETLOGIX_DWH.ANALYTICS.FACT_DELIVERIES
        """)
        count, unique, policy_count, revenue = cur.fetchone()

    total = Decimal(str(revenue))
    if (int(count), int(unique), int(policy_count)) != (400000, 400000, 400000):
        raise RuntimeError("Cantidades/versión de la política de ingresos inesperadas")
    if total != EXPECTED_REVENUE:
        raise RuntimeError(
            f"Ingreso total distinto: {total} (esperado {EXPECTED_REVENUE})"
        )
    print(f"Política de ingresos OK: {total:,.2f} COP sintéticos")
    return {"deliveries": int(count), "revenue_policy": "SYNTHETIC_REVENUE_V1",
            "estimated_revenue_cop": str(total), "synthetic": True}


def run_full_pipeline(audit: AuditLog, conn) -> None:
    missing = [file for _, file, _ in PIPELINE if not (SCRIPTS / file).is_file()]
    if missing:
        raise FileNotFoundError("No existen scripts requeridos: " + ", ".join(missing))

    for name, file, flags in PIPELINE:
        def run_script(filename=file, options=flags):
            print(f"\n>>> {filename} {' '.join(options)}", flush=True)
            # No se capturan contraseñas, tokens ni salidas de los hijos en Snowflake.
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / filename), *options],
                cwd=str(ROOT),
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"El script {filename} terminó con código {result.returncode}"
                )
            return {"script": filename, "exit_code": result.returncode,
                    "row_metrics": "pendiente_de_integracion"}

        audit.execute_step(name, run_script)

    audit.execute_step("VERIFY_DWH_COUNTS", lambda: check_dimensions(conn))
    audit.execute_step("VERIFY_REVENUE_POLICY", lambda: check_revenue(conn))


def main() -> int:
    parser = argparse.ArgumentParser(description="FleetLogix: auditoría y orquestación manual")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--audit-test", action="store_true",
        help="Prueba auditoría con dos comprobaciones de lectura (predeterminado)",
    )
    modes.add_argument(
        "--full", action="store_true",
        help="Reejecuta los siete scripts completos con auditoría; NO incremental",
    )
    args = parser.parse_args()

    mode = "FULL_REFRESH_IDEMPOTENT" if args.full else "AUDIT_SMOKE"
    run_id = str(uuid.uuid4())
    print(f"FleetLogix | RUN_ID={run_id} | MODE={mode}", flush=True)
    print("Conectando a Snowflake para registrar auditoría...", flush=True)
    conn = connect_audit()
    audit = AuditLog(conn, run_id)
    registered = False

    try:
        audit.start(mode)
        registered = True
        if args.full:
            run_full_pipeline(audit, conn)
        else:
            audit.execute_step("CHECK_DIMENSIONS_AND_FACT", lambda: check_dimensions(conn))
            audit.execute_step("CHECK_SYNTHETIC_REVENUE", lambda: check_revenue(conn))

        audit.finish("SUCCESS")
        print(f"\nAUDITORÍA CONFIRMADA: SUCCESS | RUN_ID={run_id}")
        print("Las tablas ANALYTICS no fueron modificadas por el modo AUDIT_SMOKE."
              if not args.full else "Pipeline manual completo finalizado.")
        return 0
    except Exception as exc:
        if registered:
            try:
                audit.finish("FAILED", bounded_error(exc))
            except Exception as audit_exc:
                print(f"No se pudo finalizar la auditoría: {type(audit_exc).__name__}",
                      file=sys.stderr)
        print(f"\nERROR: {bounded_error(exc)}", file=sys.stderr)
        return 1
    finally:
        conn.close()
        print("Conexión de auditoría cerrada.")


if __name__ == "__main__":
    sys.exit(main())
