# FleetLogix — Carga inicial de DIM_CUSTOMER

1. Copiar `06_load_dim_customer.py` en `Scripts/Avance_3/` del repositorio.
2. Comprobar que existe `data/staging/avance_3/prepared/dim_customer.csv` (389334 clientes, generado por el script anterior).
3. Desde la raíz del repo con el entorno virtual activado, ejecutar:

   ```powershell
   python Scripts/Avance_3/06_load_dim_customer.py
   ```

   Esta ejecución **solo valida el CSV local** y no accede a Snowflake.

4. Si la validación pasa, ejecutar:

   ```powershell
   python Scripts/Avance_3/06_load_dim_customer.py --execute
   ```

   Este comando sí carga datos en Snowflake mediante OAuth interactivo, PUT a un stage temporal, COPY a una tabla temporal y MERGE hacia `ANALYTICS.DIM_CUSTOMER`.

5. Ejecutar `08_validate_dim_customer.sql` en Snowsight y verificar las cantidades y la ausencia de duplicados.
6. Repetir `--execute` sin cambiar el CSV para probar idempotencia: el total y las versiones deben permanecer iguales.

## Precauciones
- No subir `.env`, el CSV ni los logs que contengan datos de clientes a GitHub.
- El CSV contiene nombres y direcciones: almacenarlo solo en la carpeta local ignorada por Git.
- La identidad `CUSTOMER_BK` es una clave determinista derivada de nombre y dirección; **no es anonimización** y no identifica inequívocamente a una persona.
- Este cargador valida la línea base de 389334 clientes del conjunto sintético. Para cargas incrementales, habrá que adaptar ese control a una cantidad dinámica.
- El stage y la tabla temporal desaparecen al finalizar la sesión. El MERGE se ejecuta como una operación transaccional.
- `OAUTH_AUTHORIZATION_CODE` necesita intervención en navegador; el ETL nocturno requerirá otra autenticación no interactiva.
- No ejecutar múltiples instancias del cargador simultáneamente.
