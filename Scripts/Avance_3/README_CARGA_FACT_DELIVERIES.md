# FleetLogix — Avance #3 | Carga controlada de FACT_DELIVERIES

## Requisitos ya completados

- `ANALYTICS.FACT_DELIVERIES` creada, vacía antes de la primera carga.
- Dimensiones `DIM_DATE` (2557), `DIM_TIME` (24), `DIM_VEHICLE` (200),
  `DIM_DRIVER` (400 versiones actuales), `DIM_ROUTE` (50),
  `DIM_CUSTOMER` (389334) pobladas y validadas.
- `07_extract_transform_fact_deliveries.py` ejecutado con éxito:
  `fact_deliveries.csv` y `fact_deliveries_audit.json` en
  `data/staging/avance_3/prepared/`.

## Archivos

Guardar `08_load_fact_deliveries.py` en `Scripts/Avance_3/`. Guardar
`10_validate_fact_deliveries.sql` allí o en la carpeta SQL que use el repo.
No sustituye ni modifica `07_extract_transform_fact_deliveries.py`.

## Ejecución

Desde la raíz del proyecto con `.venv` activado:

```powershell
python Scripts/Avance_3/08_load_fact_deliveries.py
```

Este modo **solo lee archivos locales**, verifica encabezados, cantidades,
identificadores únicos, fechas, reglas de negocio, hashes, 100000 viajes,
4701486.980000 km y 633064.820000 litros. No conecta a Snowflake.

Si la validación local es correcta:

```powershell
python Scripts/Avance_3/08_load_fact_deliveries.py --execute
```

La conexión usa `OAUTH_AUTHORIZATION_CODE` (navegador y cuenta Google),
reutilizando `.env`. El proceso usa:

1. Comprobación de `DIM_TIME` (24 horas 0–23; descubre columna de hora).
2. Comprobación de claves de negocio dimensionales.
3. Tabla temporal y stage temporal (`PUT`, `COPY INTO`).
4. Tabla temporal de hechos resueltos con las seis claves dimensionales,
   seleccionando la versión SCD2 del conductor vigente para la fecha de entrega.
5. Controles de cardinalidad, claves huérfanas, ingresos nulos y conciliación
   exacta de kilómetros y combustible.
6. **Solo si todo lo anterior pasa**, `BEGIN` → `MERGE` por `DELIVERY_ID` →
   validación del destino → `COMMIT`. Ante error en la fase transaccional,
   `ROLLBACK`.

La creación de temporales se hace antes de `BEGIN` porque el DDL de Snowflake
hace commits implícitos. El `MERGE` se ejecuta dentro de la transacción.

## Resultados esperados

- Primera ejecución: 400000 inserciones, 0 actualizaciones.
- Segunda ejecución con el mismo CSV: 0 inserciones, 0 actualizaciones.
- `FACT_DELIVERIES`: 400000 registros / 400000 identificadores únicos.
- Distancia: 4701486.980000 km; combustible: 633064.820000 litros.
- No existen claves dimensionales sin resolver.
- Ingreso estimado: **NULL** por política todavía no definida. No se
  presenta como ingreso real.

Después ejecutar `10_validate_fact_deliveries.sql` en Snowsight.

## Notas importantes

- `DIM_TIME` debe contener una columna de hora 0–23 o un `TIME_KEY` que
  corresponda realmente a las horas 0–23. Si no se puede verificar, el script
  **se detiene** y solicita inspeccionar `DESCRIBE TABLE ANALYTICS.DIM_TIME`.
- `DIM_DRIVER` usa historial técnico SCD tipo 2. La versión inicial con fecha
  técnica 1900-01-01 **no prueba atributos históricos observados**.
- No subir a Git los CSV: pueden incluir datos de clientes. Añadir
  `data/staging/avance_3/` al `.gitignore`.
- Este cargador está cerrado sobre la línea base auditada (400000/100000);
  al implementar incrementales diarios habrá que cambiar las validaciones de
  cantidades fijas y definir un corte por fecha/agua alta.
- `OAUTH_AUTHORIZATION_CODE` necesita interacción humana: no sirve para
  ejecución nocturna sin usuario. Para la automatización posterior crear
  rol mínimo y autenticación de servicio no interactiva.
- Este script no fue ejecutado contra la cuenta real del proyecto; se
  comprobó su sintaxis y deberá validarse con la consola del usuario.
