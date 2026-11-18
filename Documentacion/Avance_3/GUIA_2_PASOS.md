# Cierre express — Avance #3

No reejecutar las extracciones ni las cargas ya aprobadas.

1. En Snowsight (`SYSADMIN`), ejecutar **`Scripts/Avance_3/16_finalize_analytics.sql`** una vez. Crea/actualiza 2 agregados y 2 vistas seguras sin tocar las tablas originales.
2. Ejecutar **`Scripts/Avance_3/18_validacion_cierre.sql`**. Esperado: 400000 hechos, 400000 en ambos agregados y las vistas; ingresos 6270850032.24 COP; 2 vistas seguras.

**Opcional con `ACCOUNTADMIN`:** ejecutar `17_roles_opcionales.sql` para crear los roles separados. No se asignan a usuarios automáticamente.

**Entregable:** incluir `Notebooks/Avance_3_DataWarehouse.ipynb`, los SQL y `README_CIERRE.md`. Conservar los scripts Python originales y los CSV fuera de Git.

**No hacer:** instalar tarea programada nocturna con OAuth interactivo, presentar 30 días de Time Travel sin confirmación de edición, o ejecutar un delta no vacío contra FACT_DELIVERIES sin ensayo aislado.

Para pasar al Avance #4 se requiere su enunciado o rúbrica; este paquete no inventa contenidos de la siguiente consigna.
