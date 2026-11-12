# 4. Decisiones técnicas, riesgos y trabajos pendientes

## Decisiones sustentadas por evidencia

1. **Usar Query 9 corregida** en cualquier análisis de mantenimiento. La original solo se conserva como diagnóstico. Su `JOIN` multiplica kilómetros ×25 y costos ×500 y crea métricas artificiales. La reescritura fue simultáneamente más correcta y mucho más rápida.
2. **Conservar provisionalmente `idx_trips_completed_month`** para esta carga analítica: fue usado, eliminó un ordenamiento en disco y mostró mediana 48,08 % inferior. Revisar impacto en otras consultas y costo de mantenimiento en escrituras antes de pasar a producción.
3. **No atribuir reducción a los cuatro índices no utilizados** en sus queries principales. La mediana menor en algunos casos es solo una observación, no evidencia de causalidad.
4. **Conservar temporalmente el índice de `deliveries.trip_id` durante validación funcional**: uso confirmado para búsqueda de cuatro entregas (`trip_id=1`). Medir frecuencias operativas, espacio, escrituras e índice usado antes de una decisión definitiva.
5. **Reevaluar `idx_trips_driver_id`, `idx_trips_route_id`, `idx_trips_vehicle_id`** en un entorno de prueba: no mejoraron de modo demostrable sus consultas globales. No crear índices adicionales por defecto.

## Riesgos de interpretación

- Los datos son sintéticos y tienen distribución homogénea por conductor/vehículo; no son adecuados para decisiones reales de personal o mantenimiento.
- Los cuatro tipos de vehículo se comparan en consumo y mantenimiento sin controlar severidad de uso; evitar inferencias causales.
- `CURRENT_DATE` y la ventana temporal variable de la Query 4 impiden resultados idénticos en días distintos.
- Octubre de 2026 es parcial y no puede compararse directamente con meses completos.
- Los resultados de base y planes fueron reportados por el estudiante; no se dispone de telemetría del host ni observación directa del servidor desde este paquete.
- La Query 11 todavía estima decenas de miles de grupos donde el plan real obtiene 25; puede evaluarse la estadística de expresiones, pero cambiarla podría afectar comparabilidad.
- `CREATE INDEX` y `ANALYZE` impactan estadísticas, almacenamiento y escrituras. Evaluar la retención de índices bajo patrones de uso reales.

## Pendientes — para declarar cierre total del Avance #2

- [ ] **Benchmark final homogéneo de las ocho consultas** con cinco ejecuciones por query en el mismo estado final de índices; registrar fecha/configuración y Q9 corregida. Las primeras mediciones ya documentadas no suplen esta prueba.
- [ ] Completar las capturas finales posteriores de Q5, Q7 y Q9. Ya se conservaron capturas posteriores para Q4, su búsqueda selectiva y Q11; los demás planes posteriores solo están disponibles como texto.
- [ ] Verificar la prueba selectiva `WHERE driver_id = 384`, sugerida para el segundo índice; no hay resultado documentado.
- [ ] Decidir de manera justificada qué índices conservar/retirar **en copia de prueba**; no tocar prematuramente la base original.
- [ ] Revisar la rúbrica académica para verificar notebook, visualizaciones, entrega y formato exigidos; este paquete se limita a **documentación técnica, SQL y evidencias disponibles**.
- [ ] Completar captura de versión de PostgreSQL, parámetros de entorno y hora de experimentos para reproducibilidad.

## Convenciones de seguridad y despliegue

No subir `.env`, credenciales, archivos de respaldo con información sensible ni datasets reales. Los scripts `02`, `03`, `04`, `05`, `07` y `08` son de solo lectura si se ejecutan como se documenta; `06_indices_avance2.sql` contiene DDL y `ANALYZE`, no debe ejecutarse en producción sin evaluación de impacto.
