# Auditoría de asignaciones (solo lectura)

En Sectores y herramientas, **Auditar asignaciones** inicia una consulta asíncrona de clientes, asociaciones activas de sectores Ubiquiti M/AC y MikroTik, ARP del router principal y Simple Queues individuales. Muestra nombre, IP, MAC, sector y evidencias. No cambia clientes, colas, credenciales ni equipos. Solo guarda temporalmente el trabajo y resultado en Redis (15 minutos).

Clasificación: revisar diferencias, faltan datos y sin diferencias observadas. Detecta IP duplicada entre clientes, múltiples MAC por IP, diferencias de nombre, cola ausente/duplicada y asociaciones con IP sin cliente. No equivale a identidad física validada: ARP puede estar antiguo, MAC Ethernet y radio pueden diferir y nombres de colas pueden provenir del propio backend. Consultas sucesivas no constituyen una instantánea atómica. Sectores inaccesibles o MAC sin IP quedan como información incompleta; no implican desconexión.

POST `/pagos/auditoria-asignaciones/` devuelve `audit_token`; GET `/pagos/auditoria-asignaciones/<audit_token>/` devuelve estado y reporte. Ambos requieren autenticación; el token está ligado al usuario. Solo una auditoría simultánea. No existe endpoint para aplicar correcciones.

Requiere Redis, Celery worker y las credenciales existentes de sectores/router. Desplegar web y worker con las mismas versiones. No requiere migraciones.

```sh
docker compose up -d --build django-web celery-worker
```

Pruebas: `python manage.py test pagos.test_assignment_report`. La lógica pura puede probarse sin servicios; la conectividad real requiere la red de producción.
