# FleetLogix - Avance #4 FINAL (AWS)

**Entrega académica lista para integrar al repositorio. No despliega infraestructura ni causa cargos.**

## Qué entregar

1. `Documentacion/Avance_4/ARQUITECTURA_TECNICA.pdf` — documento principal: justificación, flujos, seguridad, observabilidad, migración, presupuesto y limitaciones.
2. `Documentacion/Avance_4/arquitectura_aws.png` — diagrama para insertar en la presentación; `.drawio` y `.dot` son versiones editables.
3. `Notebooks/Avance_4_CloudArchitecture.ipynb` — explicación y ejemplo local reproducible.
4. `Scripts/Avance_4/lambda_functions/` — cuatro handlers con adapters boto3; `test_lambda_logic.py` prueba el flujo sin AWS.
5. `Postman/FleetLogix_API.postman_collection.json` — llamadas de ejemplo, requieren endpoint desplegado si se usan contra AWS.

## Una sola prueba local (opcional, recomendable para evidencia)

Desde la raíz del proyecto:

```powershell
python Scripts/Avance_4/test_lambda_logic.py
```

Resultado esperado: `PRUEBA LOCAL AWS COMPLETA: OK`; API/DynamoDB/ETA/SNS/S3 simulados. No necesita instalar boto3 ni cuenta AWS porque el modo local está activo.

Para convertirlo en despliegue real se necesitarían recursos AWS, autorización JWT, reglas EventBridge, permisos IAM, variables de entorno, reintentos y control de costo. **No habilitar `LOCAL_DEMO=0` sin configuración y revisión.**

## Aclaración importante para el docente

El enunciado indica que el foco es arquitectura y documentación, **no implementación de la infraestructura**. Por eso se incluye código Lambda de ejemplo y prueba local, un plan de migración RDS, no una migración efectuada. El costo USD 23.10/mes es teórico en us-east-2 para laboratorio de bajo tráfico; no se ha generado factura ni se aplicaron créditos Free Tier.

**Estado:** el avance 4 está listo como entrega de diseño/documentación con demostración local; no representa infraestructura AWS desplegada.
