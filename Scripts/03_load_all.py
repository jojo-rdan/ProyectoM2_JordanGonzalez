"""Carga TODOS los CSV de FleetLogix con una transacción y COPY.

Uso: python Scripts/03_load_all.py --load
Por seguridad, aborta si alguna de las seis tablas contiene datos.
No elimina tablas ni filas y no ejecuta ningún TRUNCATE.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TABLE_COLS = {
    "vehicles": ["vehicle_id", "license_plate", "vehicle_type", "capacity_kg", "fuel_type", "acquisition_date", "status"],
    "drivers": ["driver_id", "employee_code", "first_name", "last_name", "license_number", "license_expiry", "phone", "hire_date", "status"],
    "routes": ["route_id", "route_code", "origin_city", "destination_city", "distance_km", "estimated_duration_hours", "toll_cost"],
    "trips": ["trip_id", "vehicle_id", "driver_id", "route_id", "departure_datetime", "arrival_datetime", "fuel_consumed_liters", "total_weight_kg", "status"],
    "deliveries": ["delivery_id", "trip_id", "tracking_number", "customer_name", "delivery_address", "package_weight_kg", "scheduled_datetime", "delivered_datetime", "delivery_status", "recipient_signature"],
    "maintenance": ["maintenance_id", "vehicle_id", "maintenance_date", "maintenance_type", "description", "cost", "next_maintenance_date", "performed_by"],
}
EXPECTED = {"vehicles": 200, "drivers": 400, "routes": 50, "trips": 100_000, "deliveries": 400_000, "maintenance": 5_000}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--load", action="store_true", help="Autorizar la carga en PostgreSQL")
    args = parser.parse_args()
    if not args.load:
        print("Sin cambios: para cargar explícitamente usa --load")
        return
    load_dotenv(ROOT / ".env")
    config = dict(host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
                  dbname=os.getenv("PGDATABASE", "fleetlogix_db"), user=os.getenv("PGUSER", "postgres"),
                  password=os.getenv("PGPASSWORD"), connect_timeout=10)
    if config["dbname"] != "fleetlogix_db":
        raise ValueError("La base destino debe ser fleetlogix_db")
    for table in TABLE_COLS:
        if not (DATA / f"{table}.csv").is_file():
            raise FileNotFoundError(DATA / f"{table}.csv")
    con = psycopg2.connect(**config)
    try:
        con.autocommit = False
        with con.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "fleetlogix_db"
            cur.execute("LOCK TABLE vehicles, drivers, routes, trips, deliveries, maintenance IN EXCLUSIVE MODE")
            for table in TABLE_COLS:
                cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                if cur.fetchone()[0] != 0:
                    raise RuntimeError(f"{table} no está vacía. Carga cancelada, sin eliminar datos.")
            for table, cols in TABLE_COLS.items():
                path = DATA / f"{table}.csv"
                with path.open("r", newline="", encoding="utf-8-sig") as infile:
                    reader = csv.DictReader(infile)
                    expected_source = cols if table in {"trips", "deliveries", "maintenance"} else cols[1:]
                    if reader.fieldnames != expected_source:
                        raise ValueError(f"Columnas inesperadas en {path}: {reader.fieldnames}")
                    # Las maestras aún no tenían PK en CSV; añadimos 1..N manteniendo orden.
                    if table in {"vehicles", "drivers", "routes"}:
                        contents = io.StringIO()
                        writer = csv.writer(contents)
                        writer.writerow(cols)
                        count = 0
                        for count, row in enumerate(reader, start=1):
                            writer.writerow([count] + [row[c] for c in cols[1:]])
                        contents.seek(0)
                        source = contents
                    else:
                        source = infile
                        # Regresa al inicio, pues DictReader ya consumió cabecera.
                        source.seek(0)
                # Para archivos grandes se abre de nuevo para evitar retener en RAM.
                if table not in {"vehicles", "drivers", "routes"}:
                    with path.open("r", newline="", encoding="utf-8-sig") as reader_file:
                        cur.copy_expert(f"COPY public.{table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)", reader_file)
                else:
                    cur.copy_expert(f"COPY public.{table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)", source)
                cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                actual = cur.fetchone()[0]
                if actual != EXPECTED[table]:
                    raise RuntimeError(f"Conteo incorrecto de {table}: {actual}")
                # COPY con IDs explícitos no sincroniza SERIAL; ajusta la secuencia.
                cur.execute("SELECT setval(pg_get_serial_sequence(%s, %s), %s, true)",
                            (f"public.{table}", cols[0], actual))
                print(f"OK {table}: {actual:,} registros")
        con.commit()
        print("CARGA COMPLETADA: 505650 registros; transacción confirmada.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    main()
