-- FLEETLOGIX — Reejecución final de las ocho consultas tras crear índices.
-- Aún PENDIENTE como medición controlada para el conjunto completo.
-- Ejecutar cada plan 5 veces, registrar Execution Time y comparar medianas.
-- No mezclar resultados de Query 9 original con Query 9 corregida.
-- Mantener misma fecha, datos, estadísticas y entorno cuando sea posible.

-- QUERY 1
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Conocer la composición de la flota
SELECT 
    vehicle_type,
    COUNT(*) as cantidad
FROM vehicles
GROUP BY vehicle_type
ORDER BY cantidad DESC;

-- QUERY 2
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Prevenir problemas legales por licencias vencidas
SELECT 
    first_name,
    last_name,
    license_number,
    license_expiry
FROM drivers
WHERE license_expiry < CURRENT_DATE + INTERVAL '30 days'
ORDER BY license_expiry;

-- QUERY 3
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Monitorear operaciones en curso
SELECT 
    status,
    COUNT(*) as total_viajes
FROM trips
GROUP BY status;

-- QUERY 4
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Identificar demanda por ciudad para planificación de recursos
SELECT 
    r.destination_city,
    COUNT(DISTINCT t.trip_id) as total_viajes,
    COUNT(d.delivery_id) as total_entregas,
    SUM(d.package_weight_kg) as peso_total_kg
FROM routes r
INNER JOIN trips t ON r.route_id = t.route_id
INNER JOIN deliveries d ON t.trip_id = d.trip_id
WHERE t.departure_datetime >= CURRENT_DATE - INTERVAL '60 days'
GROUP BY r.destination_city
ORDER BY total_entregas DESC;

-- QUERY 5
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Evaluar carga de trabajo por conductor
SELECT 
    d.driver_id,
    d.first_name || ' ' || d.last_name as nombre_completo,
    d.license_expiry,
    COUNT(t.trip_id) as viajes_totales,
    SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as viajes_completados
FROM drivers d
LEFT JOIN trips t ON d.driver_id = t.driver_id
WHERE d.status = 'active'
GROUP BY d.driver_id, d.first_name, d.last_name, d.license_expiry
HAVING COUNT(t.trip_id) > 0
ORDER BY viajes_completados DESC;

-- QUERY 7
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Identificar rutas ineficientes para optimización
SELECT 
    r.route_code,
    r.origin_city || ' -> ' || r.destination_city as ruta,
    r.distance_km,
    COUNT(t.trip_id) as viajes_realizados,
    AVG(t.fuel_consumed_liters) as promedio_combustible_litros,
    ROUND(AVG(t.fuel_consumed_liters / NULLIF(r.distance_km, 0)) * 100, 2) as litros_por_100km,
    SUM(t.fuel_consumed_liters) as combustible_total
FROM routes r
INNER JOIN trips t ON r.route_id = t.route_id
WHERE t.fuel_consumed_liters IS NOT NULL 
    AND r.distance_km > 0
    AND t.status = 'completed'
GROUP BY r.route_id, r.route_code, r.origin_city, r.destination_city, r.distance_km
HAVING COUNT(t.trip_id) >= 50
ORDER BY litros_por_100km DESC
LIMIT 10;

-- QUERY 9 (VERSIÓN CORREGIDA)
EXPLAIN (ANALYZE, BUFFERS)
WITH viajes_por_vehiculo AS (
    SELECT
        t.vehicle_id,
        COUNT(t.trip_id) AS total_viajes,
        SUM(r.distance_km) AS km_totales
    FROM trips t
    INNER JOIN routes r ON t.route_id = r.route_id
    WHERE t.status = 'completed'
    GROUP BY t.vehicle_id
),
mantenimiento_por_vehiculo AS (
    SELECT
        m.vehicle_id,
        COUNT(m.maintenance_id) AS cantidad_mantenimientos,
        SUM(m.cost) AS costo_mantenimiento_total
    FROM maintenance m
    GROUP BY m.vehicle_id
)
SELECT
    v.vehicle_type,
    COUNT(v.vehicle_id) AS cantidad_vehiculos,
    SUM(t.total_viajes) AS viajes_totales,
    SUM(t.km_totales) AS kilometros_totales,
    SUM(m.costo_mantenimiento_total) AS costo_total_mantenimiento,
    ROUND(SUM(m.costo_mantenimiento_total) / NULLIF(SUM(t.km_totales), 0), 2) AS costo_por_km,
    ROUND(AVG(m.costo_mantenimiento_total / NULLIF(m.cantidad_mantenimientos, 0)), 2) AS costo_promedio_por_mantenimiento
FROM vehicles v
INNER JOIN viajes_por_vehiculo t ON v.vehicle_id = t.vehicle_id
INNER JOIN mantenimiento_por_vehiculo m ON v.vehicle_id = m.vehicle_id
WHERE t.km_totales > 0
  AND m.costo_mantenimiento_total > 0
GROUP BY v.vehicle_type
ORDER BY costo_por_km DESC;

-- QUERY 11
EXPLAIN (ANALYZE, BUFFERS)
-- Problema de negocio: Proyectar necesidades futuras basadas en tendencias
WITH viajes_mensuales AS (
    SELECT 
        DATE_TRUNC('month', departure_datetime) as mes,
        COUNT(*) as total_viajes,
        SUM(total_weight_kg) as peso_total,
        AVG(fuel_consumed_liters) as combustible_promedio
    FROM trips
    WHERE status = 'completed'
    GROUP BY DATE_TRUNC('month', departure_datetime)
)
SELECT 
    TO_CHAR(mes, 'YYYY-MM') as periodo,
    total_viajes,
    LAG(total_viajes, 1) OVER (ORDER BY mes) as viajes_mes_anterior,
    LEAD(total_viajes, 1) OVER (ORDER BY mes) as viajes_mes_siguiente,
    total_viajes - LAG(total_viajes, 1) OVER (ORDER BY mes) as cambio_absoluto,
    ROUND((total_viajes - LAG(total_viajes, 1) OVER (ORDER BY mes))::NUMERIC / 
          NULLIF(LAG(total_viajes, 1) OVER (ORDER BY mes), 0) * 100, 2) as cambio_porcentual,
    ROUND(peso_total / 1000, 2) as toneladas_transportadas,
    ROUND(combustible_promedio, 2) as combustible_promedio_viaje,
    AVG(total_viajes) OVER (ORDER BY mes ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as promedio_movil_3m
FROM viajes_mensuales
ORDER BY mes DESC
LIMIT 12;
