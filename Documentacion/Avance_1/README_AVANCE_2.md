# FleetLogix · Avance #2 — Análisis SQL y optimización de consultas

> **Estado:** ocho consultas seleccionadas y evaluadas; cinco índices creados y analizados en sus consultas principales; corrección lógica de la Query 9 validada. Pendientes las mediciones finales homogéneas de las ocho consultas y los entregables adicionales que exija la rúbrica.

Esta carpeta está preparada para **integrarse en el repositorio existente** de FleetLogix, sin sobrescribir el `README.md` ni los archivos del Avance #1. Incluye código SQL ejecutable, resultados recibidos de PostgreSQL, metodología de evaluación y capturas originales disponibles.

## Resumen comprobado

- Motor: **PostgreSQL 17**; cliente utilizado: **DBeaver**; base local: `fleetlogix_db`.
- Seis entidades: `vehicles`, `drivers`, `routes`, `trips`, `deliveries` y `maintenance`.
- **505.650** registros sintéticos (200 vehículos, 400 conductores, 50 rutas, 100.000 viajes, 400.000 entregas y 5.000 mantenimientos).
- Consultas estudiadas: **1, 2, 3, 4, 5, 7, 9 y 11** del archivo original de 12 consultas.
- **Query 9:** se corrigió la multiplicación de filas en un `JOIN` uno-a-muchos × uno-a-muchos, reduciendo el tiempo de **1.510,417 ms a 57,661 ms** en planes individuales; se trata de una *reescritura lógica*, no de una mejora atribuible a índices.
- **Query 11:** el índice `idx_trips_completed_month` fue **efectivamente utilizado** por PostgreSQL. La mediana (cinco pruebas antes y cinco después) descendió de **79,564 ms a 41,313 ms** (**−48,08 %**) y desapareció el ordenamiento inicial en disco.
- Otros cuatro índices no fueron utilizados por sus consultas analíticas generales; `idx_deliveries_trip_id` sí fue usado en una búsqueda selectiva (`trip_id = 1`).

## Dónde está cada elemento

| Ruta | Contenido |
|---|---|
| [`Documentacion/01_contexto_y_alcance.md`](Documentacion/01_contexto_y_alcance.md) | Modelo de datos, alcance, selección de consultas, limitaciones. |
| [`Documentacion/02_resultados_y_hallazgos.md`](Documentacion/02_resultados_y_hallazgos.md) | Hallazgos de las ocho queries, corrección de la Q9. |
| [`Documentacion/03_metodologia_y_benchmarks.md`](Documentacion/03_metodologia_y_benchmarks.md) | Metodología, mediciones reproducibles, índice por índice y cautelas. |
| [`Documentacion/04_decisiones_y_pendientes.md`](Documentacion/04_decisiones_y_pendientes.md) | Conclusiones, límites, decisiones y próximos pasos. |
| [`Documentacion/05_evidencias_y_trazabilidad.md`](Documentacion/05_evidencias_y_trazabilidad.md) | Índice de capturas y trazabilidad de mediciones. |
| [`Scripts/02_queries_analysis.sql`](Scripts/02_queries_analysis.sql) | **Archivo original completo** con las 12 queries; conservado intacto. |
| [`Scripts/03_8_queries_seleccionadas.sql`](Scripts/03_8_queries_seleccionadas.sql) | Las ocho queries seleccionadas, originales y sin cambios. |
| [`Scripts/04_explain_baselines.sql`](Scripts/04_explain_baselines.sql) | `EXPLAIN (ANALYZE, BUFFERS)` de las ocho queries originales. |
| [`Scripts/05_query9_corregida.sql`](Scripts/05_query9_corregida.sql) | Versión corregida de la Query 9. |
| [`Scripts/06_indices_avance2.sql`](Scripts/06_indices_avance2.sql) | DDL de los cinco índices experimentados. |
| [`Scripts/07_auditoria_avance2.sql`](Scripts/07_auditoria_avance2.sql) | Comprobaciones de integridad, inventario y consultas selectivas. |
| [`Scripts/08_benchmark_final.sql`](Scripts/08_benchmark_final.sql) | Reejecución final y homogénea de las ocho queries (pendiente). |
| [`Datos/`](Datos/) | Resultados en CSV y las diez mediciones de cada uno de los cuatro experimentos con 5+5. |
| [`Evidencias/`](Evidencias/) | Capturas aportadas y planes posteriores transcritos o extractados. |

## Uso seguro

1. Conectar DBeaver a `fleetlogix_db` y comprobar que las tablas ya contienen datos. **No** ejecutar de nuevo los scripts de carga del Avance #1 sobre la misma base.
2. Explorar las consultas de `03_8_queries_seleccionadas.sql` y verificar que se utiliza el esquema `public`.
3. Usar `05_query9_corregida.sql` para análisis correcto de mantenimiento; la Q9 original se conserva solamente como evidencia de diagnóstico.
4. Consultar `06_indices_avance2.sql` como histórico: **los cinco índices ya fueron creados** en el entorno estudiado. Ejecutarlo de nuevo solo si se prepara una base nueva de prueba.
5. Para completar el benchmark integral, seguir `03_metodologia_y_benchmarks.md` y `08_benchmark_final.sql`.

**Reproducibilidad:** las mediciones aquí documentadas fueron reportadas por el estudiante desde su PostgreSQL local. El paquete no afirma haber ejecutado ni validado remotamente el servidor. Las pruebas de `EXPLAIN ANALYZE` muestran tiempos de su equipo, no SLA ni rendimiento de producción.

**Seguridad del repositorio:** no subir `.env`, contraseñas, dumps con secretos, carpetas `.venv`, `__pycache__` ni información real de clientes. Los datos aquí descritos son sintéticos.
