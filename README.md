# FleetLogix | Proyecto Integrador — Módulo 2

**Ingeniería y análisis de datos para un caso de logística de última milla.**  
**Tecnologías:** PostgreSQL 17 · Python · SQL · DBeaver · Jupyter Notebook

FleetLogix es un proyecto académico que simula las operaciones de una empresa de transporte y entregas en **Bogotá, Medellín, Cali, Barranquilla y Cartagena**. Su propósito es diseñar una base de datos relacional, generar y validar datos consistentes, responder preguntas de negocio con SQL y medir el efecto de optimizaciones sobre consultas analíticas.

> **Nota sobre los datos:** todas las personas, vehículos, entregas, distancias y costos generados para este ejercicio son **sintéticos**. Los resultados ilustran técnicas de ingeniería y análisis de datos, no métricas reales de una empresa.

## Estado del proyecto

| Componente | Estado documentado |
|---|---|
| Modelo relacional en PostgreSQL (seis tablas y relaciones) | Completado |
| Generación, carga y validaciones de integridad | Completado · Avance #1 |
| Análisis de ocho consultas SQL seleccionadas | Completado · Avance #2 |
| Experimentos con cinco índices y `EXPLAIN (ANALYZE, BUFFERS)` | Completado · Avance #2 |
| Corrección de la consulta de mantenimiento por kilómetro | Completado · Query 9 |
| Benchmark final homogéneo de las ocho consultas y entregables adicionales de la rúbrica | Pendiente de cierre |

## Datos y modelo

La base de trabajo se denomina `fleetlogix_db` y utiliza el esquema `public`.

| Tabla | Filas | Función |
|---|---:|---|
| `vehicles` | 200 | Vehículos, capacidad y tipo |
| `drivers` | 400 | Conductores y licencias |
| `routes` | 50 | Origen, destino y distancia de las rutas |
| `trips` | 100.000 | Viajes, fechas, combustible y peso transportado |
| `deliveries` | 400.000 | Entregas relacionadas con los viajes |
| `maintenance` | 5.000 | Historial y costos de mantenimiento |
| **Total** | **505.650** | **Registros sintéticos** |

**Relaciones principales:** `vehicles → trips`, `drivers → trips`, `routes → trips`, `trips → deliveries` y `vehicles → maintenance` (relaciones uno a muchos). El modelo incorpora claves primarias, foráneas e índices básicos.

## Principales hallazgos

### Integridad y distribución

La carga masiva fue validada en el entorno local y las comprobaciones efectuadas no identificaron errores de integridad referencial ni inconsistencias en las reglas sintéticas evaluadas. La simulación establece **500 viajes por vehículo**, **250 por conductor** y **25 mantenimientos por vehículo**. Esta uniformidad limita el análisis comparativo de productividad.

### Query 9: corrección lógica antes de optimizar

La consulta original relacionaba simultáneamente los viajes y mantenimientos de cada vehículo antes de agregarlos. Esto generaba **2.500.000 filas intermedias**, con kilómetros y costos artificialmente multiplicados.

Se sustituyó por una consulta que **agrega viajes y mantenimientos por separado** y después combina los resultados. En dos planes registrados, el tiempo pasó de **1.510,417 ms a 57,661 ms** (reducción observada aproximada del **96,18 %**). Esta mejora corresponde a la **corrección del SQL**, no a la creación de un índice.

### Query 11: índice mensual usado por PostgreSQL

Se creó el índice parcial de expresión `idx_trips_completed_month` sobre `DATE_TRUNC('month', departure_datetime)` para viajes `completed`.

La mediana de cinco ejecuciones pasó de **79,564 ms a 41,313 ms** (**48,08 % menos**). El plan posterior confirmó un `Index Scan` usando ese índice y la eliminación del ordenamiento inicial en disco. Los otros cuatro índices experimentales **no fueron utilizados por sus consultas analíticas principales**; uno de ellos sí mostró utilidad en una búsqueda selectiva.

> Las cifras corresponden al entorno local y las pruebas registradas. No son una garantía de rendimiento en producción. Los detalles, cautelas metodológicas y resultados completos están en la documentación del Avance #2.

## Organización del repositorio

La estructura de referencia, respetando las carpetas existentes del proyecto, es:

```text
FleetLogix/
├── README.md                         # Presentación general (este archivo)
├── README_ETAPA4.md                  # Guía de generación, carga y validaciones
├── requirements.txt                  # Dependencias Python fijadas
├── Scripts/
│   ├── 00_create_schema.sql           # Esquema relacional para una base nueva
│   ├── 01_data_generation.py         # Datos maestros (archivo existente)
│   ├── 02_generate_transactions.py   # Viajes, entregas y mantenimientos
│   ├── 03_load_all.py                # Carga controlada a PostgreSQL
│   └── Avance_2/                     # Consultas, índices y auditorías SQL
├── Documentacion/
│   ├── ...                            # Documentos existentes del Avance #1
│   └── Avance_2/
│       ├── README_AVANCE_2.md
│       ├── 01_contexto_y_alcance.md
│       ├── 02_resultados_y_hallazgos.md
│       ├── 03_metodologia_y_benchmarks.md
│       ├── 04_decisiones_y_pendientes.md
│       ├── 05_evidencias_y_trazabilidad.md
│       ├── Datos/                       # CSV de resultados y benchmarking
│       └── Evidencias/                  # Capturas y planes de ejecución
├── Notebooks/                         # Cuadernos del proyecto, si están integrados
├── data/                              # CSV sintéticos generados localmente
└── logs/                              # Registros locales de ejecución
```

Las carpetas `data/` y `logs/` son salidas locales: no es necesario versionar archivos voluminosos ni datos sensibles para documentar el proyecto.

## Documentación y navegación

- [Generación, carga y validación — Etapa 4 / Avance #1](README_ETAPA4.md)
- [Índice técnico del Avance #2](Documentacion/Avance_2/README_AVANCE_2.md)
- [Resultados y hallazgos de las ocho consultas](Documentacion/Avance_2/02_resultados_y_hallazgos.md)
- [Metodología y mediciones de rendimiento](Documentacion/Avance_2/03_metodologia_y_benchmarks.md)
- [Decisiones técnicas y trabajo pendiente](Documentacion/Avance_2/04_decisiones_y_pendientes.md)

## Requisitos y uso responsable

**Entorno utilizado:** PostgreSQL 17, Python 3.14 en el equipo de trabajo y DBeaver. Las versiones validadas de las dependencias de scripts y notebook están fijadas en [`requirements.txt`](requirements.txt).

Para ejecutar una instalación nueva, revisar primero [README_ETAPA4.md](README_ETAPA4.md). **No volver a cargar CSV en la base ya poblada**: el cargador está diseñado para una carga controlada sobre tablas vacías.

Para analizar SQL y los resultados del Avance #2, consultar [su guía principal](Documentacion/Avance_2/README_AVANCE_2.md). Los scripts de índices se conservan como evidencia del experimento y **no deben reejecutarse innecesariamente** sobre la base actual.

**Seguridad:** mantener `.env`, contraseñas, entornos virtuales, respaldos privados y datos reales fuera del control de versiones. Se recomienda revisar `git status` antes de cualquier `git add`.

## Próximos pasos

1. Ejecutar un benchmark final homogéneo de las ocho consultas en el estado final de índices.
2. Completar las capturas posteriores y los datos de trazabilidad aún pendientes.
3. Finalizar los cuadernos, visualizaciones y demás entregables exigidos por la rúbrica académica.

---

*Proyecto Integrador de Data Science · Módulo 2 · Actualización documental: noviembre de 2026.*
