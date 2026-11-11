# 2. Resultados analíticos y hallazgos de negocio

Los valores se transcribieron de las salidas de PostgreSQL compartidas en la conversación del proyecto. Son observaciones del conjunto sintético, no hechos empresariales externos. Los CSV originales disponibles están en `../Datos/`.

## Query 1 — Composición de flota

| Tipo | Vehículos |
|---|---:|
| Van | 80 |
| Motocicleta | 60 |
| Camión Mediano | 40 |
| Camión Grande | 20 |
| **Total** | **200** |

**Lectura:** predominan las vans (40 %), seguidas de motocicletas (30 %). El plan inicial registró **0,140 ms** y utilizó lectura secuencial de una tabla pequeña.

![Query 1](../Evidencias/antes/01_composicion_flota.png)

## Query 2 — Licencias con vencimiento previo a fecha de corte

**Resultado:** cero conductores para el filtro original, al momento de la ejecución. **Tiempo inicial: 0,131 ms.** No equivale a afirmar que una alerta futura no será necesaria. La condición `< CURRENT_DATE + INTERVAL '30 days'` incluye vencidas y vence-pronto; depende del reloj del servidor.

![Query 2](../Evidencias/antes/02_licencias_vencimiento.png)

## Query 3 — Viajes por estado

| Estado | Viajes |
|---|---:|
| `completed` | 100.000 |

**Tiempo inicial: 30,702 ms.** No se identifican estados alternativos porque el generador cargó todos los viajes como completados. La medición individual registrada en una captura diferente fue distinta, por variabilidad entre ejecuciones.

![Query 3](../Evidencias/antes/03_viajes_por_estado.png)

## Query 4 — Entregas por ciudad destino (últimos 60 días, según fecha de ejecución)

| Ciudad | Viajes | Entregas | Peso (kg) |
|---|---:|---:|---:|
| Cartagena | 1.209 | 4.860 | 1.122.201,78 |
| Barranquilla | 1.162 | 4.625 | 976.101,35 |
| Cali | 1.056 | 4.236 | 1.371.262,09 |
| Bogotá | 1.044 | 4.160 | 1.131.822,40 |
| Medellín | 929 | 3.748 | 990.884,70 |
| **Total** | **5.400** | **21.629** | **5.592.272,32** |

**Lectura:** Cartagena concentró la mayor cantidad de entregas; Cali, el mayor peso transportado. Línea base individual: **115,901 ms**. El plan filtra `trips` con `idx_trips_departure`, lee `deliveries` en paralelo y combina mediante hash join. Los números variarán con `CURRENT_DATE`.

![Query 4](../Evidencias/antes/04_entregas_por_ciudad.png)

## Query 5 — Productividad de conductores

**Resultado:** 400 conductores activos con 250 viajes totales y 250 completados por conductor; **100.000 viajes**. Línea base individual: **44,092 ms**. Las filas presentan empate en orden descendente por viajes completados; el `ORDER BY` no establece un desempate determinista. No utilizar la homogeneidad sintética para evaluar desempeño real.

![Query 5](../Evidencias/antes/05_productividad_conductores.png)

## Query 7 — Consumo de combustible por ruta

| Código | Ruta | Viajes | L/100 km |
|---|---|---:|---:|
| INT-01-02 | Bogotá → Medellín | 183 | 14,39 |
| INT-05-01 | Cartagena → Bogotá | 152 | 14,35 |
| INT-04-01 | Barranquilla → Bogotá | 189 | 14,13 |
| LOC-03-04 | Cali → Cali | 3.280 | 13,98 |
| LOC-05-02 | Cartagena → Cartagena | 3.110 | 13,91 |
| LOC-01-06 | Bogotá → Bogotá | 3.350 | 13,89 |
| INT-05-03 | Cartagena → Cali | 176 | 13,86 |
| LOC-03-05 | Cali → Cali | 3.245 | 13,81 |
| LOC-05-01 | Cartagena → Cartagena | 3.146 | 13,80 |
| INT-01-05 | Bogotá → Cartagena | 165 | 13,79 |

**Lectura:** Bogotá → Medellín encabeza la métrica relativa. El volumen de combustible total no equivale a rendimiento por 100 km. No inferir ineficiencia sin controlar la composición de flota. Línea base individual: **91,673 ms**. El plan agrupa 100.000 viajes en 50 rutas.

![Query 7](../Evidencias/antes/07_consumo_combustible_rutas.png)

## Query 9 — Costos de mantenimiento por km: defecto y corrección

**Defecto:** cada vehículo tiene 500 viajes y 25 mantenimientos. La unión directa de ambas tablas por vehículo produce 500 × 25 = **12.500 filas por vehículo**, o **2.500.000** filas en total.

- `COUNT(DISTINCT trip_id)` se mantiene correcto.
- `SUM(distance_km)` se repite **25 veces**.
- `SUM(maintenance.cost)` se repite **500 veces**.
- `costo_por_km` se multiplica aproximadamente por **20**.
- `costo_promedio_por_mantenimiento` se multiplica por **500**.

**Corrección implementada:** CTE `viajes_por_vehiculo` y CTE `mantenimiento_por_vehiculo` calculan sus métricas **por separado**, antes de relacionarlas con `vehicles`. Código en [`05_query9_corregida.sql`](../Scripts/05_query9_corregida.sql).

| Tipo | Vehículos | Viajes | Km corregidos | Costo manten. corregido | Costo/km | Costo/mantenimiento |
|---|---:|---:|---:|---:|---:|---:|
| Van | 80 | 40.000 | 1.842.566,63 | 1.173.019.417,75 | 636,62 | 586.509,71 |
| Camión Mediano | 40 | 20.000 | 938.317,36 | 587.655.609,52 | 626,29 | 587.655,61 |
| Motocicleta | 60 | 30.000 | 1.425.888,46 | 879.484.905,06 | 616,80 | 586.323,27 |
| Camión Grande | 20 | 10.000 | 494.714,53 | 291.983.285,15 | 590,21 | 583.966,57 |

**Rendimiento registrado (planes individuales):** original **1.510,417 ms**, corregida **57,661 ms**; reducción de **96,18 %**, factor aproximado **26,2×**. Es una mejora por *corrección lógica / reescritura*, **no por indexación**.

![Query 9 original](../Evidencias/antes/09_costos_mantenimiento_original.png)

![Query 9 corregida](../Evidencias/antes/09_costos_mantenimiento_corregida.png)

## Query 11 — Tendencias mensuales

La consulta agrupa los 100.000 viajes en **25 períodos mensuales**; presenta los 12 más recientes y calcula `LAG`, `LEAD`, variación porcentual y promedio móvil de tres meses.

| Mes | Viajes | Variación frente a anterior |
|---|---:|---:|
| 2026-10 | 2.496 | −40,06 % |
| 2026-09 | 4.164 | −3,34 % |
| 2026-08 | 4.308 | +0,19 % |
| 2026-07 | 4.300 | +3,49 % |
| 2026-06 | 4.155 | −3,62 % |
| 2026-05 | 4.311 | +3,23 % |
| 2026-04 | 4.176 | −2,75 % |
| 2026-03 | 4.294 | +9,96 % |
| 2026-02 | 3.905 | −9,00 % |
| 2026-01 | 4.291 | −0,97 % |
| 2025-12 | 4.333 | +4,38 % |
| 2025-11 | 4.151 | −3,71 % |

**Cautelas:** octubre de 2026 es parcial y febrero tiene menos días; para comparar demanda real, calcular tasas normalizadas por día operativo. `LEAD` no es una predicción. Línea base individual: **102,155 ms**. El índice mensual redujo el tiempo mediano de cinco pruebas de **79,564 ms a 41,313 ms** y eliminó el ordenamiento inicial en disco.

![Query 11](../Evidencias/antes/11_tendencias_mensuales.png)
