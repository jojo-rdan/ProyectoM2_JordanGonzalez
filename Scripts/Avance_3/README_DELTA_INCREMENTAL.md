# FleetLogix · Avance 3 · Preparación de delta incremental

## Propósito

`12_prepare_incremental_fact_delta.py` lee los `DELIVERY_ID` y `SOURCE_ROW_HASH` ya almacenados en `FLEETLOGIX_DWH.ANALYTICS.FACT_DELIVERIES`, compara cada fila del CSV **completo** `prepared/fact_deliveries.csv` y genera un CSV **solo de diferencias** en `data/staging/avance_3/incremental/fact_deliveries_delta.csv`. La tabla de hechos, las dimensiones y PostgreSQL no se modifican.

- **Nuevas**: `DELIVERY_ID` no aparece en Snowflake.
- **Modificadas**: existe el ID, pero su hash difiere.
- **Sin cambios**: mismo ID y mismo hash.
- **Ausentes de CSV**: existe en Snowflake pero ya no en el CSV. En este caso la ejecución falla sin publicar un delta nuevo; no se infieren eliminaciones automáticamente.

La salida preserva **las 23 columnas originales y su orden**, para que luego un cargador incremental especializado pueda reutilizar las transformaciones de resolución de dimensiones.

## Instalación y ejecución

Copia `12_prepare_incremental_fact_delta.py` dentro de `Scripts/Avance_3/` del repositorio. No reemplaces otros scripts. Reutiliza `.venv`, `.env` y `snowflake-connector-python`, que ya se instalaron en pasos anteriores.

Primero prueba tres escenarios ficticios sin conexión a Snowflake ni modificación de archivos reales:

```powershell
python Scripts/Avance_3/12_prepare_incremental_fact_delta.py --self-test
```

Se espera:
- un escenario con **1 nueva, 1 modificada y 1 sin cambios**;
- repetición con **0 diferencias**;
- detección y bloqueo de **una ausencia**.

Luego prueba contra los datos reales (con OAuth interactivo):

```powershell
python Scripts/Avance_3/12_prepare_incremental_fact_delta.py
```

Con el snapshot actual sincronizado, el resultado previsto es:

- CSV fuente: **400.000**
- Snowflake: **400.000**
- Sin cambios: **400.000**
- Nuevas: **0**
- Modificadas: **0**
- Ausentes: **0**
- Filas en delta: **0**

El `fact_deliveries_delta.csv` queda **con el encabezado únicamente**, y el JSON de auditoría registra los totales. No hay `PUT`, `COPY INTO` ni `MERGE`.

## Advertencias importantes

1. **NO** ejecutes `08_load_fact_deliveries.py --execute` sobre el delta. Ese cargador realiza validaciones de snapshot completo con conteos fijos de 400.000 entregas, 100.000 viajes y totales de conciliación globales. Se diseñará un cargador de delta separado, con controles incrementales específicos.
2. Los scripts fuente `07_extract_transform_fact_deliveries.py` y `08_load_fact_deliveries.py` contienen todavía las **cantidades y totales de referencia fijos** del conjunto sintético. Hay que refactorizarlos antes de una prueba end-to-end con registros nuevos reales. Esta herramienta **solo prepara diferencias sobre el CSV existente**.
3. Esta estrategia sigue leyendo el CSV completo y los hashes completos de Snowflake; **no implementa CDC ni extracción incremental** desde PostgreSQL. Para mejorarla, se necesitarán columnas de modificación y/o CDC con límites de actualización seguros.
4. Cambios en viajes, rutas, clientes, conductores o políticas pueden exigir recalcular hechos relacionados. Un cambio SCD tipo 2 no siempre cambia el `SOURCE_ROW_HASH` de la entrega; la resolución temporal debe revisarse en un ETL incremental verdadero.
5. Un CSV que omite entregas puede reflejar un cambio en la elegibilidad o un problema de extracción. **No borres filas** por ese motivo. Una ejecución fallida invalida cualquier delta anterior; no reutilices archivos viejos.
6. Mantén `data/staging/avance_3/` en `.gitignore`. Los registros de hechos pueden incluir identificadores de seguimiento. La salida de auditoría no imprime contenido de registros, solo IDs de ejemplo y conteos.
7. Este script usa OAuth de navegador, por lo que **todavía no es apto para ejecución nocturna desatendida**.

## Resultado de esta etapa

La aprobación de ambas pruebas confirma que podemos **clasificar** las diferencias y construir un archivo delta coherente, pero no que el delta pueda **aplicarse** aún. El siguiente paso técnico será un cargador de delta con pruebas de dimensionamiento, idempotencia, integridad referencial y reconciliación sin totales estáticos.
