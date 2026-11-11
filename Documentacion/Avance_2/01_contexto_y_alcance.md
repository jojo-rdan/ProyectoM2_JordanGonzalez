# 1. Contexto, alcance y modelo de datos

## Objetivo del Avance #2

Evaluar ocho consultas SQL entregadas para el caso FleetLogix, interpretar resultados de negocio y planes de ejecución, proponer cinco índices, contrastar sus efectos y documentar la corrección de una consulta con agregaciones incorrectas. El foco es **corrección analítica + desempeño medible**, no únicamente reducir milisegundos.

## Herramientas y origen

| Elemento | Contexto |
|---|---|
| DBMS | PostgreSQL 17, instancia local |
| Base | `fleetlogix_db`, esquema `public` |
| Cliente | DBeaver |
| Generación de datos | Scripts del Avance #1; datos de naturaleza sintética |
| Fuente de SQL original | `../../Scripts/Avance_2/02_queries_analysis.sql` aportado al proyecto |
| Evidencias | Capturas y `EXPLAIN (ANALYZE, BUFFERS)` obtenidos por el estudiante |

### Población sintética

| Entidad | Registros | Propósito |
|---|---:|---|
| `vehicles` | 200 | Flota y características del vehículo |
| `drivers` | 400 | Conductores y vigencia de licencias |
| `routes` | 50 | Rutas, ciudad origen/destino y distancia |
| `trips` | 100.000 | Viajes con conductor, vehículo, ruta, fechas, combustible, peso y estado |
| `deliveries` | 400.000 | Entregas asociadas a cada viaje |
| `maintenance` | 5.000 | Mantenimientos y costos por vehículo |
| **Total** | **505.650** | |

Relaciones principales: `vehicles (1) → (N) trips`, `drivers (1) → (N) trips`, `routes (1) → (N) trips`, `trips (1) → (N) deliveries` y `vehicles (1) → (N) maintenance`. Véase DDL del Avance #1, `fleetlogix_db_schema.sql`.

El generador establece 500 viajes por vehículo, 250 viajes por conductor y 25 mantenimientos por vehículo. Los 100.000 viajes examinados tienen estado `completed`. Este diseño produce métricas uniformes en algunas consultas y **no equivale a datos observados de una empresa real**.

La ventana temporal de los viajes reportada durante la ejecución va aproximadamente de octubre de 2024 a octubre de 2026; el último viaje registrado en las evidencias es de octubre de 2026. **No confundir cobertura del dataset con la fecha actual del servidor.**

## Consultas incluidas

| N.º | Nivel | Pregunta de negocio | Principales operaciones |
|---|---|---|---|
| 1 | Básica | ¿Cómo está compuesta la flota? | `GROUP BY`, `COUNT` |
| 2 | Básica | ¿Qué licencias vencen pronto? | Filtro temporal, `ORDER BY` |
| 3 | Básica | ¿Cuántos viajes hay por estado? | `GROUP BY`, `COUNT` |
| 4 | Intermedia | ¿Qué demanda existe por ciudad destino en 60 días? | Tres tablas, `COUNT(DISTINCT)`, `SUM` |
| 5 | Intermedia | ¿Cuál es la carga de trabajo por conductor activo? | `LEFT JOIN`, `HAVING`, agregación |
| 7 | Intermedia | ¿Qué rutas consumen más litros cada 100 km? | `AVG`, `NULLIF`, `HAVING`, `LIMIT` |
| 9 | Compleja | ¿Cuál es el costo de mantenimiento por km según vehículo? | CTE, múltiples `JOIN`, agregados; **requiere corrección lógica** |
| 11 | Compleja | ¿Cómo evolucionan los viajes mes a mes? | `DATE_TRUNC`, `LAG`, `LEAD`, promedio móvil |

Se seleccionaron **1,2,3,4,5,9**, la **7** del bloque 6/7/8, y la **11** del bloque 10/11/12. Las otras consultas están disponibles en el SQL original pero no forman parte de este experimento.

## Limitaciones importantes

- `CURRENT_DATE` hace que las consultas 2 y 4 **dependan de la fecha de ejecución**. Registrar la fecha junto con cada benchmark o congelar una fecha en una copia de prueba, sin modificar silenciosamente el SQL original.
- La Query 2 original utiliza `< CURRENT_DATE + INTERVAL '30 days'` y puede incluir licencias ya vencidas, no solo las próximas. En las observaciones compartidas devolvió **cero filas**.
- La Query 3 arroja exclusivamente `completed` debido a la generación sintética; no indica que una empresa real tenga 100 % de viajes completados.
- La Query 5 devuelve 400 conductores, todos con 250 viajes completados; **no permite discriminar productividad entre ellos** en esta muestra.
- La Query 7 no controla tipo de vehículo, peso, topografía ni tráfico; **consumo alto no demuestra ineficiencia**.
- La Query 9 original es **numéricamente incorrecta** por multiplicación de filas; las decisiones deben basarse en su versión corregida.
- La Query 11 muestra octubre de 2026 incompleto, con 2.496 viajes; **la caída mensual de 40,06 % no demuestra menor demanda**. `LEAD()` recupera datos del mes siguiente que ya existe, no predice el futuro.
