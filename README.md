# FleetLogix — Proyecto Integrador · Módulo 2

**Pipeline de datos logísticos, análisis SQL, Data Warehouse y arquitectura AWS.**  
Proyecto académico con **datos sintéticos**. Los servicios AWS del Avance #4 están **diseñados y simulados localmente, no desplegados**.

## Resumen de los cuatro avances

| Avance | Entregable | Resultado / alcance |
|---|---|---|
| **#1 — PostgreSQL** | Modelo relacional, generación y carga de datos | 6 tablas; **505.650 registros** sintéticos, integridad validada |
| **#2 — SQL y rendimiento** | Consultas, EXPLAIN ANALYZE y optimización | 8 consultas analizadas, 5 índices evaluados y corrección de Query 9 |
| **#3 — Snowflake DWH** | Modelo estrella, ETL Python, SCD2 y auditoría | **400.000 hechos**, 6 dimensiones, conciliaciones e idempotencia validadas |
| **#4 — AWS Cloud** | Arquitectura, diagrama, 4 Lambda y monitoreo | **Diseño + demostración local**, sin infraestructura desplegada |

**Resultados DWH reportados y validados en el entorno académico:** 100.000 viajes, 400.000 entregas; **4.701.486,980 km** y **633.064,820 L** asignados sin duplicar métricas; **6.270.850.032,24 COP de ingresos sintéticos**, calculados con `SYNTHETIC_REVENUE_V1`. **No representan facturación real.**

## Acceso directo a las entregas

| Etapa | Documentación | Código / cuaderno |
|---|---|---|
| 1 | [Informe del Avance #1](Documentacion/Avance_1/Informe_Avance_1_FleetLogix.pdf) · [Guía de carga](README_ETAPA4.md) | [Scripts PostgreSQL](Scripts/) · [Notebook generación](Notebooks/Avance_1_DataGeneration.ipynb) |
| 2 | [Índice y evidencias](Documentacion/Avance_2/README_AVANCE_2.md) | [Consultas y benchmarks](Scripts/Avance_2/) |
| 3 | [Cierre técnico y limitaciones](Documentacion/Avance_3/README_CIERRE.md) | [ETL y SQL](Scripts/Avance_3/) · [Notebook DWH](Notebooks/Avance_3_DataWarehouse.ipynb) |
| 4 | [PDF arquitectura AWS](Documentacion/Avance_4/ARQUITECTURA_TECNICA.pdf) · [Matriz de requisitos](Documentacion/Avance_4/MATRIZ_REQUISITOS.md) | [Diagrama editable](Documentacion/Avance_4/arquitectura_aws.drawio) · [Lambda](Scripts/Avance_4/lambda_functions/) · [Notebook Cloud](Notebooks/Avance_4_CloudArchitecture.ipynb) |

**Diagrama del Avance #4:** [PNG](Documentacion/Avance_4/arquitectura_aws.png) · [Descripción técnica editable](Documentacion/Avance_4/ARQUITECTURA_TECNICA.md).  
**API de ejemplo:** [Colección Postman](Postman/FleetLogix_API.postman_collection.json).

## Estructura del repositorio

```text
.
├── Scripts/
│   ├── 00_create_schema.sql          # Esquema PostgreSQL del Avance 1
│   ├── 01_data_generation.py
│   ├── 02_generate_transactions.py
│   ├── 03_load_all.py
│   ├── Avance_2/                    # Análisis, índices y benchmarks
│   ├── Avance_3/                    # Transformaciones, cargas, auditoría y vistas
│   └── Avance_4/                    # 4 handlers Lambda y prueba local
├── Documentacion/
│   ├── Avance_1/
│   ├── Avance_2/
│   ├── Avance_3/
│   └── Avance_4/                    # PDF, diagrama y presupuesto AWS
├── Notebooks/
├── Postman/
├── Evidencias/                      # Capturas históricas
├── .env.example
├── requirements.txt
├── requirements-cloud.txt
└── README.md
```

Los directorios locales `data/`, `logs/` y `.venv/` están ignorados en Git; se generan en el equipo durante las ejecuciones.

## Uso y validación rápida

**Entorno de referencia:** Python 3.14, PostgreSQL 17, DBeaver y Snowflake. Para una instalación local nueva:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Para trabajar con Snowflake o con los SDK de AWS, instalar también las dependencias opcionales:

```powershell
python -m pip install -r requirements-cloud.txt
```

Copiar `.env.example` a `.env` y completar **solo en el equipo local** las variables de PostgreSQL y Snowflake. La autenticación Snowflake actual para las pruebas manuales se realiza por **OAuth en navegador**; los scripts no están preparados para una ejecución nocturna desatendida.

**Prueba local del Avance #4 (no requiere AWS):**

```powershell
python Scripts/Avance_4/test_lambda_logic.py
```

Resultado esperado: `PRUEBA LOCAL AWS COMPLETA: OK`. Simula evento recibido, estado actual, ETA, alerta, archivo histórico y evento duplicado.

**Consultas finales del Avance #3 en Snowsight:**

1. `Scripts/Avance_3/16_finalize_analytics.sql` — crea vistas seguras y snapshots agregados.
2. `Scripts/Avance_3/18_validacion_cierre.sql` — verifica hechos, agregados y vistas.

Estos dos SQL forman parte del paquete de cierre, pero **su ejecución sobre la cuenta real no está confirmada en las evidencias compartidas**. No los presentes como ejecutados sin revisar sus resultados. Los roles de SALES/OPERATIONS son opcionales y requieren administración: `17_roles_opcionales.sql`.

**Precaución:** `python Scripts/Avance_3/10_run_etl_pipeline.py --full` realiza una **recarga completa** y puede solicitar inicio de sesión Google repetidamente; no es CDC ni un job desatendido. El procedimiento de carga del Avance #1 debe usarse solamente en una base PostgreSQL vacía.

## Alcance y limitaciones para la entrega

- **Avance #3:** pipeline manual auditado (9/9 pasos), SCD2 e idempotencia validados. El detector de deltas identificó correctamente el caso sin cambios; el MERGE de delta no vacío **no ha sido probado en integración aislada**, y la extracción desde PostgreSQL sigue siendo completa. No se configuró programación nocturna ni autenticación de servicio. La retención Snowflake se configuró en **1 día**, no 30.
- **Avance #4:** RDS PostgreSQL, DynamoDB, S3, API Gateway, Lambda, EventBridge, SNS, IAM y CloudWatch son un **diseño propuesto**, con una prueba local de cuatro funciones Lambda. **No hay migración real a RDS, API pública, backups activados ni servicios AWS desplegados**.
- **Costo AWS:** **US$23,10/mes** en un escenario teórico pequeño de Ohio, condicionado al volumen y a las hipótesis documentadas; no es una factura ni una cotización garantizada. Consultar el [presupuesto](Documentacion/Avance_4/presupuesto_aws.csv).
- **Seguridad:** no publicar contraseñas, `.env`, archivos de clientes/direcciones ni claves privadas. Todo el conjunto de datos operacional es sintético.

---

*Proyecto Integrador de Data Science · Módulo 2 · Estado documental: 18 de noviembre de 2026.*
