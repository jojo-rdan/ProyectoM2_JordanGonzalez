-- FleetLogix: auditoría NO destructiva del Avance #1. Ejecutar en fleetlogix_db.
SELECT current_database() AS base_conectada;

-- Conteos reales de las seis tablas
SELECT 'vehicles' AS tabla, count(*) AS registros FROM vehicles UNION ALL
SELECT 'drivers', count(*) FROM drivers UNION ALL
SELECT 'routes', count(*) FROM routes UNION ALL
SELECT 'trips', count(*) FROM trips UNION ALL
SELECT 'deliveries', count(*) FROM deliveries UNION ALL
SELECT 'maintenance', count(*) FROM maintenance;

-- Relaciones faltantes o nulas
SELECT count(*) FILTER (WHERE v.vehicle_id IS NULL) AS trips_sin_vehiculo,
       count(*) FILTER (WHERE d.driver_id IS NULL) AS trips_sin_conductor,
       count(*) FILTER (WHERE r.route_id IS NULL) AS trips_sin_ruta
FROM trips t LEFT JOIN vehicles v ON v.vehicle_id=t.vehicle_id
LEFT JOIN drivers d ON d.driver_id=t.driver_id LEFT JOIN routes r ON r.route_id=t.route_id;
SELECT (SELECT count(*) FROM deliveries d LEFT JOIN trips t ON t.trip_id=d.trip_id WHERE t.trip_id IS NULL) AS entregas_huerfanas,
       (SELECT count(*) FROM maintenance m LEFT JOIN vehicles v ON v.vehicle_id=m.vehicle_id WHERE v.vehicle_id IS NULL) AS mantenimientos_huerfanos;

-- Distribución de entregas por viaje, incluye viajes con cero entregas
WITH n AS (SELECT t.trip_id, count(d.delivery_id) AS entregas FROM trips t LEFT JOIN deliveries d ON d.trip_id=t.trip_id GROUP BY t.trip_id)
SELECT entregas, count(*) AS viajes FROM n GROUP BY entregas ORDER BY entregas;

-- Fechas, capacidad y concordancia de pesos
SELECT count(*) FILTER (WHERE arrival_datetime IS NULL OR arrival_datetime<=departure_datetime) AS viajes_temporalmente_invalidos,
       min(departure_datetime) AS primera_salida, max(departure_datetime) AS ultima_salida,
       max(arrival_datetime) AS ultima_llegada FROM trips;
SELECT count(*) AS viajes_sobrecargados FROM trips t JOIN vehicles v USING(vehicle_id)
WHERE t.total_weight_kg IS NULL OR v.capacity_kg IS NULL OR t.total_weight_kg>v.capacity_kg OR t.total_weight_kg<=0;
WITH w AS (SELECT trip_id, sum(package_weight_kg) AS peso_entregas, count(*) FILTER(WHERE package_weight_kg IS NULL OR package_weight_kg<=0) AS pesos_invalidos FROM deliveries GROUP BY trip_id)
SELECT count(*) FILTER(WHERE abs(t.total_weight_kg-w.peso_entregas)>0.01) AS cargas_inconsistentes,
       sum(w.pesos_invalidos) AS paquetes_con_peso_invalido
FROM trips t JOIN w USING(trip_id);

-- Solapamientos: máximo de llegadas anteriores por recurso
WITH o AS (SELECT departure_datetime,
  max(arrival_datetime) OVER(PARTITION BY vehicle_id ORDER BY departure_datetime, trip_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS fin_anterior_vehiculo,
  max(arrival_datetime) OVER(PARTITION BY driver_id ORDER BY departure_datetime, trip_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS fin_anterior_conductor
FROM trips)
SELECT count(*) FILTER(WHERE departure_datetime<fin_anterior_vehiculo) AS solapes_vehiculos,
       count(*) FILTER(WHERE departure_datetime<fin_anterior_conductor) AS solapes_conductores FROM o;

-- Vigencia / contratación
SELECT count(*) FILTER(WHERE d.license_expiry IS NULL OR d.license_expiry<t.departure_datetime::date) AS licencias_no_vigentes,
       count(*) FILTER(WHERE d.hire_date IS NULL OR d.hire_date>t.departure_datetime::date) AS viajes_precontratacion
FROM trips t JOIN drivers d USING(driver_id);

-- Mantenimientos (regla por cantidad y fecha)
SELECT count(*) AS total, count(*) FILTER (WHERE maintenance_date<v.acquisition_date) AS antes_compra,
       count(*) FILTER (WHERE next_maintenance_date IS NOT NULL AND next_maintenance_date<=maintenance_date) AS proxima_fecha_invalida,
       count(*) FILTER (WHERE cost IS NULL OR cost<0) AS costo_invalido
FROM maintenance m JOIN vehicles v USING(vehicle_id);
SELECT maintenance_type, count(*) AS cantidad FROM maintenance GROUP BY maintenance_type ORDER BY cantidad DESC;
WITH t AS (SELECT vehicle_id,count(*) AS viajes FROM trips GROUP BY vehicle_id),
 m AS (SELECT vehicle_id,count(*) AS mantenimientos FROM maintenance GROUP BY vehicle_id)
SELECT v.vehicle_id,coalesce(t.viajes,0) AS viajes,coalesce(m.mantenimientos,0) AS mantenimientos,
 round(coalesce(t.viajes,0)::numeric/nullif(m.mantenimientos,0),2) AS viajes_por_mantenimiento
FROM vehicles v LEFT JOIN t USING(vehicle_id) LEFT JOIN m USING(vehicle_id) ORDER BY v.vehicle_id;

-- Cobertura / comportamiento temporal
SELECT date_trunc('month',departure_datetime)::date AS mes, count(*) AS viajes,
 round(avg(extract(epoch FROM (arrival_datetime-departure_datetime))/3600)::numeric,2) AS horas_medias
FROM trips GROUP BY 1 ORDER BY 1;
SELECT extract(isodow FROM departure_datetime) AS dia_semana, count(*) AS viajes FROM trips GROUP BY 1 ORDER BY 1;
SELECT extract(hour FROM departure_datetime) AS hora, count(*) AS viajes FROM trips GROUP BY 1 ORDER BY 1;
