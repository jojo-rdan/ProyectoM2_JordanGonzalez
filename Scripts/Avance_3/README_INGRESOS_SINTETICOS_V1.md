# FleetLogix — SYNTHETIC_REVENUE_V1 (Avance 3)

## Naturaleza de las métricas

`ESTIMATED_REVENUE_COP` representa un **ingreso simulado académico**, **no facturación observada, tarifa oficial ni ingreso contable**. PostgreSQL no contiene una tarifa de entrega. Los parámetros se eligieron para probar la trazabilidad, consistencia y consultas de un Data Warehouse dimensional sobre datos sintéticos, no como cotización del mercado.

## Política aprobada para la simulación

Por entrega completada:

```
ESTIMATED_REVENUE_COP = ROUND(7000 + 20 * PACKAGE_WEIGHT_KG
                            + 300 * ALLOCATED_DISTANCE_KM, 2)
REVENUE_POLICY_VERSION = 'SYNTHETIC_REVENUE_V1'
```

- `7000` COP: tarifa base sintética.
- `20` COP/kg: componente por peso sintético.
- `300` COP/km: componente por distancia asignada sintético.
- `PACKAGE_WEIGHT_KG`: peso operativo almacenado con tres decimales.
- `ALLOCATED_DISTANCE_KM`: distancia del viaje ya repartida proporcionalmente según el peso, con seis decimales.
- Redondeo por fila: `ROUND_HALF_UP` en Python, equivalente a `ROUND(...,2)` en Snowflake para estos valores no negativos de punto fijo.
- Sin topes o truncamiento: las entregas atípicas se conservan; NO se interpretan como una política tarifaria real.

## Línea base de referencia (consulta de simulación SQL)

400.000 entregas, mínimo 7.005,71 COP, promedio 15.677,13 COP, mediana 10.810,37 COP, P95 39.595,33 COP, máximo 341.566,12 COP, total **6.270.850.032,24 COP**. 2.751 entregas >100.000 COP; 45 entregas >250.000 COP; 0 nulos. Son cifras de referencia calculadas sobre la línea base de 400.000 hechos de FleetLogix, no valores universales.

## Trazabilidad e idempotencia

Los archivos modificados son:

- `07_extract_transform_fact_deliveries.py`: aplica la fórmula a cada entrega al crear el CSV preparado, calcula el `SOURCE_ROW_HASH` a partir de todos los campos transformados (incluyendo ingresos y versión) y registra una auditoría con la política y el total.
- `08_load_fact_deliveries.py`: verifica localmente que la fórmula, el hash, el total y la política coinciden; valida los importes en Snowflake antes y después del `MERGE`, dentro de una transacción.
- `12_validate_revenue_policy.sql`: consulta de validación en Snowsight, solo lectura.

En la **primera carga de política**, se esperan aproximadamente 400.000 `UPDATE` por hash cambiado y ninguna inserción, porque los hechos ya existen. En la **segunda ejecución con los mismos datos**, se esperan cero inserciones y cero actualizaciones.

**IMPORTANTE:** reemplazar **ambos** scripts 07 y 08 juntos; **no ejecutar el script 08 anterior** (que exigía que los ingresos fueran nulos) con el nuevo CSV. No usar el transformador antiguo una vez aplicada la política. Se recomienda conservar el ZIP anterior como respaldo de los scripts de la etapa sin ingresos.

## Ejecución, desde la raíz del proyecto

```powershell
python Scripts/Avance_3/07_extract_transform_fact_deliveries.py
python Scripts/Avance_3/08_load_fact_deliveries.py
python Scripts/Avance_3/08_load_fact_deliveries.py --execute
```

Tras `CARGA CONFIRMADA (COMMIT)`, abrir `12_validate_revenue_policy.sql` y ejecutar sus dos consultas. Por último, repetir `python Scripts/Avance_3/08_load_fact_deliveries.py --execute` sin regenerar ni modificar el CSV para la prueba de idempotencia.

La autenticación OAuth por navegador requiere intervención humana. La automatización nocturna posterior necesitará autenticación de servicio, permisos mínimos y una arquitectura incremental. Las constantes de recuento y total de este script pertenecen a la **línea base académica**; antes de usarlo con nuevas entregas, sustituirlas por validaciones dinámicas e incrementales.

## Protección de datos

El CSV intermedio contiene identificadores de entregas y datos derivados de clientes. Mantener `data/staging/avance_3/` ignorada por Git y controlar el acceso a los archivos locales.
