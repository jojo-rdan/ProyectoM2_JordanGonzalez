import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

REQUIRED = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
]

missing = [key for key in REQUIRED if not os.getenv(key)]

if missing:
    raise RuntimeError(
        "Faltan variables en .env: " + ", ".join(missing)
    )


def main():
    print("Conectando con Snowflake...")

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="OAUTH_AUTHORIZATION_CODE",
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        login_timeout=120,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    CURRENT_ROLE(),
                    CURRENT_WAREHOUSE(),
                    CURRENT_DATABASE(),
                    CURRENT_SCHEMA()
            """)

            role, warehouse, database, schema = cursor.fetchone()

            print("\nCONEXION SNOWFLAKE OK")
            print(f"Rol: {role}")
            print(f"Warehouse: {warehouse}")
            print(f"Base: {database}")
            print(f"Esquema: {schema}")

            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM DIM_DATE),
                    (SELECT COUNT(*) FROM DIM_TIME)
            """)

            total_dates, total_hours = cursor.fetchone()

            print(f"\nDIM_DATE: {total_dates} registros")
            print(f"DIM_TIME: {total_hours} registros")

    finally:
        conn.close()
        print("\nConexion cerrada correctamente.")


if __name__ == "__main__":
    main()