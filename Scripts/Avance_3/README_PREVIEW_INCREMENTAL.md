# FleetLogix · Comprobación de cambios en FACT_DELIVERIES

## Objetivo

Comparar en modo **solo lectura** los pares `DELIVERY_ID` y `SOURCE_ROW_HASH` del CSV `data/staging/avance_3/prepared/fact_deliveries.csv` con los almacenados en `ANALYTICS.FACT_DELIVERIES` de Snowflake.

## Instalación

Copiar `11_preview_incremental_fact.py` a `Scripts/Avance_3/` del repositorio. Usa el `.env` existente y el conector de Snowflake ya instalado. No requiere bibliotecas adicionales.

```powershell
python Scripts/Avance_3/11_preview_incremental_fact.py
```

Se abre OAuth con navegador. Esta prueba no altera PostgreSQL, Snowflake ni los archivos locales.

## Resultado de referencia

Si se ejecuta después del último `--full` exitoso, sin modificar el CSV, se espera: CSV 400.000, Snowflake 400.000, sin cambios 400.000, nuevas 0, modificadas 0 y ausentes 0.

## Límites de la prueba

- Se lee el CSV completo y se consultan las 400.000 parejas de claves y hashes desde Snowflake; **no es todavía un extractor incremental del origen**. Se prueba únicamente el *detector de diferencias*.
- La ausencia de un registro del CSV no autoriza su borrado en Snowflake; debe definirse una política para bajas y estados.
- Cuando cambian viajes, rutas, clientes, conductores o la política de ingresos, puede requerirse recalcular todos los hechos afectados, aunque su entrega original no haya cambiado. El cálculo de hashes debe contemplar las dependencias.
- Un futuro pipeline productivo debería calcular diferencias en staging dentro de Snowflake, procesar transacciones de forma segura, medir inserciones y actualizaciones reales, y utilizar autenticación no interactiva. `updated_at` o CDC en PostgreSQL permitirían evitar escaneos completos del origen.
- Los CSV pueden contener datos de cliente; mantener la carpeta de staging fuera de Git.
