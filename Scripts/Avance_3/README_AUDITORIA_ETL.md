# FleetLogix — auditoría inicial y orquestación manual (Avance 3)

## Requisitos

- Las tablas `CONTROL.ETL_RUNS` y `CONTROL.ETL_RUN_STEPS` ya deben existir.
- Mantener el archivo `.env` en la raíz del repositorio con las variables de Snowflake ya usadas por los scripts anteriores.
- Python `.venv` con `snowflake-connector-python` y `python-dotenv`.
- Conexión interactiva OAuth por navegador, utilizando rol `SYSADMIN` para estas pruebas académicas.
- No subir el `.env` ni los CSV de staging a GitHub.

## Instalación

Colocar `10_run_etl_pipeline.py` y `14_validate_etl_audit.sql` en `Scripts/Avance_3/`.

## Paso actual: auditoría de humo, sin tocar datos operacionales

Desde la raíz del proyecto:

```powershell
python Scripts/Avance_3/10_run_etl_pipeline.py --audit-test
```

Se abre OAuth en el navegador. Este modo **solo lee** las tablas `ANALYTICS` y escribe en `CONTROL`:

- Un `RUN` con `RUN_MODE = AUDIT_SMOKE` y estado final `SUCCESS`.
- Dos `STEPS`, uno para validar conteos dimensionales y otro para validar la política de ingresos.

Se esperan 400 conductores, 389.334 clientes y 400.000 entregas. El ingreso sintético esperado es exactamente `6270850032.24` COP. Si falla alguna aserción, el RUN debe quedar `FAILED` y se registrará un STEP fallido.

Ejecutar `14_validate_etl_audit.sql` en Snowsight. Si no había otras auditorías, los totales esperados tras una prueba exitosa son `TOTAL_RUNS = 1` y `TOTAL_STEPS = 2`.

## Modo orquestador completo: **NO ejecutarlo aún**

El script también admite la opción explícita:

```powershell
python Scripts/Avance_3/10_run_etl_pipeline.py --full
```

Esta opción reejecutará secuencialmente los archivos 02, 03, 04, 05, 06 con `--execute`, 07 y 08 con `--execute`. Registra cada paso y detiene el proceso si una etapa sale con código distinto de cero. Los scripts de carga abren sus propias conexiones OAuth; pueden aparecer varias autenticaciones en navegador. Se diseñó para revisión manual posterior, no para ejecuciones sin supervisión.

**Limitaciones que aún debemos resolver:**

- Es `FULL_REFRESH_IDEMPOTENT`, no un ETL incremental real. Todavía lee 400.000 entregas en cada ejecución.
- Las etapas tienen transacciones independientes: si la etapa final falla, las anteriores que ya hicieron `COMMIT` permanecen cargadas. La idempotencia permite reanudar mediante reejecución, pero no hay `ROLLBACK` global.
- Por ahora, las etapas de subprocess registran éxito/error y nombre de script; `ROWS_READ`, `ROWS_INSERTED` y `ROWS_UPDATED` permanecen `NULL` para evitar métricas inventadas. Más adelante integraremos métricas estructuradas.
- El modo `--full` exige autenticación interactiva de Snowflake. No usar todavía con Task Scheduler.
- Los controles de conteos están fijados a la foto académica actual. Para incrementalidad será necesario reemplazarlos por controles dinámicos y una estrategia de cambio de origen.
- Este script no contiene lógica para gestionar solapamientos ni abortos abruptos que dejen RUNNING; la detección de ejecuciones obsoletas y exclusión mutua se abordará antes de programarlo.

## Consulta rápida

```sql
SELECT RUN_ID, RUN_MODE, STATUS, STARTED_AT, FINISHED_AT
FROM FLEETLOGIX_DWH.CONTROL.ETL_RUNS
ORDER BY STARTED_AT DESC LIMIT 5;
```
