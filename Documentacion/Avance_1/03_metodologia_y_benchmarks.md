# 3. Metodología de medición y evaluación de índices

## Protocolo utilizado

1. Seleccionar una consulta SQL definida en `02_queries_analysis.sql`, sin cambiar sus filtros, columnas o lógica entre pruebas de un mismo índice.
2. Ejecutar `EXPLAIN (ANALYZE, BUFFERS)` para registrar nodos, cardinalidad, buffers y tiempos.
3. Para índices 2–5, registrar **cinco ejecuciones antes**, crear índice y actualizar estadísticas con `ANALYZE`, luego registrar **cinco ejecuciones después**.
4. Resumir cada serie con su **mediana**; conservar todas las observaciones sin descartar valores altos o bajos.
5. Comparar el plan estructural, no solamente milisegundos. **Un índice que no aparece en el plan no demuestra haber acelerado esa consulta.**
6. En Query 9, comparar índices sobre **la versión corregida en ambos lados**, separando la mejora de reescritura de la de indexación.

**Excepción:** para Query 4 hay **una sola ejecución original** (115,901 ms) contra cinco posteriores (mediana 102,567 ms). La variación registrada es descriptiva y **no comparable con rigor equivalente** a 5 vs 5.

## Condiciones y límites de causalidad

- Las pruebas fueron ejecutadas localmente por el estudiante. No se suministraron muestras repetidas de referencia sin índice para Query 4, ni mediciones bajo condiciones controladas de carga del servidor.
- Los tiempos pueden depender de caché, planificador, CPU, concurrencia, estadísticas, orden de ejecución y versión del esquema. Las cinco pruebas no sustituyen un benchmark de producción.
- `shared hit` describe accesos a páginas atendidos en búfer compartido; no equivale a lecturas físicas. **Más hits no demuestra por sí solo peor rendimiento.**
- `Execution Time` de EXPLAIN no incluye latencia de red, descarga ni renderización del grid de DBeaver.
- Las pruebas se hicieron **secuencialmente**, por lo que los índices posteriores se evalúan con los índices anteriores presentes. Esta circunstancia debe conservarse al reproducir la prueba.
- `CURRENT_DATE` cambia los datos elegibles de la Query 4 con el paso de los días; anotar fecha o fijarla en una variante exclusivamente experimental.
- El archivo `08_benchmark_final.sql` facilita correr las **ocho queries** en un mismo ambiente final; esa reejecución integral todavía no está registrada y no se simula en este informe.

## Resultados de los cinco experimentos

| Query | Índice | Mediana antes (ms) | Mediana después (ms) | Variación de tiempo | ¿Índice usado? |
|---|---|---:|---:|---:|---|
| 4 | `idx_deliveries_trip_id` | 115,901* | 102,567 | −11,50 % | **No** |
| 5 | `idx_trips_driver_id` | 53,856 | 60,106 | +11,61 % | **No** |
| 7 | `idx_trips_route_id` | 80,424 | 77,083 | −4,15 % | **No** |
| 9 corregida | `idx_trips_vehicle_id` | 57,756 | 54,078 | −6,37 % | **No** |
| 11 | `idx_trips_completed_month` | 79,564 | 41,313 | **−48,08 %** | **Sí** |

*Query 4: valor original de una sola ejecución, no mediana de cinco.* Las cifras son redondeos de las mediciones aportadas; las diez observaciones por experimento están en [`../Datos/benchmarks_5_indices_repeticiones.csv`](../Datos/benchmarks_5_indices_repeticiones.csv), salvo la excepción de Q4.

Un valor negativo indica reducción del tiempo, no causalidad demostrada. Q5 presenta aumento de mediana, pero su índice no fue utilizado: **no afirmar que el índice ralentizó la query**.

## Evolución de planes y hallazgos

### Índice 1: `deliveries(trip_id)` — Query 4

- **Antes:** `Parallel Seq Scan` sobre 400.000 `deliveries`; `Parallel Hash Join`; `Bitmap Index Scan` con `idx_trips_departure` para 5.400 viajes; 7.643 shared hits; 115,901 ms.
- **Después:** mismo plan, 7.643 shared hits; EXPLAIN posterior 115,588 ms.
- **Demostración complementaria:** consulta `WHERE trip_id = 1` utilizó `Index Scan using idx_deliveries_trip_id`, devolvió **4 filas** y registró **0,029 ms**. Esto **demuestra uso**, no reducción cuantificada sin línea base selectiva.
- **Veredicto:** no justificado como optimización de Query 4. Posible utilidad operativa para localizar entregas de un viaje; considerar su costo de escritura antes de mantenerlo.

### Índice 2: `trips(driver_id)` — Query 5

- **Antes/después:** `Seq Scan` sobre los 100.000 viajes, `Hash Right Join` y `HashAggregate`; 1.045 shared hits.
- **Después:** plan individual 43,678 ms, sin presencia del nuevo índice.
- **Veredicto:** no mejoró de forma demostrable la agregación global. La prueba selectiva por conductor fue sugerida pero **su resultado no está disponible**.

### Índice 3: `trips(route_id)` — Query 7

- **Antes/después:** `Seq Scan` sobre 100.000 viajes, `Hash Join` con 50 rutas, `HashAggregate` y `top-N heapsort`; 1.041 shared hits.
- **Después:** plan individual 82,750 ms, sin presencia del nuevo índice.
- **Veredicto:** no demuestra mejora causal; podría ser útil cuando se filtra un subconjunto pequeño de rutas, pendiente de medir.

### Índice 4: `trips(vehicle_id)` — Query 9 CORREGIDA

- **Antes/después:** `Seq Scan` sobre los 100.000 viajes, `HashAggregate` por vehículo y uniones hash con mantenimientos y vehículos; 1.143 shared hits.
- **Después:** plan individual 57,348 ms, sin presencia del nuevo índice.
- **Veredicto:** no mejora demostrada. **No confundir** con la reducción de 1.510,417 a 57,661 ms causada por la corrección lógica anterior.

### Índice 5: expresión parcial por mes — Query 11

```sql
CREATE INDEX IF NOT EXISTS idx_trips_completed_month
ON public.trips ((DATE_TRUNC('month', departure_datetime)))
WHERE status = 'completed';
```

- `departure_datetime` se verificó como **`timestamp without time zone`**, condición relevante para la inmutabilidad de esta expresión en el índice B-tree.
- **Antes:** `Seq Scan` de 100.000 viajes → `Sort external merge`, **3.088 kB en disco**, 386 bloques temporales leídos / 387 escritos → `GroupAggregate` (25 meses) → `WindowAgg` → `Sort` final `top-N heapsort` (12 filas).
- **Después:** `Index Scan using idx_trips_completed_month` → `GroupAggregate` (25 meses) → `WindowAgg` → `Sort` final `top-N heapsort`. **Desaparece el Sort inicial y no se reportan bloques temporales.**
- **Buffers:** 1.040 shared hits antes; 6.069 después. El aumento es compatible con accesos adicionales a páginas de tabla durante el Index Scan; no invalida el menor tiempo mediano.
- **Planes individuales:** 102,155 ms antes vs. 38,991 ms después. Los planes comparados son ejecuciones separadas; para la métrica de mejora principal se usan las medianas 5 vs 5.
- **Veredicto:** índice realmente utilizado, reducción observada **48,08 %** con una explicación estructural clara: eliminar ordenamiento inicial costoso.

## Baseline inicial de las ocho consultas

| Query | Versión | Execution Time (ms) |
|---|---|---:|
| 1 | Original | 0,140 |
| 2 | Original | 0,131 |
| 3 | Original | 30,702 |
| 4 | Original | 115,901 |
| 5 | Original | 44,092 |
| 7 | Original | 91,673 |
| 9 | Original, **incorrecta** | 1.510,417 |
| 9 | Corregida, **válida** | 57,661 |
| 11 | Original | 102,155 |

**No usar esta tabla como comparación pareada contra las medianas de cinco pruebas posteriores**: se creó solo como registro de las primeras capturas. La evaluación 5 vs 5 figura en la tabla anterior.

## Protocolo recomendado para consolidación final

1. Anotar fecha/hora, `SELECT version()`, parámetros de `work_mem`, `shared_buffers`, `max_parallel_workers_per_gather`, y conteos de tablas; preservar resultados.
2. Usar `08_benchmark_final.sql` (Q9 **corregida**) y recopilar cinco tiempos por consulta **sin modificar SQL**; documentar plan y buffers.
3. Si se desea estimar causalidad por índice, comparar contra un **clon de la misma base** con esos índices ausentes (no borrar índices del entorno original). Repetir lotes A/B alternados con calentamiento y la misma configuración.
4. Conservar cualquier diferencia de planes, no eliminar valores atípicos sin criterio predefinido, presentar medianas, rango y limitaciones.
5. Evitar aplicar `SET enable_seqscan = off` como si fuese evidencia de mejora real: solo sería un experimento de diagnóstico del planificador.
