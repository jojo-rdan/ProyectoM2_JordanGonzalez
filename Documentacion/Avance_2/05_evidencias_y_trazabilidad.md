# 5. Evidencias, integridad y trazabilidad

## Origen de las pruebas

Las capturas fueron aportadas por el estudiante y están copiadas **sin edición** desde los adjuntos originales. Los planes posteriores en `Evidencias/planes_posteriores/` son transcripciones o **extractos identificados como tales** de los textos compartidos; no son exportaciones automáticas del servidor.

## Evidencias visuales efectivamente disponibles

| Query | Resultados | Plan previo |
|---|---|---|
| 1 | [Composición](Evidencias/antes/01_composicion_flota.png) | [EXPLAIN](Evidencias/antes/01_explain_antes.png) |
| 2 | [Licencias](Evidencias/antes/02_licencias_vencimiento.png) | [EXPLAIN](Evidencias/antes/02_explain_antes.png) |
| 3 | [Estados](Evidencias/antes/03_viajes_por_estado.png) | [EXPLAIN](Evidencias/antes/03_explain_antes.png) |
| 4 | [Ciudades](Evidencias/antes/04_entregas_por_ciudad.png) | [EXPLAIN](Evidencias/antes/04_explain_antes.png) |
| 5 | [Conductores](Evidencias/antes/05_productividad_conductores.png) | [EXPLAIN](Evidencias/antes/05_explain_antes.png) |
| 7 | [Rutas](Evidencias/antes/07_consumo_combustible_rutas.png) | [EXPLAIN](Evidencias/antes/07_explain_antes.png) |
| 9 | [Original](Evidencias/antes/09_costos_mantenimiento_original.png), [corregida](Evidencias/antes/09_costos_mantenimiento_corregida.png) | [Original](Evidencias/antes/09_explain_antes.png), [corregida](Evidencias/antes/09_explain_corregida.png) |
| 11 | [Tendencias](Evidencias/antes/11_tendencias_mensuales.png) | [EXPLAIN](Evidencias/antes/11_explain_antes.png) |

**Índices posteriores:** consultar [planes textuales/extractos](Evidencias/planes_posteriores/) y [`Datos/benchmarks_5_indices_repeticiones.csv`](Datos/benchmarks_5_indices_repeticiones.csv). También están disponibles las capturas del [plan posterior de Q4](Evidencias/planes_posteriores/04_explain_despues_indice.png), la [búsqueda selectiva por `trip_id`](Evidencias/planes_posteriores/04_indice_busqueda_selectiva.png) y el [plan posterior de Q11](Evidencias/planes_posteriores/11_explain_despues_indice.png).

## Valores cuyo origen debe mantenerse diferenciado

| Dato | Origen | Alcance |
|---|---|---|
| Baselines de las ocho queries | Capturas y texto de planes iniciales | Una ejecución histórica por query, con posible variación entre capturas y texto |
| Resultados Q4, Q7, Q9, Q11 | Salidas SQL pegadas por el estudiante | Datos puntuales del momento de ejecución |
| Diez tiempos para Q5, Q7, Q9 y Q11 | Cinco `Execution Time` antes y cinco después | Comparación pareada temporal (no necesariamente carga perfectamente controlada) |
| Q4 — índice 1 | Una ejecución previa y cinco posteriores | Comparación descriptiva, no 5 vs 5 |
| Prueba `trip_id = 1` | Plan textual pegado por el estudiante | Confirma `Index Scan` con cuatro filas; no hay versión sin índice |
| Plan final Q11 | Texto completo pegado por el estudiante | Confirma `Index Scan using idx_trips_completed_month` |

## Archivos adicionales sugeridos antes de entrega

- `Evidencias/despues/05_explain_despues_indice.png`
- `Evidencias/despues/07_explain_despues_indice.png`
- `Evidencias/despues/09_explain_despues_indice.png`

Estos tres archivos pendientes **no se incluyen** porque no fueron suministrados como capturas. No reemplazar evidencias ausentes con imágenes fabricadas.
