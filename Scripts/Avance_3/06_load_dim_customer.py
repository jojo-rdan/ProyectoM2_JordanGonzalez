"""FleetLogix Avance 3 — carga inicial idempotente de DIM_CUSTOMER.

Uso desde la raíz del repositorio:
    python Scripts/Avance_3/06_load_dim_customer.py
    python Scripts/Avance_3/06_load_dim_customer.py --execute

Sin --execute solo valida el CSV local. No imprime datos de clientes.
"""

import argparse
import csv
import json
import os
import re
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "staging" / "avance_3" / "prepared" / "dim_customer.csv"
load_dotenv(ROOT / ".env")

EXPECTED_ROWS = 389_334  # línea base del Avance 3; cambiar si se amplía el origen
EXPECTED_COLUMNS = [
    "CUSTOMER_BK",
    "CUSTOMER_NAME",
    "DELIVERY_ADDRESS",
    "CUSTOMER_NAME_NORMALIZED",
    "DELIVERY_ADDRESS_NORMALIZED",
    "IDENTIFICATION_METHOD",
]
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def expected_bk(name_normalized: str, address_normalized: str) -> str:
    payload = json.dumps(
        [name_normalized, address_normalized],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def check_csv() -> int:
    if not CSV_PATH.is_file():
        raise FileNotFoundError(f"No existe el CSV esperado: {CSV_PATH}")

    print("Verificando CSV local (sin enviar datos)...")
    seen: set[str] = set()
    total = 0
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "Las columnas no coinciden con el archivo preparado. "
                f"Encontradas: {reader.fieldnames}"
            )
        for row in reader:
            total += 1
            if None in row or not all(row.get(k) for k in EXPECTED_COLUMNS):
                raise ValueError(f"Fila incompleta o inválida: número {total}")
            bk = row["CUSTOMER_BK"]
            if not SHA256_PATTERN.fullmatch(bk):
                raise ValueError(f"CUSTOMER_BK inválida en fila {total}")
            if bk != expected_bk(
                row["CUSTOMER_NAME_NORMALIZED"],
                row["DELIVERY_ADDRESS_NORMALIZED"],
            ):
                raise ValueError(f"CUSTOMER_BK no coincide en fila {total}")
            if bk in seen:
                raise ValueError(f"CUSTOMER_BK repetida en fila {total}")
            seen.add(bk)
            if total % 100_000 == 0:
                print(f"  Filas revisadas: {total:,}")

    if total != EXPECTED_ROWS:
        raise ValueError(
            f"Se esperaban {EXPECTED_ROWS:,} clientes y se obtuvieron {total:,}"
        )
    print(f"CSV OK: {total:,} filas únicas; claves SHA-256 correctas")
    return total


def load_to_snowflake(expected: int) -> None:
    import snowflake.connector

    required = (
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Faltan variables del .env: {', '.join(missing)}")

    # El comando PUT requiere una ruta 'file://C:/...' en Windows.
    # Las comillas SQL protegen rutas con espacios o comillas simples.
    local_path = CSV_PATH.resolve().as_posix()
    quoted_file_uri = ("file://" + local_path).replace("'", "''")

    print("Conectando con Snowflake mediante OAuth de navegador...")
    connection = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="OAUTH_AUTHORIZATION_CODE",
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        login_timeout=120,
    )
    in_transaction = False
    try:
        with connection.cursor() as cur:
            # Los objetos temporales desaparecen al cerrar esta sesión.
            cur.execute("""
                CREATE TEMPORARY TABLE TMP_FLEETLOGIX_CUSTOMERS (
                    CUSTOMER_BK VARCHAR(64),
                    CUSTOMER_NAME VARCHAR,
                    DELIVERY_ADDRESS VARCHAR,
                    CUSTOMER_NAME_NORMALIZED VARCHAR,
                    DELIVERY_ADDRESS_NORMALIZED VARCHAR,
                    IDENTIFICATION_METHOD VARCHAR(80)
                )
            """)
            cur.execute("""
                CREATE TEMPORARY STAGE TMP_FLEETLOGIX_CUSTOMER_FILES
                FILE_FORMAT = (
                    TYPE = CSV
                    FIELD_DELIMITER = ','
                    SKIP_HEADER = 1
                    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
                    MULTI_LINE = TRUE
                    ENCODING = 'UTF8'
                    EMPTY_FIELD_AS_NULL = FALSE
                    ESCAPE_UNENCLOSED_FIELD = NONE
                )
            """)
            print("Staging temporal preparado.")

            cur.execute(
                f"PUT '{quoted_file_uri}' @TMP_FLEETLOGIX_CUSTOMER_FILES "
                "AUTO_COMPRESS = TRUE OVERWRITE = TRUE PARALLEL = 4"
            )
            put_results = cur.fetchall()
            if not put_results or any(str(r[-2]).upper() not in {"UPLOADED", "SKIPPED"} for r in put_results):
                raise RuntimeError(f"La carga PUT no se confirmó: {put_results}")
            print("Archivo transferido al stage temporal.")

            cur.execute("""
                COPY INTO TMP_FLEETLOGIX_CUSTOMERS
                FROM @TMP_FLEETLOGIX_CUSTOMER_FILES
                ON_ERROR = ABORT_STATEMENT
            """)
            copy_results = cur.fetchall()
            if not copy_results:
                raise RuntimeError("COPY INTO no devolvió confirmación")
            print("COPY INTO staging completado.")

            cur.execute("""
                SELECT
                    COUNT(*) AS TOTAL,
                    COUNT(DISTINCT CUSTOMER_BK) AS CLAVES_UNICAS,
                    COUNT_IF(
                        CUSTOMER_BK IS NULL OR CUSTOMER_NAME IS NULL
                        OR DELIVERY_ADDRESS IS NULL
                        OR CUSTOMER_NAME_NORMALIZED IS NULL
                        OR DELIVERY_ADDRESS_NORMALIZED IS NULL
                    ) AS NULOS
                FROM TMP_FLEETLOGIX_CUSTOMERS
            """)
            total, unique, invalid = cur.fetchone()
            print(f"Staging: {total:,} filas; {unique:,} claves únicas; {invalid} nulos")
            if (total, unique, invalid) != (expected, expected, 0):
                raise RuntimeError("Validación del staging falló: no se modifica DIM_CUSTOMER")

            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT CUSTOMER_BK)
                FROM ANALYTICS.DIM_CUSTOMER
            """)
            before, distinct_before = cur.fetchone()
            if before != distinct_before:
                raise RuntimeError("DIM_CUSTOMER tiene CUSTOMER_BK duplicadas: detener carga")
            print(f"DIM_CUSTOMER antes: {before:,} filas")

            # DDL y COPY ya terminaron. Solo el MERGE corre dentro de la transacción.
            cur.execute("BEGIN")
            in_transaction = True
            cur.execute("""
                MERGE INTO ANALYTICS.DIM_CUSTOMER AS target
                USING TMP_FLEETLOGIX_CUSTOMERS AS source
                   ON target.CUSTOMER_BK = source.CUSTOMER_BK
                WHEN MATCHED AND (
                    target.CUSTOMER_NAME <> source.CUSTOMER_NAME
                    OR target.DELIVERY_ADDRESS <> source.DELIVERY_ADDRESS
                ) THEN UPDATE SET
                    CUSTOMER_NAME = source.CUSTOMER_NAME,
                    DELIVERY_ADDRESS = source.DELIVERY_ADDRESS,
                    CUSTOMER_NAME_NORMALIZED = source.CUSTOMER_NAME_NORMALIZED,
                    DELIVERY_ADDRESS_NORMALIZED = source.DELIVERY_ADDRESS_NORMALIZED,
                    IDENTIFICATION_METHOD = source.IDENTIFICATION_METHOD
                WHEN NOT MATCHED THEN INSERT (
                    CUSTOMER_BK,
                    CUSTOMER_NAME,
                    DELIVERY_ADDRESS,
                    CUSTOMER_NAME_NORMALIZED,
                    DELIVERY_ADDRESS_NORMALIZED,
                    IDENTIFICATION_METHOD
                ) VALUES (
                    source.CUSTOMER_BK,
                    source.CUSTOMER_NAME,
                    source.DELIVERY_ADDRESS,
                    source.CUSTOMER_NAME_NORMALIZED,
                    source.DELIVERY_ADDRESS_NORMALIZED,
                    source.IDENTIFICATION_METHOD
                )
            """)
            merge_result = cur.fetchone()
            print(f"MERGE (insertadas / actualizadas, según Snowflake): {merge_result}")

            cur.execute("""
                SELECT COUNT(*)
                FROM TMP_FLEETLOGIX_CUSTOMERS s
                LEFT JOIN ANALYTICS.DIM_CUSTOMER d
                    ON d.CUSTOMER_BK = s.CUSTOMER_BK
                WHERE d.CUSTOMER_BK IS NULL
            """)
            missing_in_target = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT CUSTOMER_BK)
                FROM ANALYTICS.DIM_CUSTOMER
            """)
            after, distinct_after = cur.fetchone()
            if missing_in_target != 0 or after != distinct_after or after < expected:
                raise RuntimeError(
                    "Validación posterior falló; se revertirá el MERGE "
                    f"(faltantes={missing_in_target}, total={after}, únicas={distinct_after})"
                )
            cur.execute("COMMIT")
            in_transaction = False
            print(f"CARGA CONFIRMADA (COMMIT) — DIM_CUSTOMER: {after:,} filas")
    except Exception:
        if in_transaction:
            try:
                connection.cursor().execute("ROLLBACK")
                print("MERGE revertido mediante ROLLBACK.")
            except Exception:
                print("No pudo confirmarse el ROLLBACK; verificar Snowflake.")
        raise
    finally:
        connection.close()
        print("Conexión Snowflake cerrada.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga idempotente de DIM_CUSTOMER")
    parser.add_argument(
        "--execute", action="store_true",
        help="Tras las comprobaciones locales, carga los clientes a Snowflake",
    )
    options = parser.parse_args()
    expected = check_csv()
    if options.execute:
        load_to_snowflake(expected)
    else:
        print("MODO VALIDACIÓN: no se enviaron datos a Snowflake.")
        print("Para cargar, ejecuta de nuevo con --execute.")


if __name__ == "__main__":
    main()
