# FleetLogix | Generación, carga y validación de datos

**Etapa 4 — Avance #1 (documentación actualizada)**

Este documento describe el flujo de **generación de datos sintéticos, carga controlada y validación** de FleetLogix. Sustituye las instrucciones anteriores que trataban la carga como una tarea pendiente: **la carga y sus validaciones ya se realizaron en el entorno local del proyecto**.

> Los comandos se presentan para **reproducir el proceso en una base nueva y vacía**, no para repetir la carga sobre `fleetlogix_db` ya poblada. No se ejecutó ninguna carga al actualizar esta documentación.

## 1. Entorno y requisitos

- Base de datos: **PostgreSQL 17**, `fleetlogix_db`, esquema `public`.
- Herramientas de trabajo: **Python 3.14** en el equipo del proyecto (scripts declarados para Python 3.10+), **DBeaver** y Jupyter Notebook.
- Bibliotecas del flujo Python: `faker`, `pandas`, `numpy`, `psycopg2-binary`, `python-dotenv`.
- Estructura de referencia: scripts en `Scripts/`, resultados locales en `data/` y logs en `logs/`.

Ejemplo de preparación **en un entorno nuevo**, desde la raíz del repositorio (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install faker pandas numpy psycopg2-binary python-dotenv
```

La instalación anterior es una referencia de dependencias conocidas; si el repositorio incluye un archivo `requirements.txt` actualizado, utilizarlo como fuente principal.

## 2. Flujo de trabajo reproducible

### 2.1. Esquema relacional

Crear previamente las seis tablas a partir del DDL del proyecto, con sus claves primarias, foráneas y restricciones. **No volver a ejecutar `CREATE TABLE` sobre las tablas existentes**. El esquema contiene:

| Tabla | Filas validadas | Descripción |
|---|---:|---|
| `vehicles` | 200 | Flota |
| `drivers` | 400 | Personal conductor |
| `routes` | 50 | Rutas predefinidas |
| `trips` | 100.000 | Viajes |
| `deliveries` | 400.000 | Entregas |
| `maintenance` | 5.000 | Mantenimientos |
| **Total** | **505.650** | |

### 2.2. Generación sintética

En una **instalación de prueba nueva**, con la terminal ubicada en la raíz del proyecto:

```powershell
python Scripts/01_data_generation.py
python Scripts/02_generate_transactions.py
```

El primer script genera los archivos maestros y el segundo construye viajes, entregas y mantenimientos. Las salidas son:

```text
data/vehicles.csv
data/drivers.csv
data/routes.csv
data/trips.csv
data/deliveries.csv
data/maintenance.csv
```

**Estos dos comandos no insertan datos en PostgreSQL.** Si ya existen los CSV generados y validados, no es necesario repetirlos.

### 2.3. Configuración segura

Crear un `.env` local tomando como referencia `.env.example`:

```dotenv
PGHOST=localhost
PGPORT=5432
PGDATABASE=fleetlogix_db
PGUSER=postgres
PGPASSWORD=REEMPLAZAR_LOCALMENTE
```

**Nunca publicar `.env` ni credenciales reales**. El archivo `.env.example` debe contener únicamente valores de ejemplo.

### 2.4. Carga a PostgreSQL (solo en una base nueva)

El cargador del proyecto se invoca explícitamente mediante:

```powershell
python Scripts/03_load_all.py --load
```

**Seguridades documentadas del cargador:**

- Aborta si alguna de las tablas de destino ya contiene filas.
- Utiliza `COPY` dentro de una única transacción.
- Asigna identificadores deterministas a los registros maestros y mantiene las referencias entre CSV.
- Ajusta las secuencias de las columnas `SERIAL` después de insertar.
- No elimina tablas ni reemplaza los datos existentes como paso normal.

**No ejecutar este comando sobre la base actual poblada.** Para hacer una prueba de reproducción, utilizar una base independiente y vacía.

## 3. Reglas de la simulación

- **500 viajes por vehículo** y **250 viajes por conductor**; se asignan dos conductores exclusivos a cada vehículo.
- **25 mantenimientos por vehículo** (uno después de cada 20 viajes).
- **Entre dos y seis entregas por viaje**, con proporciones controladas 5 % / 20 % / 50 % / 20 % / 5 %. Total: 400.000 entregas.
- Los viajes generados están marcados `completed` y las entregas `delivered`: es una simplificación del escenario sintético, no una tasa real de éxito.
- Se mantienen restricciones de secuencia temporal, ubicación, peso/capacidad y relaciones.
- La función `gethourly_distribution(weekday)` pondera salidas según hora y día; es una distribución diseñada, no una medición empírica.

**Cobertura observada en las consultas del entorno cargado:** aproximadamente del **29 de octubre de 2024 al 18 de octubre de 2026**. El rango proyectado por el generador no debe confundirse con las fechas efectivamente presentes en la carga.

### Limitaciones del modelo

- Los valores de consumo, distancia, matrícula, duración y costo son sintéticos.
- Las fechas `timestamp without time zone` no representan información de zona horaria.
- `maintenance_date` es un `DATE`, por lo que no registra la hora del mantenimiento ni bloquea automáticamente el uso del vehículo.
- Las rutas locales comparten ciudad de origen y destino; las interurbanas mantienen ciudades diferentes.
- La asignación uniforme de viajes limita la comparación realista de productividad.

## 4. Verificaciones rápidas de la carga

Esta consulta es **solo de lectura**; puede ejecutarse en DBeaver para corroborar las cantidades:

```sql
SELECT 'vehicles' AS tabla, COUNT(*) AS filas FROM public.vehicles
UNION ALL SELECT 'drivers', COUNT(*) FROM public.drivers
UNION ALL SELECT 'routes', COUNT(*) FROM public.routes
UNION ALL SELECT 'trips', COUNT(*) FROM public.trips
UNION ALL SELECT 'deliveries', COUNT(*) FROM public.deliveries
UNION ALL SELECT 'maintenance', COUNT(*) FROM public.maintenance
ORDER BY tabla;
```

Las pruebas del Avance #1 comprobaron además integridad referencial, relaciones, temporalidad y consistencia de pesos, sin errores en las validaciones informadas. Esto no equivale a una auditoría completa del desempeño de producción.

## 5. Continuidad con el Avance #2

Una vez cargada y validada la base, se analizaron las consultas **1, 2, 3, 4, 5, 7, 9 y 11** del conjunto original de 12 consultas. Se documentaron cinco experimentos de indexación y una corrección lógica de la Query 9.

- [Presentación general de FleetLogix](README.md)
- [Documentación técnica del Avance #2](Documentacion/Avance_2/README_AVANCE_2.md)
- [Metodología y benchmarks de SQL](Documentacion/Avance_2/03_metodologia_y_benchmarks.md)

**Estado:** generación, carga y validaciones completadas; documentación histórica del Avance #1 actualizada sin reejecutar scripts de carga.
