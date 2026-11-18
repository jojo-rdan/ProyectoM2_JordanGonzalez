# FleetLogix — Avance #3 · Cierre técnico con limitaciones declaradas

## Evidencias confirmadas por ejecución del estudiante (17-nov-2026)

| Hito | Resultado |
|---|---|
| Snowflake `FLEETLOGIX_DWH`, `FLEETLOGIX_WH` | Conexión Python/OAuth validada |
| `DIM_DATE`, `DIM_TIME` | 2.557 / 24 |
| `DIM_VEHICLE`, `DIM_DRIVER`, `DIM_ROUTE` | 200 / 400 / 50 |
| `DIM_CUSTOMER` | 389.334 identidades provisionales; cero duplicadas |
| `FACT_DELIVERIES` | 400.000 entregas, 100.000 viajes |
| Distancia asignada (sin duplicar viajes) | 4.701.486,980000 km |
| Combustible asignado (sin duplicar viajes) | 633.064,820000 L |
| Ingresos **sintéticos** | 6.270.850.032,24 COP, `SYNTHETIC_REVENUE_V1` |
| Idempotencia completa | MERGE 0 inserciones, 0 actualizaciones en segunda ejecución |
| SCD2 Python (aislado) | 401 versiones, 400 actuales, 1 histórica; segunda pasada estable |
| Auditoría / orquestador `--full` | 9/9 pasos `SUCCESS`, 0 fallidos |
| Preview incremental | 400.000 iguales; 0 altas, 0 modificaciones, 0 ausencias |
| Delta incremental | 0 filas; no-op sin PUT, COPY ni MERGE |

**RUN_ID ejemplo confirmado:** `1111af91-384d-4f6f-9ce2-ee647afbf0ca`.
Las cantidades son resultados reportados en la consola/Snowsight del estudiante, no verificaciones ejecutadas por este paquete sobre su cuenta.

## Diseño dimensional y reglas

- Grano de `FACT_DELIVERIES`: 1 fila por `DELIVERY_ID` completado.
- Seis dimensiones: fecha, hora, vehículo, conductor (SCD2), ruta y cliente.
- Cliente: identidad provisional SHA-256 de nombre y dirección normalizados. No hay `customer_id` del origen.
- Distancia y combustible de cada viaje se asignan proporcionalmente por peso, con ajuste de residuo y conciliación.
- Ingresos: `ROUND(7000 + 20*PACKAGE_WEIGHT_KG + 300*ALLOCATED_DISTANCE_KM, 2)` COP por entrega. Tarifa **didáctica**, no facturación.
- Hash `SOURCE_ROW_HASH` y `MERGE` por entrega para idempotencia.

## Piezas de cierre incluidas

- `Scripts/Avance_3/16_finalize_analytics.sql`: dos tablas de preagregación y dos vistas `SECURE` (OPERATIONS incluye los datos necesarios de cliente/dirección para el despacho (acceso restringido); SALES mensual solo contiene agregados, sin nombres/direcciones).
- `Scripts/Avance_3/17_roles_opcionales.sql`: roles separados y grants exclusivamente sobre vistas; ejecutar con permisos administrativos solo si se requieren roles reales.
- `Scripts/Avance_3/18_validacion_cierre.sql`: conteos, conciliación y comprobación de vistas y retención.
- `Notebooks/Avance_3_DataWarehouse.ipynb`: informe reproducible con código de lectura opcional.

## Limitaciones pendientes para no declarar capacidades inexistentes

1. **Incrementalidad parcial:** detección por `DELIVERY_ID` y hash y delta vacío comprobados; delta **no vacío todavía no se probó con MERGE real aislado**. La extracción desde PostgreSQL sigue siendo completa y el transformador asume conteos fijos de datos de laboratorio. No es CDC.
2. **Nocturno desatendido no configurado:** los cargadores usan OAuth de navegador. Se requiere identidad de servicio, autenticación no interactiva, permisos mínimos, bloqueo de concurrencia y programación en Windows antes de crear una tarea nocturna real.
3. **Time Travel de 30 días no comprobado:** la base se creó con 1 día de retención. 30 días requiere Snowflake Enterprise o superior y tablas permanentes; no intentar `ALTER` sin comprobar la edición y evaluar el coste.
4. **Preagregados son snapshots:** el SQL de `16` debe reejecutarse al terminar cargas que cambien hechos. No son refrescados automáticamente.
5. **Roles:** crear vistas `SECURE` no concede por sí solo acceso a usuarios; ejecutar el script opcional y asignar roles a usuarios reales bajo control administrativo para demostrar la segregación efectiva.
6. **SCD2:** historia solo desde observaciones del ETL; `VALID_FROM` inicial 1900 es ancla técnica, no dato histórico observado.
7. **Datos:** el conjunto origen es sintético; no inferir productividad, tarifas ni rendimiento comercial reales.

## Estado de entrega

**Modelo, cargas, auditoría, validaciones, idempotencia y pruebas de SCD2:** terminados en el entorno académico.
**Requerimientos de operación desatendida, CDC completo, retención 30 días y roles efectivos:** pendientes o condicionados; deben constar así en la entrega.
