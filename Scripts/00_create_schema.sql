-- FleetLogix - esquema relacional base reproducible.
-- Ejecutar solamente sobre una base nueva y vacia.
-- Este script reproduce el esquema original validado en PostgreSQL.
-- Los indices experimentales del Avance 2 se mantienen separados en
-- Scripts/Avance_2/06_indices_avance2.sql.

BEGIN;

CREATE TABLE public.vehicles (
    vehicle_id SERIAL CONSTRAINT vehicles_pkey PRIMARY KEY,
    license_plate VARCHAR(20) NOT NULL
        CONSTRAINT vehicles_license_plate_key UNIQUE,
    vehicle_type VARCHAR(50) NOT NULL,
    capacity_kg NUMERIC(10, 2),
    fuel_type VARCHAR(20),
    acquisition_date DATE,
    status VARCHAR(20) DEFAULT 'active'
);

CREATE TABLE public.drivers (
    driver_id SERIAL CONSTRAINT drivers_pkey PRIMARY KEY,
    employee_code VARCHAR(20) NOT NULL
        CONSTRAINT drivers_employee_code_key UNIQUE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    license_number VARCHAR(50) NOT NULL
        CONSTRAINT drivers_license_number_key UNIQUE,
    license_expiry DATE,
    phone VARCHAR(20),
    hire_date DATE,
    status VARCHAR(20) DEFAULT 'active'
);

CREATE TABLE public.routes (
    route_id SERIAL CONSTRAINT routes_pkey PRIMARY KEY,
    route_code VARCHAR(20) NOT NULL
        CONSTRAINT routes_route_code_key UNIQUE,
    origin_city VARCHAR(100) NOT NULL,
    destination_city VARCHAR(100) NOT NULL,
    distance_km NUMERIC(10, 2),
    estimated_duration_hours NUMERIC(5, 2),
    toll_cost NUMERIC(10, 2) DEFAULT 0
);

CREATE TABLE public.trips (
    trip_id SERIAL CONSTRAINT trips_pkey PRIMARY KEY,
    vehicle_id INTEGER
        CONSTRAINT trips_vehicle_id_fkey REFERENCES public.vehicles (vehicle_id),
    driver_id INTEGER
        CONSTRAINT trips_driver_id_fkey REFERENCES public.drivers (driver_id),
    route_id INTEGER
        CONSTRAINT trips_route_id_fkey REFERENCES public.routes (route_id),
    departure_datetime TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    arrival_datetime TIMESTAMP WITHOUT TIME ZONE,
    fuel_consumed_liters NUMERIC(10, 2),
    total_weight_kg NUMERIC(10, 2),
    status VARCHAR(20) DEFAULT 'in_progress'
);

CREATE TABLE public.deliveries (
    delivery_id SERIAL CONSTRAINT deliveries_pkey PRIMARY KEY,
    trip_id INTEGER
        CONSTRAINT deliveries_trip_id_fkey REFERENCES public.trips (trip_id),
    tracking_number VARCHAR(50) NOT NULL
        CONSTRAINT deliveries_tracking_number_key UNIQUE,
    customer_name VARCHAR(200) NOT NULL,
    delivery_address TEXT NOT NULL,
    package_weight_kg NUMERIC(10, 2),
    scheduled_datetime TIMESTAMP WITHOUT TIME ZONE,
    delivered_datetime TIMESTAMP WITHOUT TIME ZONE,
    delivery_status VARCHAR(20) DEFAULT 'pending',
    recipient_signature BOOLEAN DEFAULT FALSE
);

CREATE TABLE public.maintenance (
    maintenance_id SERIAL CONSTRAINT maintenance_pkey PRIMARY KEY,
    vehicle_id INTEGER
        CONSTRAINT maintenance_vehicle_id_fkey REFERENCES public.vehicles (vehicle_id),
    maintenance_date DATE NOT NULL,
    maintenance_type VARCHAR(50) NOT NULL,
    description TEXT,
    cost NUMERIC(10, 2),
    next_maintenance_date DATE,
    performed_by VARCHAR(200)
);

-- Indices secundarios presentes en el esquema base original.
CREATE INDEX idx_trips_departure
    ON public.trips (departure_datetime);

CREATE INDEX idx_deliveries_status
    ON public.deliveries (delivery_status);

CREATE INDEX idx_vehicles_status
    ON public.vehicles (status);

COMMIT;
