from pathlib import Path
from hashlib import sha256
from decimal import Decimal, InvalidOperation
import json

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "staging" / "avance_3"
DEST = SOURCE / "prepared"

EXPECTED = {
    "vehicles": 200,
    "drivers": 400,
    "routes": 50,
}

PRIMARY_KEYS = {
    "vehicles": "vehicle_id",
    "drivers": "driver_id",
    "routes": "route_id",
}


def read_source(name):
    path = SOURCE / f"{name}.csv"

    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")

    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8",
    )

    # Eliminar espacios externos sin alterar los valores internos.
    for column in df.columns:
        df[column] = df[column].str.strip()

    pk = PRIMARY_KEYS[name]

    if len(df) != EXPECTED[name]:
        raise ValueError(
            f"{name}: cantidad inesperada: {len(df)}"
        )

    if df[pk].eq("").any() or df[pk].duplicated().any():
        raise ValueError(
            f"{name}: IDs nulos o duplicados"
        )

    return df


def require_columns(df, name, columns):
    missing = set(columns) - set(df.columns)

    if missing:
        raise ValueError(
            f"{name}: columnas faltantes: {sorted(missing)}"
        )


def require_values(df, columns):
    for column in columns:
        if df[column].eq("").any():
            raise ValueError(
                f"Hay valores obligatorios vacíos en {column}"
            )


def check_numeric(df, columns, strictly_positive=False):
    for column in columns:
        for value in df[column]:
            if value == "":
                continue

            try:
                number = Decimal(value)
            except InvalidOperation:
                raise ValueError(
                    f"Valor no numérico en {column}: {value}"
                )

            valid = (
                number.is_finite()
                and (
                    number > 0
                    if strictly_positive
                    else number >= 0
                )
            )

            if not valid:
                raise ValueError(
                    f"Valor inválido en {column}: {value}"
                )


def attribute_hash(row, columns):
    values = {column: row[column] for column in columns}

    payload = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return sha256(payload.encode("utf-8")).hexdigest()


def main():
    print("Iniciando transformaciones FleetLogix...")

    vehicles = read_source("vehicles")
    drivers = read_source("drivers")
    routes = read_source("routes")

    # DIM_VEHICLE
    vehicles = vehicles.rename(
        columns={"status": "vehicle_status"}
    )
    vehicle_cols = [
        "vehicle_id", "license_plate", "vehicle_type",
        "capacity_kg", "fuel_type", "acquisition_date",
        "vehicle_status",
    ]
    require_columns(vehicles, "vehicles", vehicle_cols)
    vehicles = vehicles[vehicle_cols]
    require_values(
        vehicles,
        ["vehicle_id", "license_plate", "vehicle_type"],
    )
    check_numeric(vehicles, ["capacity_kg"], True)

    # DIM_DRIVER: atributos para SCD tipo 2.
    drivers = drivers.rename(
        columns={"status": "driver_status"}
    )
    driver_cols = [
        "driver_id", "employee_code", "first_name",
        "last_name", "license_expiry", "hire_date",
        "driver_status",
    ]
    require_columns(drivers, "drivers", driver_cols)
    drivers = drivers[driver_cols].copy()
    require_values(
        drivers,
        ["driver_id", "employee_code", "first_name", "last_name"],
    )

    # No existe una zona maestra en PostgreSQL.
    drivers["assigned_zone"] = ""

    tracked_attributes = [
        "employee_code", "first_name", "last_name",
        "license_expiry", "hire_date", "driver_status",
        "assigned_zone",
    ]

    drivers["attribute_hash"] = drivers.apply(
        lambda row: attribute_hash(row, tracked_attributes),
        axis=1,
    )

    # DIM_ROUTE
    route_cols = [
        "route_id", "route_code", "origin_city",
        "destination_city", "distance_km",
        "estimated_duration_hours", "toll_cost",
    ]
    require_columns(routes, "routes", route_cols)
    routes = routes[route_cols]
    require_values(
        routes,
        ["route_id", "route_code", "origin_city",
         "destination_city"],
    )
    check_numeric(routes, ["distance_km"], True)
    check_numeric(routes, ["estimated_duration_hours"], True)
    check_numeric(routes, ["toll_cost"])

    outputs = {
        "dim_vehicle": vehicles,
        "dim_driver": drivers,
        "dim_route": routes,
    }

    # Solo guardar después de superar las validaciones.
    DEST.mkdir(parents=True, exist_ok=True)

    for name, df in outputs.items():
        df.columns = df.columns.str.upper()
        path = DEST / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8")

        print(f"{name}: {len(df)} registros preparados")

    print("\nTRANSFORMACION COMPLETADA")
    print(f"Total: {sum(len(df) for df in outputs.values())}")
    print(f"Destino: {DEST}")


if __name__ == "__main__":
    main()
