# FleetLogix — Avance 3, extracción para FACT_DELIVERIES

## Objetivo

Preparar 400.000 entregas completadas de PostgreSQL para la futura carga en Snowflake, sin modificar el origen ni el destino. La salida tiene **una fila por `DELIVERY_ID`**.

## Instalación y ubicación

Colocar `07_extract_transform_fact_deliveries.py` en `Scripts/Avance_3/` del proyecto. Reutiliza el archivo `.env` de la raíz y las dependencias `psycopg2-binary` y `python-dotenv` ya utilizadas en las etapas anteriores.

Desde la raíz del proyecto:

```powershell
python Scripts/Avance_3/07_extract_transform_fact_deliveries.py
```

Si la contraseña de PostgreSQL no está en el entorno, el script la solicitará sin mostrarla.

## Archivos generados

- `data/staging/avance_3/prepared/fact_deliveries.csv`
- `data/staging/avance_3/prepared/fact_deliveries_audit.json`

No subir los archivos de staging a Git: incluyen referencias a datos de clientes.

## Controles esperados

| Indicador | Control |
| --- | ---: |
| Entregas únicas | 400.000 |
| Viajes | 100.000 |
| Distancia total asignada | 4.701.486,980000 km |
| Combustible total asignado | 633.064,820000 L |

El archivo se genera como `.tmp` y solo se publica al completar las validaciones.

## Reglas de transformación

- `DATE_KEY = YYYYMMDD` según `delivered_datetime`.
- `DELIVERY_HOUR` = hora local de la entrega (0–23); el `TIME_KEY` se resolverá durante la carga a Snowflake, tras verificar la estructura real de `DIM_TIME`.
- `CUSTOMER_BK` coincide con el algoritmo de `05_extract_transform_customers.py`: SHA-256 del JSON compacto `[lower(trim(customer_name)), lower(trim(delivery_address))]`.
- `DELIVERY_DURATION_MINUTES`: minutos entre salida del viaje y entrega real.
- `SCHEDULE_VARIANCE_MINUTES`: minutos de entrega real menos fecha programada; positivo significa retraso.
- `IS_ON_TIME`: verdadero si la entrega ocurrió en o antes de lo programado.
- Distancia y combustible se asignan proporcionalmente al peso del paquete **dentro de cada viaje**. La última entrega recibe el residuo por redondeo para garantizar conciliación exacta con seis decimales.
- `ESTIMATED_REVENUE_COP` y `REVENUE_POLICY_VERSION` permanecen vacíos: política financiera sintética pendiente de definición.
- `SOURCE_ROW_HASH` se crea de manera determinista para futuras cargas incrementales.

## Límite importante

Este script **no resuelve aún las claves sustitutas de las dimensiones** ni escribe en `FACT_DELIVERIES`. El siguiente cargador debe unir `VEHICLE_ID`, `DRIVER_ID` con vigencias SCD2, `ROUTE_ID`, `CUSTOMER_BK`, `DATE_KEY` y `DELIVERY_HOUR` contra las dimensiones en Snowflake, y rechazar cualquier fila sin relación. Antes de construirlo, revisar `DESCRIBE TABLE ANALYTICS.DIM_TIME` para confirmar la columna de hora y la clave real.

Las cantidades y totales de referencia corresponden al conjunto sintético auditado. Si se cambia intencionalmente el origen, deberán actualizarse de manera controlada y documentada.
