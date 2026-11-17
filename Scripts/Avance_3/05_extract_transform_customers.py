import csv
import json
import os
from datetime import datetime, timezone
from getpass import getpass
from hashlib import sha256
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUTPUT_DIR = ROOT / "data" / "staging" / "avance_3" / "prepared"

EXPECTED_DELIVERIES = 400_000
EXPECTED_CUSTOMERS = 389_334
BATCH_SIZE = 5000

SQL_COUNTS = """
SELECT
    COUNT(*) AS deliveries,
    COUNT(DISTINCT (
        LOWER(TRIM(customer_name)),
        LOWER(TRIM(delivery_address))
    )) AS customers
FROM public.deliveries
WHERE delivery_status = 'delivered';
"""

SQL_CUSTOMERS = """
SELECT DISTINCT ON (
    LOWER(TRIM(customer_name)),
    LOWER(TRIM(delivery_address))
)
    customer_name,
    delivery_address,
    LOWER(TRIM(customer_name)) AS name_normalized,
    LOWER(TRIM(delivery_address)) AS address_normalized
FROM public.deliveries
WHERE delivery_status = 'delivered'
ORDER BY
    LOWER(TRIM(customer_name)),
    LOWER(TRIM(delivery_address)),
    customer_name,
    delivery_address;
"""


def customer_business_key(name, address):
    """Identificador determinista de una identidad provisional."""
    payload = json.dumps(
        [name, address],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def main():
    print("FleetLogix: preparando DIM_CUSTOMER...")

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

    output_file = OUTPUT_DIR / "dim_customer.csv"
    temp_file = OUTPUT_DIR / "dim_customer.csv.tmp"
    audit_file = OUTPUT_DIR / "dim_customer_audit.json"

    try:
        conn.set_session(readonly=True, autocommit=False)

        with conn.cursor() as cursor:
            cursor.execute(SQL_COUNTS)
            total_deliveries, total_customers = cursor.fetchone()

        print(f"Entregas completadas: {total_deliveries}")
        print(f"Identidades provisionales: {total_customers}")

        if total_deliveries != EXPECTED_DELIVERIES:
            raise ValueError(
                "Cantidad de entregas diferente a la referencia."
            )

        if total_customers != EXPECTED_CUSTOMERS:
            raise ValueError(
                "Cantidad de clientes diferente a la referencia."
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        count = 0
        last_identity = None

        with open(
            temp_file, "w", newline="", encoding="utf-8"
        ) as file:
            writer = csv.writer(file)

            writer.writerow([
                "CUSTOMER_BK",
                "CUSTOMER_NAME",
                "DELIVERY_ADDRESS",
                "CUSTOMER_NAME_NORMALIZED",
                "DELIVERY_ADDRESS_NORMALIZED",
                "IDENTIFICATION_METHOD",
            ])

            with conn.cursor(
                name="fleetlogix_customer_stream"
            ) as cursor:
                cursor.itersize = BATCH_SIZE
                cursor.execute(SQL_CUSTOMERS)

                while True:
                    rows = cursor.fetchmany(BATCH_SIZE)

                    if not rows:
                        break

                    for name, address, norm_name, norm_address in rows:
                        if not norm_name or not norm_address:
                            raise ValueError(
                                "Identidad de cliente incompleta."
                            )

                        identity = (norm_name, norm_address)

                        if identity == last_identity:
                            raise ValueError(
                                "Identidad duplicada en la extracción."
                            )

                        last_identity = identity

                        key = customer_business_key(
                            norm_name, norm_address
                        )

                        writer.writerow([
                            key,
                            name,
                            address,
                            norm_name,
                            norm_address,
                            "NAME_ADDRESS_NORMALIZED",
                        ])

                        count += 1

                    if count % 50000 < BATCH_SIZE:
                        print(f"Procesados: {count:,}")

        if count != total_customers:
            raise ValueError(
                f"Se esperaban {total_customers}, "
                f"se prepararon {count}."
            )

        # Publicar el CSV solo si todas las validaciones pasan.
        os.replace(temp_file, output_file)

        audit = {
            "extracted_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "source": "PostgreSQL public.deliveries",
            "completed_deliveries": total_deliveries,
            "unique_customer_identities": count,
            "identification_method": "NAME_ADDRESS_NORMALIZED",
            "hash_algorithm": "SHA256",
            "status": "VALIDATED",
        }

        audit_file.write_text(
            json.dumps(audit, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\nTRANSFORMACION CLIENTES COMPLETADA")
        print(f"Clientes preparados: {count}")
        print(f"CSV: {output_file}")
        print(f"Auditoria: {audit_file}")

    finally:
        conn.close()

        if temp_file.exists():
            temp_file.unlink()

        print("Conexion PostgreSQL cerrada.")


if __name__ == "__main__":
    main()
