-- FLEETLOGIX — Consultas de comprobación no destructivas.
-- Operan sobre public en fleetlogix_db; no insertar ni modificar datos.

-- A. Inventario actual (deberían aparecer 19 índices si se conservan los 5).
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('vehicles', 'drivers', 'routes', 'trips', 'deliveries', 'maintenance')
ORDER BY tablename, indexname;

-- B. Volúmenes y cobertura temporal para contextualizar mediciones.
SELECT 'vehicles' AS tabla, COUNT(*)::BIGINT AS filas FROM vehicles
UNION ALL SELECT 'drivers', COUNT(*) FROM drivers
UNION ALL SELECT 'routes', COUNT(*) FROM routes
UNION ALL SELECT 'trips', COUNT(*) FROM trips
UNION ALL SELECT 'deliveries', COUNT(*) FROM deliveries
UNION ALL SELECT 'maintenance', COUNT(*) FROM maintenance;

SELECT MIN(departure_datetime) AS primer_viaje,
       MAX(departure_datetime) AS ultimo_viaje,
       CURRENT_DATE AS fecha_de_consulta
FROM trips;

-- C. Cardinalidad de una unión ingenua por vehículo para Q9.
-- Esperado en el conjunto sintético: 2.500.000 filas.
SELECT COUNT(*) AS filas_join_no_agregado
FROM vehicles v
JOIN trips t ON t.vehicle_id = v.vehicle_id
JOIN maintenance m ON m.vehicle_id = v.vehicle_id
WHERE t.status = 'completed';

-- D. Prueba selectiva relacionada con el índice 1.
EXPLAIN (ANALYZE, BUFFERS)
SELECT delivery_id, trip_id, tracking_number, package_weight_kg
FROM deliveries WHERE trip_id = 1;

-- E. Prueba selectiva candidata para el índice 2.
-- No se dispone de resultado de esta prueba en las evidencias actuales.
EXPLAIN (ANALYZE, BUFFERS)
SELECT trip_id, driver_id, departure_datetime, status
FROM trips WHERE driver_id = 384;
