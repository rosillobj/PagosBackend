# Sincronizar nombres de Simple Queues

En Sectores y herramientas, el botón «Revisar nombres por sincronizar» compara `Cliente.nombre` y `Cliente.ip_completa` con `/queue/simple`. Solo acepta una cola estática con un único target IPv4 /32 por cliente. Las colas generales /24, targets múltiples, dinámicas, ambiguas y nombres ocupados por otra cola se omiten.

GET `/pagos/mikrotik/sincronizar-nombres/` devuelve la vista previa y un token firmado por usuario, válido durante diez minutos. POST al mismo endpoint con `plan_token` aplica exclusivamente la lista revisada mediante Celery. GET `/pagos/mikrotik/sincronizar-nombres/<job_token>/` consulta el resultado. Todos requieren autenticación. Se admite una sincronización a la vez.

Solo se envía `name` al comando `/queue/simple/set`; no se cambian IP, límites, estado, orden o parent. Antes de ejecutar se comprueban otra vez nombre/IP del cliente y nombre/target/ID de la cola. Al terminar se releen los nombres del router. Un error detiene los envíos restantes y el resultado identifica cambios verificados, omitidos y fallidos. Si el worker se detiene o no se confirma un resultado, obtener otra vista previa antes de repetir. La operación no es una transacción del router: puede completarse parcialmente.

La conexión usa las mismas variables `MIKROTIK_API_HOST`, `MIKROTIK_API_USER`, `MIKROTIK_API_PASSWORD`, `MIKROTIK_API_PORT` de la medición de consumo. Ahora esa cuenta también necesita permiso de escritura para renombrar colas. Se usa UTF-8 para conservar acentos. No modificar las credenciales globales ni el servicio API para habilitar acceso externo.

Despliegue:

```sh
docker compose up -d --build django-web celery-worker
docker compose restart frontend-proxy
```

No requiere migraciones. Redis y Celery deben estar activos. Las pruebas de lógica están en `pagos/test_queue_names.py`; validar primero la vista previa del servidor y comprobar los primeros nombres aplicados en WinBox.
