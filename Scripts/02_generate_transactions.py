"""FleetLogix Avance #1 - datos transaccionales (solo CSV, sin INSERT).

Requiere que 01_data_generation.py haya generado vehicles.csv, drivers.csv y routes.csv.
IDs referenciales 1..N: para carga, usar 03_load_all.py que asigna los mismos IDs.
Rango de operación: 2024-10-29 a 2026-10-28 (dos años retrospectivos).
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LOGS = ROOT / "logs"
SEED = 20261029
START = datetime(2024, 10, 29)
END = datetime(2026, 10, 29)  # exclusivo
N_TRIPS = 100_000
N_DELIVERIES = 400_000
N_MAINTENANCE = 5_000
MAINTENANCE_TYPES = [
    "Cambio de aceite", "Revisión de frenos", "Cambio de llantas",
    "Mantenimiento general", "Revisión de motor", "Alineación y balanceo",
]


def logger_factory():
    LOGS.mkdir(exist_ok=True, parents=True)
    logger = logging.getLogger("fleetlogix.transacciones")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    for handler in (logging.FileHandler(LOGS / "generacion_transacciones.log", encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def gethourly_distribution(weekday: int) -> np.ndarray:
    """Probabilidades horarias para salir: 0=lunes..6=domingo.

    Se incrementa la probabilidad de operar entre las 7 y las 18 h;
    en fines de semana disminuye la actividad. Se normaliza a suma 1.
    Es una hipótesis sintética y no una distribución medida de FleetLogix.
    """
    weights = np.full(24, 0.05, dtype=float)
    weights[6:10] = [2.0, 5.0, 7.0, 5.5]
    weights[10:13] = [4.0, 4.2, 3.5]
    weights[13:17] = [4.0, 5.0, 5.0, 4.5]
    weights[17:20] = [4.0, 2.8, 1.5]
    weights[20:22] = [0.7, 0.3]
    if weekday >= 5:
        weights[6:9] *= 0.4
        weights[9:18] *= 0.75
    return weights / weights.sum()


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def decimal(v: float) -> str:
    return f"{v:.2f}"


def write_csv(path: Path, fieldnames: list[str], rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_trips(vehicles: pd.DataFrame, routes: pd.DataFrame, rng: np.random.Generator):
    """Genera 500 viajes/vehículo con disponibilidad de vehículo/conductor.

    Dos conductores exclusivos por vehículo evitan solapamientos entre flotas.
    Cada vehículo y sus conductores tienen una ubicación actual; el origen de
    la ruta siempre coincide con ella y se actualiza al destino. Se reserva
    tiempo tras llegada y se verifica el límite de los dos años.
    """
    assert len(vehicles) == 200 and len(routes) == 50
    trip_rows = []
    hour_probs = [gethourly_distribution(d) for d in range(7)]
    route_records = routes.to_dict("records")
    trip_lookup = {}
    maintenance_rows = []
    trip_id = 0
    maintenance_id = 0
    route_maps = {city: [i for i,r in enumerate(route_records) if r["origin_city"] == city]
                  for city in routes.origin_city.unique()}
    local_maps = {city: [i for i in ids if route_records[i]["destination_city"] == city]
                  for city, ids in route_maps.items()}
    intercity_maps = {city: [i for i in ids if route_records[i]["destination_city"] != city]
                  for city, ids in route_maps.items()}
    city_names = sorted(route_maps)
    maintenance_cost = {
        "Cambio de aceite": (120_000, 420_000),
        "Revisión de frenos": (180_000, 650_000),
        "Cambio de llantas": (380_000, 1_600_000),
        "Mantenimiento general": (250_000, 900_000),
        "Revisión de motor": (300_000, 1_800_000),
        "Alineación y balanceo": (100_000, 350_000),
    }
    for vi, vehicle in vehicles.reset_index(drop=True).iterrows():
        vehicle_id = vi + 1
        driver_a, driver_b = 2 * vi + 1, 2 * vi + 2
        city = city_names[vi % len(city_names)]
        prev_end = START
        # 720 de los 730 días dejan margen para las operaciones de larga duración.
        for j in range(500):
            planned_day = min(719, int((j + float(rng.uniform(0, .9))) * 720 / 500))
            day = (START + timedelta(days=planned_day)).date()
            hour = int(rng.choice(24, p=hour_probs[day.weekday()]))
            minute = int(rng.integers(0, 60))
            planned = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
            departure = max(planned, prev_end + timedelta(hours=2))
            local = local_maps[city]
            intercity = intercity_maps[city]
            pool = intercity if intercity and rng.random() < .035 else local
            chosen = pool[int(rng.integers(0, len(pool)))]
            route = route_records[chosen]
            estimate = float(route["estimated_duration_hours"])
            duration = max(.35, estimate * float(rng.uniform(.9, 1.15)))
            arrival = departure + timedelta(hours=duration)
            if arrival >= END:
                # No salir del histórico: preferir ruta local y duración menor.
                chosen = local[int(rng.integers(0,len(local)))]
                route = route_records[chosen]
                estimate = float(route["estimated_duration_hours"])
                duration = max(.35, estimate * .95)
                arrival = departure + timedelta(hours=duration)
            if arrival >= END:
                raise ValueError(f"No cabe viaje de vehículo {vehicle_id} en los dos años")
            kind = vehicle.vehicle_type
            # En el esquema solo se almacena el consumo de combustible, no su tarifa.
            liters_per_100km = {"Camión Grande": 32, "Camión Mediano": 22, "Van": 11, "Motocicleta": 3.5}[kind]
            liters = float(route["distance_km"]) * liters_per_100km / 100 * float(rng.uniform(.87, 1.18))
            trip_id += 1
            driver_id = driver_a if j % 2 == 0 else driver_b
            info = {
                "trip_id": trip_id, "vehicle_id": vehicle_id, "driver_id": driver_id,
                "route_id": chosen + 1, "departure_datetime": fmt(departure),
                "arrival_datetime": fmt(arrival), "fuel_consumed_liters": decimal(liters),
                "total_weight_kg": None, "status": "completed",
            }
            trip_rows.append(info)
            trip_lookup[trip_id] = (departure, arrival, float(vehicle.capacity_kg), route["destination_city"])
            city = str(route["destination_city"])
            prev_end = arrival
            if (j + 1) % 20 == 0:
                maintenance_id += 1
                typ = MAINTENANCE_TYPES[(maintenance_id - 1) % len(MAINTENANCE_TYPES)]
                cost_min, cost_max = maintenance_cost[typ]
                mdate = arrival.date()
                maintenance_rows.append({
                    "maintenance_id": maintenance_id,
                    "vehicle_id": vehicle_id,
                    "maintenance_date": mdate.isoformat(),
                    "maintenance_type": typ,
                    "description": f"Mantenimiento preventivo tras {j + 1} viajes del vehículo FX{vehicle_id:04d}",
                    "cost": decimal(float(rng.uniform(cost_min, cost_max))),
                    "next_maintenance_date": (mdate + timedelta(days=35)).isoformat(),
                    "performed_by": f"Taller Sintético {1 + (vi % 12):02d}",
                })
    assert trip_id == N_TRIPS and maintenance_id == N_MAINTENANCE
    return trip_rows, trip_lookup, maintenance_rows


def delivery_count_distribution(rng: np.random.Generator) -> np.ndarray:
    """Exactamente 400k: 5% con 2, 20% con 3, 50% con 4, 20% con 5, 5% con 6."""
    counts = np.array([2]*5000 + [3]*20000 + [4]*50000 + [5]*20000 + [6]*5000, dtype=np.int8)
    rng.shuffle(counts)
    assert len(counts) == N_TRIPS and counts.sum() == N_DELIVERIES
    return counts


def generate_deliveries(trip_rows, trip_lookup, rng: np.random.Generator, fake: Faker, logger):
    """Escribe 400k entregas en streaming y asigna peso exacto a cada viaje."""
    output = DATA / "deliveries.csv"
    fields = ["delivery_id", "trip_id", "tracking_number", "customer_name", "delivery_address",
              "package_weight_kg", "scheduled_datetime", "delivered_datetime",
              "delivery_status", "recipient_signature"]
    counts = delivery_count_distribution(rng)
    # Faker se usa en un banco de identidades/ubicaciones que se reutiliza de forma sintética.
    names = [fake.name()[:200] for _ in range(1500)]
    addresses = {city: [f"{fake.street_address()}, {city}" for _ in range(1000)]
                 for city in sorted({v[3] for v in trip_lookup.values()})}
    delivery_id = 0
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for idx, trip in enumerate(trip_rows):
            tid = int(trip["trip_id"])
            departure, arrival, capacity, city = trip_lookup[tid]
            n = int(counts[idx])
            # Se utiliza 15-70% de capacidad: la suma no puede superar capacidad.
            total = round(capacity * float(rng.uniform(.15, .70)), 2)
            # Último peso como residuo evita diferencias por redondeos monetarios.
            proportions = rng.dirichlet(np.full(n, 2.5))
            # En motos de poca capacidad el paquete mínimo puede ser muy pequeño, pero positivo.
            weights = [round(total * float(x), 2) for x in proportions[:-1]]
            weights.append(round(total - sum(weights), 2))
            if min(weights) <= 0:
                # Casos raros por redondeo: dividir en centavos, sin exceder la capacidad.
                cents = max(n, int(round(total * 100)))
                base = cents // n
                weights = [base / 100] * n
                weights[-1] = round((cents - base*(n-1))/100, 2)
            trip["total_weight_kg"] = decimal(sum(weights))
            span = (arrival - departure).total_seconds()
            for k, weight in enumerate(weights):
                delivery_id += 1
                # Entregas en orden, todas en el intervalo del viaje.
                fraction = (k+1)/(n+1)
                delivery_time = departure + timedelta(seconds=span*fraction)
                scheduled = delivery_time - timedelta(minutes=int(rng.integers(0, 15)))
                scheduled = max(scheduled, departure)
                writer.writerow({
                    "delivery_id": delivery_id,
                    "trip_id": tid,
                    "tracking_number": f"FLX{delivery_id:09d}",
                    "customer_name": names[int(rng.integers(0, len(names)))],
                    "delivery_address": addresses[city][int(rng.integers(0, 1000))],
                    "package_weight_kg": decimal(weight),
                    "scheduled_datetime": fmt(scheduled),
                    "delivered_datetime": fmt(delivery_time),
                    "delivery_status": "delivered",
                    "recipient_signature": "true",
                })
            if (idx+1) % 20000 == 0:
                logger.info("Entregas preparadas para %s viajes: %s filas", idx+1, delivery_id)
    assert delivery_id == N_DELIVERIES


def validate(trips, maintenance, trip_lookup, vehicles, routes):
    if len(trips) != N_TRIPS or len(maintenance) != N_MAINTENANCE:
        raise ValueError("Recuento incorrecto")
    by_vehicle = {}
    by_driver = {}
    for t in trips:
        vid, did, rid = (int(t[key]) for key in ("vehicle_id", "driver_id", "route_id"))
        if not (1 <= vid <= 200 and 1 <= did <= 400 and 1 <= rid <= 50):
            raise ValueError("FK inválida")
        departure, arrival, capacity, _ = trip_lookup[t["trip_id"]]
        if not (START <= departure < arrival < END):
            raise ValueError("Fechas de viaje incoherentes")
        weight = float(t["total_weight_kg"])
        if not (0 < weight <= capacity):
            raise ValueError("Capacidad excedida")
        for key, ident, registry in (("vehículo", vid, by_vehicle), ("conductor", did, by_driver)):
            previous = registry.get(ident)
            if previous is not None and departure < previous:
                raise ValueError(f"Viajes simultáneos de {key}: {ident}")
            registry[ident] = arrival
    for m in maintenance:
        vid = int(m["vehicle_id"])
        if vid < 1 or vid > 200:
            raise ValueError("Mantenimiento con vehículo inválido")
        if not (date.fromisoformat(str(vehicles.iloc[vid - 1].acquisition_date))
                <= date.fromisoformat(m["maintenance_date"])
                < date.fromisoformat(m["next_maintenance_date"])):
            raise ValueError("Fecha de mantenimiento inválida")
    frequency = Counter(int(x["vehicle_id"]) for x in maintenance)
    assert len(frequency) == 200 and set(frequency.values()) == {25}
    assert all(float(t["fuel_consumed_liters"]) > 0 for t in trips)


def main():
    logger = logger_factory()
    for name in ("vehicles", "drivers", "routes"):
        if not (DATA / f"{name}.csv").exists():
            raise FileNotFoundError(f"Falta data/{name}.csv; ejecuta primero 01_data_generation.py")
    vehicles = pd.read_csv(DATA / "vehicles.csv", encoding="utf-8-sig")
    drivers = pd.read_csv(DATA / "drivers.csv", encoding="utf-8-sig")
    routes = pd.read_csv(DATA / "routes.csv", encoding="utf-8-sig")
    if (len(vehicles), len(drivers), len(routes)) != (200, 400, 50):
        raise ValueError("Los CSV maestros no tienen las cantidades esperadas")
    rng = np.random.default_rng(SEED+1)
    fake = Faker("es_CO")
    fake.seed_instance(SEED+1)
    trips, lookup, maintenance = generate_trips(vehicles, routes, rng)
    logger.info("Viajes: %s; mantenimientos: %s", len(trips), len(maintenance))
    generate_deliveries(trips, lookup, rng, fake, logger)
    validate(trips, maintenance, lookup, vehicles, routes)
    write_csv(DATA / "trips.csv", list(trips[0]), trips)
    write_csv(DATA / "maintenance.csv", list(maintenance[0]), maintenance)
    logger.info("OK: 100000 viajes, 400000 entregas, 5000 mantenimientos; PostgreSQL sin cambios")
    logger.info("IDs de viajes y FK asumen la carga del conjunto completo mediante 03_load_all.py")


if __name__ == "__main__":
    main()
