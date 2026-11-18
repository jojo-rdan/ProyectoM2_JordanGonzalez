# Matriz breve de cumplimiento — FleetLogix Avance 4

| Requisito de la consigna | Evidencia | Estado |
|---|---|---|
| Arquitectura AWS con diagrama y justificación | `ARQUITECTURA_TECNICA.pdf`, `arquitectura_aws.drawio` y PNG | Documentado |
| API Gateway para conductores | Flujo `POST /events`, `GET /deliveries/{id}` | Diseñado y simulado localmente |
| S3 histórico por fecha | `lambda_archive`, prefijo `events/AAAA/MM/DD/` | Código de ejemplo y prueba local |
| 3 a 5 funciones Lambda | Cuatro handlers en `lambda_functions/handlers.py` | Código de ejemplo y prueba local |
| Entrega completada, ETA, desvío | `lambda_ingest`, `lambda_eta`, `lambda_route_alert` | Funcional en modo local |
| Automatización básica de procesamiento | EventBridge como bus/reglas por tipo de evento | Diseño documentado |
| RDS PostgreSQL + migración + backups | Sección de migración y retención de 7 días | Plan documentado, no migrado |
| DynamoDB estado actual | Esquema y lectura/escritura en Lambda | Simulación funcional |
| Una funcionalidad tiempo real | POST actualiza estado y GET lo consulta inmediatamente | Prueba local ejecutada |
| CloudWatch métricas y alertas | Tabla de umbrales y SNS | Documentado, no configurado |
| IAM no root y cifrado | Roles mínimos, JWT, TLS, KMS/SSE-S3 | Diseñado, no provisionado |
| Costo teórico menor a USD 50/mes | `presupuesto_aws.csv` + sección 8 PDF | USD 23.10/mes, estimado condicional |
| Jupyter y boto3 | Notebook ejecutado; handlers con llamadas boto3 para AWS | Entregado |
| Postman | Colección de endpoints hipotéticos | Entregada; no probada en AWS |

**Alcance honesto:** la consigna prioriza diseño y documentación, por lo que NO se afirma un despliegue AWS, RDS migrada, backups activos, permisos IAM aplicados ni un servicio público real en producción.
