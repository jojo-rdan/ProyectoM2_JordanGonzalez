"""FleetLogix / Avance 3: extracción y transformación de FACT_DELIVERIES.

Uso:
    python Scripts/Avance_3/07_extract_transform_fact_deliveries.py

- Solo LEE de PostgreSQL; NO realiza cambios en Snowflake.
- Escribe CSV de staging de manera atómica después de validar la extracción.
- Reparte distancia y combustible del viaje por peso de paquete, conservando
  exactamente el total de cada viaje con seis decimales.
- ESTIMATED_REVENUE_COP se deriva con SYNTHETIC_REVENUE_V1 (simulación académica).
"""

import csv
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from getpass import getpass
from hashlib import sha256
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
OUTPUT_DIR = ROOT / "data" / "staging" / "avance_3" / "prepared"
OUTPUT_FILE = OUTPUT_DIR / "fact_deliveries.csv"
TEMP_FILE = OUTPUT_DIR / "fact_deliveries.csv.tmp"
AUDIT_FILE = OUTPUT_DIR / "fact_deliveries_audit.json"

EXPECTED_DELIVERIES = 400_000
EXPECTED_TRIPS = 100_000
EXPECTED_DISTANCE_KM = Decimal("4701486.980")
EXPECTED_FUEL_L = Decimal("633064.820")
BATCH_SIZE = 5_000
ALLOC_QUANT = Decimal("0.000001")
METRIC_QUANT = Decimal("0.001")
ALLOC_METHOD = "WEIGHT_PROPORTIONAL_V1"
REVENUE_POLICY = "SYNTHETIC_REVENUE_V1"
REVENUE_BASE_COP = Decimal("7000")
REVENUE_PER_KG_COP = Decimal("20")
REVENUE_PER_KM_COP = Decimal("300")
REVENUE_QUANT = Decimal("0.01")
EXPECTED_REVENUE_COP = Decimal("6270850032.24")
DATE_MIN = datetime(2024, 1, 1)
DATE_MAX_EXCLUSIVE = datetime(2031, 1, 1)

CSV_COLUMNS = [
    "DELIVERY_ID", "TRIP_ID", "TRACKING_NUMBER", "DATE_KEY",
    "DELIVERY_HOUR", "VEHICLE_ID", "DRIVER_ID", "ROUTE_ID",
    "CUSTOMER_BK", "DEPARTURE_DATETIME", "SCHEDULED_DATETIME",
    "DELIVERED_DATETIME", "DELIVERY_COUNT", "PACKAGE_WEIGHT_KG",
    "DELIVERY_DURATION_MINUTES", "SCHEDULE_VARIANCE_MINUTES",
    "IS_ON_TIME", "ALLOCATED_DISTANCE_KM", "ALLOCATED_FUEL_LITERS",
    "ALLOCATION_METHOD", "ESTIMATED_REVENUE_COP",
    "REVENUE_POLICY_VERSION", "SOURCE_ROW_HASH",
]

# Todos los conteos se hacen sobre la misma selección que leerá el cursor.
PREFLIGHT_SQL = """
SELECT
    COUNT(*) AS total_deliveries,
    COUNT(DISTINCT d.delivery_id) AS unique_deliveries,
    COUNT(DISTINCT d.trip_id) AS unique_trips
FROM public.deliveries AS d
JOIN public.trips AS t ON t.trip_id = d.trip_id
JOIN public.routes AS r ON r.route_id = t.route_id
WHERE d.delivery_status = 'delivered'
  AND t.status = 'completed';
"""

EXTRACTION_SQL = """
SELECT
    d.delivery_id,
    d.trip_id,
    d.tracking_number,
    t.vehicle_id,
    t.driver_id,
    t.route_id,
    LOWER(TRIM(d.customer_name)) AS customer_name_normalized,
    LOWER(TRIM(d.delivery_address)) AS delivery_address_normalized,
    t.departure_datetime,
    d.scheduled_datetime,
    d.delivered_datetime,
    d.package_weight_kg,
    r.distance_km,
    t.fuel_consumed_liters
FROM public.deliveries AS d
JOIN public.trips AS t ON t.trip_id = d.trip_id
JOIN public.routes AS r ON r.route_id = t.route_id
WHERE d.delivery_status = 'delivered'
  AND t.status = 'completed'
ORDER BY d.trip_id, d.delivery_id;
"""


def number(value, field, allow_zero=False):
    """Convierte números fuente a Decimal sin pasar por float de Python."""
    if value is None:
        raise ValueError(f"{field} no puede ser NULL")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field}: número inválido {value!r}") from exc
    if not result.is_finite() or (result < 0 if allow_zero else result <= 0):
        raise ValueError(f"{field}: fuera de rango {value!r}")
    return result


def dt_string(value, field):
    if not isinstance(value, datetime):
        raise ValueError(f"{field}: fecha/hora ausente o inválida")
    if value.tzinfo is not None:
        raise ValueError(f"{field}: se esperaba TIMESTAMP WITHOUT TIME ZONE")
    return value.isoformat(sep=" ", timespec="microseconds")


def customer_bk(name, address):
    if not name or not address:
        raise ValueError("Cliente con nombre o dirección normalizados vacíos")
    # ¡Debe coincidir EXACTAMENTE con 05_extract_transform_customers.py!
    payload = json.dumps([name, address], ensure_ascii=False, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def estimate_revenue(weight_kg: Decimal, allocated_distance_km: Decimal) -> Decimal:
    """Calcula ingresos SINTÉTICOS sobre métricas tal como se guardan en CSV/DWH.

    Peso: NUMBER(18,3); distancia: NUMBER(20,6); redondeo HALF_UP
    (equivalente al ROUND de valores positivos de Snowflake).
    """
    saved_weight = weight_kg.quantize(METRIC_QUANT, rounding=ROUND_HALF_UP)
    saved_distance = allocated_distance_km.quantize(ALLOC_QUANT, rounding=ROUND_HALF_UP)
    revenue = (
        REVENUE_BASE_COP
        + saved_weight * REVENUE_PER_KG_COP
        + saved_distance * REVENUE_PER_KM_COP
    )
    return revenue.quantize(REVENUE_QUANT, rounding=ROUND_HALF_UP)


def make_row_hash(record):
    payload = json.dumps(
        {key: record[key] for key in CSV_COLUMNS if key != "SOURCE_ROW_HASH"},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def allocate_amount(total, weights):
    """Retorna partes de 6 decimales que suman EXACTAMENTE el total redondeado."""
    if not weights or any(w <= 0 for w in weights):
        raise ValueError("Pesos no válidos para la asignación")
    target = total.quantize(ALLOC_QUANT, rounding=ROUND_HALF_UP)
    weight_sum = sum(weights, Decimal(0))
    with localcontext() as ctx:
        ctx.prec = 38
        parts = [
            (target * w / weight_sum).quantize(ALLOC_QUANT, rounding=ROUND_HALF_UP)
            for w in weights[:-1]
        ]
    parts.append(target - sum(parts, Decimal(0)))
    if any(part < 0 for part in parts):
        raise ValueError("Asignación produjo una parte negativa")
    if sum(parts, Decimal(0)) != target:
        raise AssertionError("Error en la conservación del total por viaje")
    return parts


def transform_trip(raw_rows):
    """Transforma exclusivamente las entregas de UN viaje."""
    if not raw_rows:
        raise ValueError("Viaje sin entregas")
    trip_id = raw_rows[0][1]
    total_distance = number(raw_rows[0][12], "distance_km")
    total_fuel = number(raw_rows[0][13], "fuel_consumed_liters", allow_zero=True)
    weights = [number(raw[11], "package_weight_kg") for raw in raw_rows]
    distance_parts = allocate_amount(total_distance, weights)
    fuel_parts = allocate_amount(total_fuel, weights)
    records = []

    for raw, weight, assigned_distance, assigned_fuel in zip(
        raw_rows, weights, distance_parts, fuel_parts, strict=True
    ):
        (
            delivery_id, row_trip_id, tracking, vehicle_id, driver_id,
            route_id, norm_name, norm_address, departed, scheduled,
            delivered, _weight, row_distance, row_fuel,
        ) = raw
        if row_trip_id != trip_id:
            raise ValueError("Se mezclaron entregas de distintos viajes")
        if (number(row_distance, "distance_km") != total_distance
                or number(row_fuel, "fuel_consumed_liters", allow_zero=True) != total_fuel):
            raise ValueError(f"Viaje {trip_id}: totales inconsistentes en filas")
        if any(v is None for v in (delivery_id, vehicle_id, driver_id, route_id)):
            raise ValueError("Identificador operacional nulo")
        if not all(isinstance(v, datetime) for v in (departed, scheduled, delivered)):
            raise ValueError(f"Entrega {delivery_id}: fecha/hora obligatoria nula")
        if not DATE_MIN <= delivered < DATE_MAX_EXCLUSIVE:
            raise ValueError(f"Entrega {delivery_id}: fuera del rango DIM_DATE")
        if delivered < departed:
            raise ValueError(f"Entrega {delivery_id}: entregada antes de la salida")

        duration_minutes = (
            Decimal(str((delivered - departed).total_seconds())) / Decimal(60)
        ).quantize(METRIC_QUANT, rounding=ROUND_HALF_UP)
        schedule_variance = (
            Decimal(str((delivered - scheduled).total_seconds())) / Decimal(60)
        ).quantize(METRIC_QUANT, rounding=ROUND_HALF_UP)

        estimated_revenue = estimate_revenue(weight, assigned_distance)
        record = {
            "DELIVERY_ID": str(delivery_id),
            "TRIP_ID": str(trip_id),
            "TRACKING_NUMBER": str(tracking) if tracking is not None else "",
            "DATE_KEY": delivered.strftime("%Y%m%d"),
            # Hora de 0 a 23. La clave DIM_TIME se resolverá en Snowflake.
            "DELIVERY_HOUR": str(delivered.hour),
            "VEHICLE_ID": str(vehicle_id),
            "DRIVER_ID": str(driver_id),
            "ROUTE_ID": str(route_id),
            "CUSTOMER_BK": customer_bk(norm_name, norm_address),
            "DEPARTURE_DATETIME": dt_string(departed, "departure_datetime"),
            "SCHEDULED_DATETIME": dt_string(scheduled, "scheduled_datetime"),
            "DELIVERED_DATETIME": dt_string(delivered, "delivered_datetime"),
            "DELIVERY_COUNT": "1",
            "PACKAGE_WEIGHT_KG": format(weight.quantize(METRIC_QUANT, rounding=ROUND_HALF_UP), ".3f"),
            "DELIVERY_DURATION_MINUTES": format(duration_minutes, ".3f"),
            "SCHEDULE_VARIANCE_MINUTES": format(schedule_variance, ".3f"),
            "IS_ON_TIME": "TRUE" if delivered <= scheduled else "FALSE",
            "ALLOCATED_DISTANCE_KM": format(assigned_distance, ".6f"),
            "ALLOCATED_FUEL_LITERS": format(assigned_fuel, ".6f"),
            "ALLOCATION_METHOD": ALLOC_METHOD,
            "ESTIMATED_REVENUE_COP": format(estimated_revenue, ".2f"),
            "REVENUE_POLICY_VERSION": REVENUE_POLICY,
        }
        record["SOURCE_ROW_HASH"] = make_row_hash(record)
        records.append(record)
    return records, sum(distance_parts, Decimal(0)), sum(fuel_parts, Decimal(0))


def main():
    print("FleetLogix: extrayendo FACT_DELIVERIES desde PostgreSQL...")
    print("Modo: solo lectura de PostgreSQL; sin conexión a Snowflake.")
    password = os.getenv("PGPASSWORD") or getpass("Contraseña PostgreSQL: ")
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "fleetlogix_db"),
        user=os.getenv("PGUSER", "postgres"),
        password=password,
        connect_timeout=20,
    )

    success = False
    try:
        # Una sola instantánea consistente para conteo y extracción.
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
        with conn.cursor() as cursor:
            cursor.execute(PREFLIGHT_SQL)
            total, unique_deliveries, unique_trips = cursor.fetchone()
        print(f"Prevalidación: {total:,} entregas, {unique_trips:,} viajes")
        if (total, unique_deliveries, unique_trips) != (
            EXPECTED_DELIVERIES, EXPECTED_DELIVERIES, EXPECTED_TRIPS
        ):
            raise ValueError("Los conteos del origen no coinciden con la auditoría previa")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        processed_deliveries = 0
        processed_trips = 0
        distance_sum = Decimal(0)
        fuel_sum = Decimal(0)
        revenue_sum = Decimal(0)
        current_trip_id = None
        group = []

        with TEMP_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()

            def flush_trip():
                nonlocal processed_deliveries, processed_trips, distance_sum, fuel_sum, revenue_sum
                if not group:
                    return
                records, trip_distance, trip_fuel = transform_trip(group)
                writer.writerows(records)
                processed_deliveries += len(records)
                processed_trips += 1
                distance_sum += trip_distance
                fuel_sum += trip_fuel
                revenue_sum += sum(
                    (Decimal(row["ESTIMATED_REVENUE_COP"]) for row in records),
                    Decimal(0),
                )
                if processed_trips % 10_000 == 0:
                    print(f"  Viajes procesados: {processed_trips:,} | Entregas: {processed_deliveries:,}")

            with conn.cursor(name="fleetlogix_fact_deliveries_stream") as cursor:
                cursor.itersize = BATCH_SIZE
                cursor.execute(EXTRACTION_SQL)
                while True:
                    batch = cursor.fetchmany(BATCH_SIZE)
                    if not batch:
                        break
                    for raw in batch:
                        row_trip_id = raw[1]
                        if current_trip_id is not None and row_trip_id != current_trip_id:
                            if row_trip_id < current_trip_id:
                                raise ValueError("Los viajes no llegaron ordenados")
                            flush_trip()
                            group.clear()
                        current_trip_id = row_trip_id
                        group.append(raw)
                flush_trip()

        if processed_deliveries != EXPECTED_DELIVERIES or processed_trips != EXPECTED_TRIPS:
            raise ValueError("No cuadran entregas o viajes transformados")
        if distance_sum != EXPECTED_DISTANCE_KM or fuel_sum != EXPECTED_FUEL_L:
            raise ValueError(
                "No concilian los totales de distancia/combustible: "
                f"{distance_sum} km y {fuel_sum} L"
            )

        if revenue_sum != EXPECTED_REVENUE_COP:
            raise ValueError(
                "Ingresos estimados no concilian con la simulación previa: "
                f"{revenue_sum} COP vs {EXPECTED_REVENUE_COP} COP"
            )

        # Publicamos únicamente tras completar todas las validaciones.
        os.replace(TEMP_FILE, OUTPUT_FILE)
        audit = {
            "processed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "PostgreSQL: deliveries + trips + routes",
            "grain": "one row per delivered delivery_id",
            "source_delivery_count": total,
            "source_unique_delivery_ids": unique_deliveries,
            "prepared_delivery_count": processed_deliveries,
            "source_trip_count": unique_trips,
            "processed_trip_count": processed_trips,
            "allocated_distance_km": str(distance_sum),
            "allocated_fuel_liters": str(fuel_sum),
            "allocation_method": ALLOC_METHOD,
            "customer_key_method": "SHA256(JSON([lower(trim(name)),lower(trim(address))]))",
            "revenue_policy": REVENUE_POLICY,
            "revenue_is_synthetic": True,
            "revenue_base_cop": str(REVENUE_BASE_COP),
            "revenue_per_kg_cop": str(REVENUE_PER_KG_COP),
            "revenue_per_km_cop": str(REVENUE_PER_KM_COP),
            "revenue_total_estimated_cop": str(revenue_sum),
            "revenue_rounding": "HALF_UP to 2 decimals per delivery",
            "source_row_hash": "SHA256 of deterministic prepared record",
            "status": "VALIDATED",
        }
        AUDIT_FILE.write_text(
            json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        success = True
        print("\nTRANSFORMACION FACT_DELIVERIES COMPLETADA")
        print(f"Entregas: {processed_deliveries:,} | Viajes: {processed_trips:,}")
        print(f"Distancia asignada: {distance_sum:,.6f} km")
        print(f"Combustible asignado: {fuel_sum:,.6f} L")
        print(f"Ingresos SINTÉTICOS estimados: {revenue_sum:,.2f} COP ({REVENUE_POLICY})")
        print(f"Archivo: {OUTPUT_FILE}")
        print(f"Auditoría: {AUDIT_FILE}")
        print("Snowflake no fue modificado.")
    finally:
        conn.close()
        if not success and TEMP_FILE.exists():
            TEMP_FILE.unlink()
        print("Conexión PostgreSQL cerrada.")


if __name__ == "__main__":
    main()
