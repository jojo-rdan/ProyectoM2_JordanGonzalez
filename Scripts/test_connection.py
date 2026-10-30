"""Prueba de conexión segura a fleetlogix_db. No modifica datos."""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
missing = [name for name in required if not os.getenv(name)]
if missing:
    raise SystemExit("Faltan variables en .env: " + ", ".join(missing))

with psycopg2.connect(
    host=os.environ["PGHOST"],
    port=os.environ["PGPORT"],
    dbname=os.environ["PGDATABASE"],
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"],
    connect_timeout=10,
) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, version()")
        database, username, version = cur.fetchone()
        if database != "fleetlogix_db":
            raise SystemExit(f"Base inesperada: {database}")
        print("CONEXIÓN OK")
        print("Base:", database)
        print("Usuario:", username)
        print("PostgreSQL:", version.split(',')[0])
