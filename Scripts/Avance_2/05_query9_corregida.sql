-- FLEETLOGIX — Query 9 corregida, validada con resultados del estudiante.
-- Agrega viajes y mantenimiento por separado antes de hacer JOIN.
-- SOLO LECTURA: no modifica datos.

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
