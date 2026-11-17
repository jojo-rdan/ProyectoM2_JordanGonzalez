import os
from getpass import getpass
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUTPUT = ROOT / "data" / "staging" / "avance_3"

QUERIES = {
    "vehicles": """
        SELECT
            vehicle_id,
            license_plate,
            vehicle_type,
            capacity_kg,
            fuel_type,
            acquisition_date,
            status
        FROM public.vehicles
        ORDER BY vehicle_id
    """,
    "drivers": """
        SELECT
            driver_id,
            employee_code,
            first_name,
            last_name,
            license_expiry,
            hire_date,
            status
        FROM public.drivers
        ORDER BY driver_id
    """,
    "routes": """
        SELECT
            route_id,
            route_code,
            origin_city,
            destination_city,
            distance_km,
            estimated_duration_hours,
            toll_cost
        FROM public.routes
        ORDER BY route_id
    """,
}

EXPECTED = {
    "vehicles": 200,
    "drivers": 400,
    "routes": 50,
}


def main():
    print("Iniciando extraccion PostgreSQL...")

    password = os.getenv("PGPASSWORD") or getpass(
        "Contraseña PostgreSQL: "
    )

    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "fleetlogix_db"),
        user=os.getenv("PGUSER", "postgres"),
        password=password,
        connect_timeout=15,
    )

    frames = {}

    try:
        # Solo lectura: este script no modifica PostgreSQL.
        conn.set_session(readonly=True, autocommit=True)

        with conn.cursor() as cursor:
            for table, query in QUERIES.items():
                cursor.execute(query)

                columns = [
                    description.name
                    for description in cursor.description
                ]

                df = pd.DataFrame(
                    cursor.fetchall(),
                    columns=columns,
                )

                pk = {
                    "vehicles": "vehicle_id",
                    "drivers": "driver_id",
                    "routes": "route_id",
                }[table]

                if len(df) != EXPECTED[table]:
                    raise ValueError(
                        f"{table}: se esperaban "
                        f"{EXPECTED[table]} registros, "
                        f"se obtuvieron {len(df)}"
                    )

                if df[pk].isna().any():
                    raise ValueError(
                        f"{table}: hay claves nulas"
                    )

                if df[pk].duplicated().any():
                    raise ValueError(
                        f"{table}: hay claves duplicadas"
                    )

                frames[table] = df
                print(
                    f"{table}: {len(df)} registros OK"
                )

        OUTPUT.mkdir(parents=True, exist_ok=True)

        for table, df in frames.items():
            path = OUTPUT / f"{table}.csv"
            df.to_csv(path, index=False, encoding="utf-8")

        print("\nEXTRACCION COMPLETADA")
        print(f"Total registros: {sum(map(len, frames.values()))}")
        print(f"Archivos guardados en: {OUTPUT}")

    finally:
        conn.close()
        print("Conexion PostgreSQL cerrada.")


if __name__ == "__main__":
    main()