-- FLEETLOGIX — Cinco índices evaluados en Avance #2.
-- Registro de DDL ejecutado por el estudiante; NO volver a ejecutar
-- innecesariamente en un servidor compartido o de producción.
-- La creación de índices implica espacio y costo adicional de escritura.
-- IF NOT EXISTS solo controla nombres, no demuestra identidad de definición.

-- 1. Query 4: NO utilizado en la consulta analítica; útil al filtrar por trip_id.
CREATE INDEX IF NOT EXISTS idx_deliveries_trip_id
    ON public.deliveries (trip_id);
ANALYZE public.deliveries;

-- 2. Query 5: NO utilizado en la consulta analítica.
CREATE INDEX IF NOT EXISTS idx_trips_driver_id
    ON public.trips (driver_id);
ANALYZE public.trips;

-- 3. Query 7: NO utilizado en la consulta analítica.
CREATE INDEX IF NOT EXISTS idx_trips_route_id
    ON public.trips (route_id);
ANALYZE public.trips;

-- 4. Query 9 CORREGIDA: NO utilizado en la consulta analítica.
CREATE INDEX IF NOT EXISTS idx_trips_vehicle_id
    ON public.trips (vehicle_id);
ANALYZE public.trips;

-- 5. Query 11: UTILIZADO (Index Scan), elimina el sort inicial en disco.
-- Requiere departure_datetime TIMESTAMP WITHOUT TIME ZONE,
-- como se verificó para esta base.
CREATE INDEX IF NOT EXISTS idx_trips_completed_month
    ON public.trips ((DATE_TRUNC('month', departure_datetime)))
    WHERE status = 'completed';
ANALYZE public.trips;
