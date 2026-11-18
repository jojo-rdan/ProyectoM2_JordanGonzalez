# FleetLogix — Integración SCD tipo 2 de Python

Esta prueba llama **las funciones originales** `stage_rows()` y `apply_driver_scd2()` del script `04_load_master_dimensions.py` (sin ejecutarlo desde su `main`).

## Instalación

1. Coloca `09_test_driver_scd2_python_isolated.py` en `Scripts/Avance_3/`, **junto al `04_load_master_dimensions.py` original**.
2. Comprueba que el `.env` de la raíz conserva la conexión Snowflake que ya funcionó mediante OAuth.
3. Desde la raíz del repositorio ejecuta:

```powershell
python Scripts/Avance_3/09_test_driver_scd2_python_isolated.py
```

## Aislamiento y comportamiento

- Lee el `dim_driver.csv` que ya preparaste; **no lo modifica**.
- Cambia en memoria un solo `DRIVER_STATUS` a `SCD2_TEST` y recalcula el mismo SHA-256 canónico usado en la transformación.
- Crea **dos tablas `TEMPORARY` en el esquema `STAGING`** en una sesión nueva. Una copia las filas actuales de `DIM_DRIVER`, pero tiene una secuencia `IDENTITY` propia que empieza en 900000000000; no se usa `CLONE` ni una secuencia compartida.
- Ejecuta **la función original** `apply_driver_scd2()` dos veces, usando un guardián que solo admite sus sentencias UPDATE/INSERT y redirige todas las referencias a `ANALYTICS.DIM_DRIVER` hacia la tabla temporal.
- Comprueba 401 versiones, 400 actuales, una histórica, unicidad de claves, cierre correcto de vigencias e idempotencia en la segunda pasada.
- Verifica antes y después las tablas reales. Deben seguir con 400 conductores, 400 actuales y 400000 entregas; sin `SCD2_TEST`.
- Al cerrar la conexión, las tablas temporales desaparecen. No se conecta a PostgreSQL.

## Nota

Esta es una prueba de integración **de las funciones de staging y SCD2 del cargador Python**. No prueba el programa entero de extremo a extremo (incluidos los 3 MERGE, autenticación desatendida y automatización nocturna). Las fechas SCD2 representan cuándo se observó el cambio, no una reconstrucción histórica de atributos.

Si aparece un error, no edites ni borres las tablas reales. Comparte la salida de la terminal; si falló una validación, el script intenta ROLLBACK.
