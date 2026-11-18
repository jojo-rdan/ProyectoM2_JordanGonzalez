# FleetLogix · Avance #3 · Cargador incremental de hechos (primera validación)

## Estado y alcance

Se completó la prueba de preparación del delta: 400.000 filas iguales, 0 nuevas, 0 modificadas, 0 ausentes. Este paquete añade un **cargador por diferencias** independiente del `08_load_fact_deliveries.py` de recarga total. **En esta etapa solamente validaremos la autopueba local y el caso real de delta vacío**. La aplicación de un delta NO VACÍO requiere un ensayo posterior de integración aislada antes de autorizársela sobre `ANALYTICS.FACT_DELIVERIES`.

Archivos:
- `13_load_incremental_fact_delta.py` — cargador experimental con control de no-op, validaciones y lógica de carga acotada al delta.
- `15_validate_incremental_baseline.sql` — comprobación opcional de la línea base en Snowflake, solo SELECT.

## Instalación

Coloca el archivo Python en la **misma carpeta** que el cargador validado `08_load_fact_deliveries.py`: `Scripts/Avance_3/`. No reemplaces el `08`, `12` ni el orquestador `10`. Reutiliza `.venv` y `.env` de FleetLogix. El detector previo `12_prepare_incremental_fact_delta.py` ya creó:

```
data/staging/avance_3/incremental/fact_deliveries_delta.csv
data/staging/avance_3/incremental/fact_deliveries_delta_audit.json
```

El cargador exige el encabezado de 23 columnas, la auditoría `VALIDATED_NOT_LOADED`, los conteos coherentes, hashes SHA-256 válidos, referencias de identidad formadas, fechas, política `SYNTHETIC_REVENUE_V1` e importes compatibles con la fórmula.

## Las únicas dos ejecuciones recomendadas en este momento

1. **Prueba local ficticia, sin conexión:**

   ```powershell
   python Scripts/Avance_3/13_load_incremental_fact_delta.py --self-test
   ```

   Esperado: altas y modificaciones simuladas OK, cambios indebidos bloqueados, recuentos erróneos bloqueados.

2. **Validación del delta real (0 filas), sin conexión:**

   ```powershell
   python Scripts/Avance_3/13_load_incremental_fact_delta.py
   ```

   Esperado:

   ```text
   Delta OK: 0 filas, 0 nuevas, 0 modificadas; 400,000 sin cambios
   DELTA VACÍO — NO-OP: sin conexión a Snowflake ni operaciones PUT/COPY/MERGE
   ```

**No utilices `--execute` todavía.** Para deltas vacíos está implementada una ruta sin operaciones en Snowflake, incluso si se especifica `--execute`, pero es preferible demostrar primero el modo de validación. Para deltas no vacíos, la escritura requiere **dos controles de ejecución** (`--execute --confirm-nonempty-write`). No uses esa combinación hasta que probemos un `MERGE` aislado y tengamos confirmadas las reglas de concurrencia.

## Diseño técnico del futuro MERGE (todavía no probado en Snowflake real)

- Carga solo el `fact_deliveries_delta.csv` a un **stage y una tabla temporales**.
- Verifica `PUT`, `COPY INTO`, conteos, hashes, importes y resolución de las seis dimensiones.
- Reutiliza `build_resolved_sql()` y `merge_facts()` del `08` ya utilizado exitosamente para recarga total, para reducir divergencias.
- Inicia `BEGIN` solo **después** de crear las tablas temporales, porque `CREATE TABLE`, incluso temporal, es DDL y confirma implícitamente una transacción anterior en Snowflake.
- Actualiza o inserta únicamente los `DELIVERY_ID` del delta; comprueba integridad y medidas afectadas antes de `COMMIT`. Ante excepción, ejecuta `ROLLBACK`.
- La protección es para un ensayo **manual y sin otros escritores concurrentes**, no equivale a una solución de producción.

## Limitaciones que no debemos ocultar

1. **No es CDC real**: el preparador `12` todavía lee todos los hashes de Snowflake y todas las entregas del CSV completo. Ahorra filas a cargar, no elimina la extracción completa de PostgreSQL.
2. **No incorpora aún nuevas dimensiones o versiones históricas automáticamente**: antes de un futuro delta con entregas nuevas se deben cargar las dimensiones implicadas y comprobar la vigencia SCD2. Cambiar una dimensión puede exigir recalcular hechos aunque el `SOURCE_ROW_HASH` de sus atributos operativos no cambie.
3. **El transformador `07` todavía utiliza totales estáticos** del conjunto académico para validar la recarga total. Antes de procesar altas genuinas se debe adaptar a conteos variables y escenarios por viaje.
4. **No hay coordinador distribuido**: una escritura simultánea o una revisión antigua de datos puede requerir regenerar el delta. Deben implementarse bloqueo, snapshots coherentes y/o una estrategia CDC en etapas posteriores.
5. **Sin borrados automáticos**: ausencias de entregas hacen fallar al detector `12`, no autorizan la eliminación de hechos.
6. **No sirve para tarea nocturna desatendida**: usa OAuth con navegador hasta que implementemos autenticación no interactiva con permisos limitados.
7. **Datos locales sensibles**: conservar `data/staging/avance_3/` en `.gitignore` y evitar subir CSV/credenciales a Git.

## Validación técnica realizada sobre el código

- Compilación Python: OK.
- Autopueba ficticia local: 1 alta + 1 modificación, alteración del hash/importe rechazada, conteo erróneo rechazado.
- No-op con delta de cero filas, incluyendo el caso de invocar `--execute`: OK **en simulación local**, sin conectarse a Snowflake.
- La vía de carga de un **delta real no vacío todavía no está verificada** contra Snowflake: no debe presentarse como lista para producción.
