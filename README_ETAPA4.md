# FleetLogix — Etapa 4 | Avance #1

## Requisitos
Python 3.10+; `faker`, `pandas`, `numpy`, `psycopg2-binary`, `python-dotenv`.

Desde la **raíz del proyecto FleetLogix**, con `.venv` activado:

```powershell
python Scripts/01_data_generation.py
python Scripts/02_generate_transactions.py
```

El resultado es `data/{vehicles,drivers,routes,trips,deliveries,maintenance}.csv`.
Los seis CSV suman **505.650 registros**. Los logs se guardan en `logs/`.

> Estos dos comandos NO escriben en PostgreSQL. Si ya ejecutaste el primer comando
> y tienes los tres CSV maestros, no es necesario repetirlo.

## Opcional, siguiente paso: carga transaccional

Completa `.env` a partir de `.env.example` (NUNCA compartir ni publicar `.env`).
El archivo `03_load_all.py` solo carga cuando se invoca con permiso explícito:

```powershell
python Scripts/03_load_all.py --load
```

**Precauciones:**
- Aborta si cualquier tabla de destino tiene filas (no elimina nada).
- Hace todas las inserciones con `COPY` en una sola transacción.
- Mantiene `vehicle_id`, `driver_id`, `route_id`, `trip_id` y demás IDs de manera
  determinista: los CSV maestros carecen de IDs y el cargador asigna 1..N.
- Tras `COPY`, ajusta las secuencias SERIAL a los máximos de cada tabla.
- Genera una carga sintética demostrativa, no evidencia real de FleetLogix.

## Funciones explicadas

`gethourly_distribution(weekday)` construye una distribución de 24 probabilidades
normalizadas para la hora de salida de un viaje. Los días laborables dan mayor peso
al horario diurno, y los fines de semana cambian la ponderación; no es una medición
empírica.

`generate_trips(vehicles, routes, rng)` asigna 500 viajes por vehículo y alterna
entre dos conductores exclusivos por vehículo. Para cada viaje selecciona una hora
usando `gethourly_distribution`, elige una ruta cuyo origen coincide con la ciudad
actual del vehículo, calcula una duración cercana a la estimada y ajusta la salida
para no solaparse con la llegada del viaje anterior. Mantiene todos los eventos
entre el 29-10-2024 y el 28-10-2026. Añade 25 mantenimientos por vehículo (uno
por cada 20 viajes). El peso total de cada viaje se completa después, al crear las
entregas.

`delivery_count_distribution` impone exactamente 2–6 entregas por viaje, con
frecuencias 5%/20%/50%/20%/5% y un total exacto de 400.000 entregas.
`generate_deliveries` distribuye pesos por viaje sin superar capacidad, programa
horas entre salida y llegada y guarda 400.000 filas en streaming. Todos los viajes
están finalizados y todas las entregas están marcadas `delivered` para mantener
consistencia con el histórico: es una simplificación de la simulación documentada.

Las distancias, costos, tiempos y matrículas son supuestos sintéticos; no deben
interpretarse como valores reales ni certificados.

## Consideraciones

- Se reutiliza la ciudad en `origin_city`/`destination_city` para operaciones
  locales; las rutas interurbanas también pueden usarse.
- Los eventos de mantenimiento se fechan al terminar el 20.º, 40.º, ... viaje.
  Como `maintenance_date` es `DATE` (no timestamp), el esquema no permite
  representar la hora ni inmovilizar automáticamente al vehículo durante el servicio.
- La hora de la entrega siempre cae dentro del viaje correspondiente; se usan
  `timestamp without time zone` tal como los define el esquema original.
- La asignación de dos conductores por vehículo es una simplificación
  deliberada para evitar solapamientos sin alterar las tablas.
