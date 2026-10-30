# 1. Análisis del modelo relacional proporcionado

## 1.1. Descripción general del modelo

FleetLogix es una empresa de transporte y logística dedicada a operaciones de última milla, con una flota de 200 vehículos que presta servicios en cinco ciudades principales.

El modelo de datos proporcionado está implementado en PostgreSQL y utiliza una estructura relacional orientada a gestionar vehículos, conductores, rutas, viajes, entregas y mantenimientos.

La base de datos se compone de seis tablas, que suman 50 columnas y están conectadas mediante cinco relaciones de clave foránea.

Las tablas se clasifican en dos grupos:

**Tablas maestras:**

- `vehicles`: almacena la información de los vehículos que integran la flota.
- `drivers`: registra los datos personales y laborales de los conductores.
- `routes`: contiene las rutas predefinidas, sus ciudades de origen y destino, distancias y costos estimados.

**Tablas transaccionales:**

- `trips`: registra los viajes realizados y los recursos asignados a cada operación.
- `deliveries`: almacena las entregas individuales asociadas a los viajes.
- `maintenance`: registra los mantenimientos efectuados a los vehículos.

Esta organización permite separar las entidades relativamente estables de los eventos operativos, facilitando la trazabilidad de las operaciones logísticas.

---

## 1.2. Documentación de las relaciones

El modelo contiene cinco relaciones de uno a muchos (1:N).

| Tabla origen | Campo FK | Tabla referenciada | Cardinalidad |
|---|---|---|---|
| `trips` | `vehicle_id` | `vehicles.vehicle_id` | N:1 |
| `trips` | `driver_id` | `drivers.driver_id` | N:1 |
| `trips` | `route_id` | `routes.route_id` | N:1 |
| `deliveries` | `trip_id` | `trips.trip_id` | N:1 |
| `maintenance` | `vehicle_id` | `vehicles.vehicle_id` | N:1 |

**Relación vehicles – trips**

Un vehículo puede participar en múltiples viajes a lo largo de su vida operativa. Cada viaje puede estar asociado con un vehículo mediante el campo `vehicle_id`.

Esta relación permite analizar el nivel de utilización de la flota, los kilómetros recorridos y el consumo de combustible.

**Relación drivers – trips**

Un conductor puede realizar múltiples viajes en diferentes momentos. Cada viaje puede asociarse con un conductor mediante `driver_id`.

Esta relación permite medir la productividad de los conductores y analizar la distribución de las operaciones.

**Relación routes – trips**

Una ruta predefinida puede utilizarse en múltiples viajes. Cada viaje puede referenciar una ruta mediante `route_id`.

Esto permite comparar tiempos reales de desplazamiento, consumo de combustible y eficiencia por ruta.

**Relación trips – deliveries**

Un viaje puede contener múltiples entregas, mientras que cada entrega puede asociarse a un viaje mediante `trip_id`.

Esta relación es fundamental para analizar el volumen de paquetes, los tiempos de entrega y la eficiencia logística.

**Relación vehicles – maintenance**

Un vehículo puede tener múltiples registros de mantenimiento durante su vida útil. Cada mantenimiento puede referenciar un vehículo mediante `vehicle_id`.

Esto permite estudiar costos de mantenimiento, frecuencia de servicios y comportamiento de la flota.

**Observación:** aunque las relaciones existen mediante claves foráneas, los cinco campos FK permiten valores `NULL` en el esquema original. Por tanto, la participación obligatoria de las entidades dependientes debe garantizarse mediante las reglas de generación y validación de datos.

---

## 1.3. Documentación de constraints

El esquema utiliza restricciones para garantizar la identificación de registros, la unicidad de determinados campos y la integridad referencial.

### Claves primarias (PRIMARY KEY)

Cada tabla dispone de una clave primaria definida como `SERIAL PRIMARY KEY`.

| Tabla | Clave primaria |
|---|---|
| `vehicles` | `vehicle_id` |
| `drivers` | `driver_id` |
| `routes` | `route_id` |
| `trips` | `trip_id` |
| `deliveries` | `delivery_id` |
| `maintenance` | `maintenance_id` |

Estas claves identifican inequívocamente cada registro y no permiten valores nulos ni duplicados.

### Claves foráneas (FOREIGN KEY)

El modelo contiene las siguientes restricciones:

- `trips_vehicle_id_fkey`
- `trips_driver_id_fkey`
- `trips_route_id_fkey`
- `deliveries_trip_id_fkey`
- `maintenance_vehicle_id_fkey`

Estas restricciones impiden que se almacenen identificadores no nulos que no existan en las tablas referenciadas.

### Restricciones UNIQUE

Se identificaron cinco restricciones de unicidad:

| Tabla | Campo UNIQUE | Finalidad |
|---|---|---|
| `vehicles` | `license_plate` | Evitar matrículas duplicadas |
| `drivers` | `employee_code` | Garantizar códigos únicos de empleados |
| `drivers` | `license_number` | Evitar números de licencia duplicados |
| `routes` | `route_code` | Identificar cada ruta mediante un código único |
| `deliveries` | `tracking_number` | Garantizar identificadores únicos de seguimiento |

### Restricciones NOT NULL

Se identificaron 21 columnas que no admiten valores nulos, distribuidas de la siguiente manera:

| Tabla | Columnas NOT NULL |
|---|---|
| `vehicles` | `vehicle_id`, `license_plate`, `vehicle_type` |
| `drivers` | `driver_id`, `employee_code`, `first_name`, `last_name`, `license_number` |
| `routes` | `route_id`, `route_code`, `origin_city`, `destination_city` |
| `trips` | `trip_id`, `departure_datetime` |
| `deliveries` | `delivery_id`, `tracking_number`, `customer_name`, `delivery_address` |
| `maintenance` | `maintenance_id`, `maintenance_date`, `maintenance_type` |

Las restantes 29 columnas permiten valores nulos.

En los resultados de PostgreSQL, las restricciones de nulidad aparecen representadas con nombres terminados en `_not_null` y clasificadas como `CHECK` por la consulta utilizada. No deben confundirse con restricciones adicionales que validen reglas del negocio.

### Valores predeterminados (DEFAULT)

| Tabla | Campo | Valor predeterminado |
|---|---|---|
| `vehicles` | `status` | `active` |
| `drivers` | `status` | `active` |
| `trips` | `status` | `in_progress` |
| `deliveries` | `delivery_status` | `pending` |
| `deliveries` | `recipient_signature` | `false` |
| `routes` | `toll_cost` | `0` |

Los valores predeterminados se utilizan cuando la columna correspondiente se omite de una operación `INSERT`. No impiden asignar explícitamente `NULL` a una columna que lo permita.

### Índices adicionales

El archivo original incluye tres índices secundarios:

| Índice | Tabla | Campo |
|---|---|---|
| `idx_trips_departure` | `trips` | `departure_datetime` |
| `idx_deliveries_status` | `deliveries` | `delivery_status` |
| `idx_vehicles_status` | `vehicles` | `status` |

Estos índices buscan mejorar el acceso a los datos en consultas frecuentes relacionadas con fechas de salida y estados operativos.

PostgreSQL también crea índices asociados a las restricciones `PRIMARY KEY` y `UNIQUE`.

### Restricciones no implementadas

El modelo no incorpora restricciones explícitas de negocio para:

- Garantizar capacidades y pesos positivos.
- Impedir que el peso transportado supere la capacidad del vehículo.
- Exigir que la llegada ocurra después de la salida.
- Restringir los valores posibles de los estados.
- Evitar fechas de mantenimiento inconsistentes.
- Garantizar que un conductor tenga su licencia vigente durante un viaje.
- Impedir viajes simultáneos de un mismo conductor o vehículo.

Estas limitaciones deberán contemplarse durante la generación y validación de los datos sintéticos.

---

# 2. Identificación de patrones de negocio implícitos

El modelo permite identificar varios patrones operativos asociados al funcionamiento de una empresa de logística de última milla.

Las siguientes reglas se infieren de la estructura relacional y de los requisitos del proyecto. No todas están implementadas como restricciones SQL.

## 2.1. Reutilización de recursos operativos

La relación entre `vehicles`, `drivers` y `trips` muestra que los vehículos y conductores son recursos reutilizables.

Un mismo vehículo puede completar múltiples viajes y un conductor puede participar en diferentes operaciones durante su período laboral.

**Regla de negocio:** las asignaciones deben respetar la disponibilidad temporal de ambos recursos, evitando solapamientos de viajes.

## 2.2. Distribución de entregas por viaje

La relación `trips` – `deliveries` representa un patrón de consolidación de paquetes.

El proyecto establece que cada viaje debe contener entre dos y seis entregas, con una concentración alrededor de cuatro entregas por viaje.

**Regla de negocio:** la generación sintética deberá conservar esta distribución y garantizar que todas las entregas pertenezcan a viajes existentes.

## 2.3. Operación histórica y variaciones horarias

El proyecto requiere generar 100.000 viajes distribuidos en dos años de operación.

Esto implica que la actividad debe reflejar variaciones temporales, en lugar de distribuir los viajes de manera completamente uniforme.

**Patrón esperado:** concentración de operaciones en franjas horarias de mayor demanda y diferencias entre días laborales y fines de semana.

Este comportamiento deberá modelarse mediante `generate_trips()` y su función auxiliar `gethourly_distribution()`.

## 2.4. Restricciones de capacidad de transporte

Los campos `vehicles.capacity_kg`, `trips.total_weight_kg` y `deliveries.package_weight_kg` permiten relacionar la capacidad máxima de un vehículo con la carga transportada.

**Reglas de negocio propuestas:**

- El peso de cada paquete debe ser positivo.
- El peso total del viaje no debe superar la capacidad del vehículo.
- La suma de los pesos de los paquetes asociados a un viaje debe ser coherente con su carga total registrada.

Estas reglas buscan evitar situaciones operativamente imposibles.

## 2.5. Mantenimiento asociado al uso de la flota

La relación `vehicles` – `maintenance` permite representar el desgaste de los vehículos mediante su historial de mantenimiento.

El proyecto establece aproximadamente un mantenimiento por cada 20 viajes, lo que corresponde a 5.000 mantenimientos para 100.000 viajes.

Los tipos establecidos para los datos sintéticos son:

- Cambio de aceite.
- Revisión de frenos.
- Cambio de llantas.
- Mantenimiento general.
- Revisión de motor.
- Alineación y balanceo.

**Regla de negocio:** el mantenimiento debe asociarse a vehículos existentes y mantener coherencia con su antigüedad y nivel de utilización.

## 2.6. Coherencia temporal de las operaciones

Las tablas contienen fechas de adquisición, contratación, vencimiento de licencias, viajes, entregas y mantenimiento.

Esto implica una dependencia cronológica entre diferentes procesos del negocio.

**Reglas de negocio propuestas:**

- La fecha de adquisición de un vehículo debe preceder a sus operaciones.
- La fecha de contratación de un conductor debe preceder a los viajes asignados.
- La licencia del conductor debe estar vigente durante sus viajes.
- La fecha de llegada de un viaje debe ser posterior a su salida.
- Las entregas completadas deben tener fechas compatibles con el intervalo del viaje.
- Las fechas de mantenimiento deben ser posteriores a la adquisición del vehículo.
- El próximo mantenimiento debe programarse después del mantenimiento efectuado.

## 2.7. Seguimiento del ciclo de vida operativo

Los campos `status`, `delivery_status` y `recipient_signature` permiten representar distintos estados de la operación.

Esto sugiere que FleetLogix necesita conocer tanto la situación general de los recursos como el resultado individual de las entregas.

**Patrón esperado:** las entregas completadas deben ser coherentes con su fecha de finalización y la evidencia de recepción, cuando corresponda.

El modelo permite almacenar estos datos, pero no implementa reglas automáticas de transición entre estados.

## 2.8. Análisis de eficiencia logística

Los atributos de rutas, viajes y entregas permiten calcular indicadores relacionados con:

- Consumo de combustible por distancia recorrida.
- Duración real frente a duración estimada.
- Número de entregas por viaje.
- Productividad de vehículos y conductores.
- Costos de mantenimiento por vehículo.
- Porcentaje de entregas completadas.

Estos indicadores muestran que la estructura puede servir como base para futuros análisis operativos y procesos de inteligencia de negocios.

---

# 3. Diagrama entidad-relación del modelo existente

El diagrama entidad-relación fue generado mediante DBeaver a partir de las tablas y claves foráneas implementadas en PostgreSQL.

En él se representan las seis entidades, sus atributos, claves primarias y relaciones.

La organización utilizada permite distinguir claramente:

- **Tablas maestras:** `vehicles`, `drivers` y `routes`.
- **Tabla transaccional central:** `trips`.
- **Tablas transaccionales dependientes:** `deliveries` y `maintenance`.

Las conexiones representan las cinco relaciones de uno a muchos definidas en el esquema original.

El diagrama fue elaborado sin modificar las tablas proporcionadas y constituye evidencia visual de la estructura relacional implementada.

**[Insertar aquí el diagrama ER exportado desde DBeaver.]**

---

# 4. Análisis de posibles mejoras sin modificar la estructura base

Aunque el modelo proporcionado cubre los elementos esenciales de una operación logística, existen oportunidades de mejora relacionadas con integridad, normalización, calidad de datos y rendimiento.

Estas propuestas se documentan exclusivamente como recomendaciones y no implican modificaciones al esquema original durante el Avance #1.

## 4.1. Fortalecer la obligatoriedad de las relaciones

**Problema identificado:**

Las claves foráneas permiten valores `NULL`. Esto significa que podrían existir viajes sin vehículo, conductor o ruta asignados, además de entregas sin viaje y mantenimientos sin vehículo.

**Mejora propuesta:**

Evaluar la incorporación de restricciones `NOT NULL` en los cinco campos FK.

**Beneficio:**

Garantizar que todos los registros transaccionales estén vinculados con sus entidades correspondientes.

## 4.2. Implementar restricciones CHECK para valores numéricos

**Problema identificado:**

El esquema permite registrar valores negativos o cero en campos donde podrían carecer de sentido operativo.

**Mejora propuesta:**

Agregar validaciones conceptuales como:

```sql
CHECK (capacity_kg > 0)
CHECK (distance_km > 0)
CHECK (fuel_consumed_liters >= 0)
CHECK (package_weight_kg > 0)
CHECK (cost >= 0)
```

**Beneficio:**

Reducir errores de captura y mejorar la calidad de la información almacenada.

Las restricciones entre tablas, como comparar la carga de un viaje con la capacidad de su vehículo, requerirían validaciones adicionales.

## 4.3. Incorporar validaciones temporales

**Problema identificado:**

No existen restricciones que aseguren coherencia entre fechas relacionadas.

**Mejora propuesta:**

Definir controles como:

```sql
CHECK (arrival_datetime > departure_datetime)
```

Y, para entregas completadas:

```sql
CHECK (
    delivered_datetime IS NULL
    OR scheduled_datetime IS NULL
    OR delivered_datetime >= scheduled_datetime
)
```

La segunda condición sería una política opcional del negocio, ya que las entregas anticipadas también pueden ser válidas. En cualquier caso, la consistencia con las fechas del viaje debe verificarse adicionalmente.

**Beneficio:**

Prevenir registros cronológicamente imposibles y facilitar el análisis de tiempos operativos.

## 4.4. Estandarizar los estados operativos

**Problema identificado:**

Los estados se almacenan mediante campos `VARCHAR`, sin un conjunto explícito de valores permitidos.

**Mejora propuesta:**

Definir catálogos de estados o restricciones para los campos `status` y `delivery_status`.

**Beneficio:**

Evitar inconsistencias por diferencias ortográficas, valores no reconocidos o denominaciones duplicadas.

## 4.5. Fortalecer el control de disponibilidad de recursos

**Problema identificado:**

El modelo no impide que un conductor o vehículo sea asignado a viajes cuyos períodos de ejecución se superpongan.

**Mejora propuesta:**

Implementar validaciones temporales mediante lógica de aplicación o mecanismos de control apropiados en PostgreSQL.

**Beneficio:**

Garantizar asignaciones operativamente viables y obtener indicadores confiables de utilización de recursos.

## 4.6. Mejorar la representación de la información geográfica

**Problema identificado:**

Las ciudades de origen y destino se almacenan directamente como texto en `routes`.

Esto podría producir inconsistencias en la escritura de nombres y dificultades para gestionar información geográfica adicional.

**Mejora propuesta:**

Evaluar la creación futura de una entidad `cities` con identificadores únicos y atributos geográficos normalizados.

**Beneficio:**

Facilitar la estandarización de ubicaciones y el análisis de operaciones por ciudad.

## 4.7. Evaluar índices adicionales para consultas frecuentes

**Problema identificado:**

El esquema original incluye tres índices secundarios, pero no proporciona índices secundarios específicos para todas las columnas utilizadas como claves foráneas.

**Mejora propuesta:**

Evaluar índices sobre campos como:

- `trips.vehicle_id`
- `trips.driver_id`
- `trips.route_id`
- `deliveries.trip_id`
- `maintenance.vehicle_id`

La incorporación debe evaluarse mediante consultas representativas y planes de ejecución, considerando el costo adicional de mantenimiento de los índices durante las inserciones.

**Beneficio:**

Mejorar potencialmente el rendimiento de operaciones `JOIN`, filtros y consultas analíticas.

La selección e implementación de índices de optimización se desarrollará en el Avance #2.

## 4.8. Incorporar controles sistemáticos de calidad

**Problema identificado:**

La integridad estructural del modelo no garantiza por sí sola que los datos representen operaciones logísticas realistas.

**Mejora propuesta:**

Incorporar validaciones en Python y consultas de control en PostgreSQL para comprobar:

- Integridad referencial.
- Ausencia de identificadores duplicados.
- Coherencia temporal.
- Cumplimiento de capacidades máximas.
- Distribución realista de viajes y entregas.
- Ausencia de solapamientos operativos.
- Consistencia de fechas de licencias y mantenimientos.

**Beneficio:**

Generar un conjunto de datos sintéticos confiable, reproducible y adecuado para las posteriores etapas analíticas del proyecto.

---

# 5. Conclusión del análisis

El modelo relacional proporcionado para FleetLogix establece una estructura inicial adecuada para administrar las principales entidades y operaciones de una empresa de logística de última milla.

Las seis tablas, las claves primarias, las cinco relaciones mediante claves foráneas y las restricciones de unicidad proporcionan una base para mantener la integridad estructural de la información.

Sin embargo, el análisis identifica que varias reglas operativas importantes no están implementadas directamente en PostgreSQL. Entre ellas se encuentran la obligatoriedad de ciertas relaciones, el control de capacidades de carga, la coherencia temporal, la vigencia de licencias y la disponibilidad de conductores y vehículos.

Por esta razón, durante la siguiente etapa se desarrollará un generador de datos sintéticos en Python que respete las relaciones del modelo y aplique controles de calidad adicionales, sin modificar la estructura original proporcionada.

El análisis realizado cumple con los objetivos de documentar las relaciones y restricciones, identificar patrones de negocio implícitos, representar el modelo mediante un diagrama entidad-relación y proponer mejoras técnicas fundamentadas.

**Estado del Avance #1:** análisis del modelo documentado; pendiente generación, carga y validación de los 505.650 registros sintéticos.