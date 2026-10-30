"""FleetLogix - Avance 1: tablas maestras (solo genera CSV, NO carga PostgreSQL).

Ejecutar desde la raíz FleetLogix: python Scripts/01_data_generation.py
"""
from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
SEED = 20261029
CITIES = ["Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena"]
# Distancias ilustrativas por carretera: no son mediciones cartográficas.
INTERCITY_KM = {
    frozenset(("Bogotá", "Medellín")): 420,
    frozenset(("Bogotá", "Cali")): 460,
    frozenset(("Bogotá", "Barranquilla")): 1000,
    frozenset(("Bogotá", "Cartagena")): 1060,
    frozenset(("Medellín", "Cali")): 420,
    frozenset(("Medellín", "Barranquilla")): 700,
    frozenset(("Medellín", "Cartagena")): 640,
    frozenset(("Cali", "Barranquilla")): 1150,
    frozenset(("Cali", "Cartagena")): 1090,
    frozenset(("Barranquilla", "Cartagena")): 125,
}


def make_logger() -> logging.Logger:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fleetlogix")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    for handler in (logging.FileHandler(LOG_DIR / "generacion_maestras.log", encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def generate_vehicles(rng: np.random.Generator) -> pd.DataFrame:
    # 200 vehículos: 20 grandes, 40 medianos, 80 vans, 60 motos.
    types = (["Camión Grande"] * 20 + ["Camión Mediano"] * 40
             + ["Van"] * 80 + ["Motocicleta"] * 60)
    rng.shuffle(types)
    spec = {
        "Camión Grande": ((7000, 14000), "Diesel"),
        "Camión Mediano": ((2500, 6500), "Diesel"),
        "Van": ((600, 1800), "Gasolina"),
        "Motocicleta": ((10, 40), "Gasolina"),
    }
    rows = []
    for i, kind in enumerate(types, start=1):
        (minimum, maximum), fuel = spec[kind]
        acquired = date(2019, 1, 1) + timedelta(days=int(rng.integers(0, 1700)))
        # Matrículas ficticias únicas (no se afirma validez registral colombiana).
        rows.append({
            "license_plate": f"FX{i:04d}",
            "vehicle_type": kind,
            "capacity_kg": round(float(rng.uniform(minimum, maximum)), 2),
            "fuel_type": fuel,
            "acquisition_date": acquired.isoformat(),
            "status": "active",
        })
    return pd.DataFrame(rows)


def generate_drivers(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    rows = []
    for i in range(1, 401):
        hired = date(2018, 1, 1) + timedelta(days=int(rng.integers(0, 2050)))
        expiry = date(2028, 1, 1) + timedelta(days=int(rng.integers(0, 1100)))
        rows.append({
            "employee_code": f"EMP{i:04d}",
            "first_name": fake.first_name()[:100],
            "last_name": fake.last_name()[:100],
            "license_number": f"LIC{i:08d}",
            "license_expiry": expiry.isoformat(),
            "phone": f"3{int(rng.integers(0, 10**9)):09d}",
            "hire_date": hired.isoformat(),
            "status": "active",
        })
    return pd.DataFrame(rows)


def generate_routes(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    # 30 rutas de última milla dentro de las ciudades: seis variantes por ciudad.
    for city_index, city in enumerate(CITIES, start=1):
        for variant in range(1, 7):
            distance = round(float(rng.uniform(5, 35)), 2)
            rows.append({
                "route_code": f"LOC-{city_index:02d}-{variant:02d}",
                "origin_city": city,
                "destination_city": city,
                "distance_km": distance,
                "estimated_duration_hours": round(distance / 23 + .20, 2),
                "toll_cost": 0.0,
            })
    # 20 conexiones dirigidas entre las cinco ciudades (5 * 4).
    for origin_index, origin in enumerate(CITIES, start=1):
        for destination_index, destination in enumerate(CITIES, start=1):
            if origin_index == destination_index:
                continue
            nominal = INTERCITY_KM[frozenset((origin, destination))]
            distance = round(nominal * float(rng.uniform(.97, 1.03)), 2)
            rows.append({
                "route_code": f"INT-{origin_index:02d}-{destination_index:02d}",
                "origin_city": origin,
                "destination_city": destination,
                "distance_km": distance,
                "estimated_duration_hours": round(distance / 55 + .50, 2),
                "toll_cost": round(distance * .20, 2),  # valor sintético, NO tarifa real
            })
    return pd.DataFrame(rows)


def validate(vehicles: pd.DataFrame, drivers: pd.DataFrame, routes: pd.DataFrame) -> None:
    assert (len(vehicles), len(drivers), len(routes)) == (200, 400, 50)
    assert vehicles.license_plate.is_unique
    assert drivers.employee_code.is_unique and drivers.license_number.is_unique
    assert routes.route_code.is_unique
    assert (vehicles.capacity_kg > 0).all()
    assert (routes.distance_km > 0).all() and (routes.estimated_duration_hours > 0).all()
    assert (routes.origin_city.isin(CITIES) & routes.destination_city.isin(CITIES)).all()
    assert (pd.to_datetime(drivers.license_expiry) > pd.Timestamp("2026-10-29")).all()
    assert (pd.to_datetime(drivers.hire_date) <= pd.Timestamp("2024-10-01")).all()
    assert (pd.to_datetime(vehicles.acquisition_date) <= pd.Timestamp("2024-10-01")).all()
    for name, table in (("vehicles", vehicles), ("drivers", drivers), ("routes", routes)):
        assert not table.isna().any().any(), f"{name}: valores nulos inesperados"


def main() -> None:
    random.seed(SEED)
    rng = np.random.default_rng(SEED)
    fake = Faker("es_CO")
    fake.seed_instance(SEED)
    logger = make_logger()
    vehicles = generate_vehicles(rng)
    drivers = generate_drivers(rng, fake)
    routes = generate_routes(rng)
    validate(vehicles, drivers, routes)
    for name, table in (("vehicles", vehicles), ("drivers", drivers), ("routes", routes)):
        output = DATA_DIR / f"{name}.csv"
        table.to_csv(output, index=False, encoding="utf-8-sig")
        logger.info("OK %s: %s filas -> %s", name, len(table), output)
    logger.info("TOTAL: 650 registros maestros validados; PostgreSQL no fue modificado")


if __name__ == "__main__":
    main()
