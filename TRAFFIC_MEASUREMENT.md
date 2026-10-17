# Medición de consumo por cliente

Configurar en `.env.prod` para Django y Celery:

```env
MIKROTIK_API_HOST=192.168.1.2
MIKROTIK_API_PORT=8728
MIKROTIK_API_USER=admin
MIKROTIK_API_PASSWORD=CONFIGURAR_EN_EL_SERVIDOR
```

Usar una cuenta con permiso de lectura y acceso API. El puerto 8728 debe ser accesible solo desde la red de confianza. No guardar las credenciales en Git.

Reconstruir los servicios después de configurar las variables:

```sh
docker compose up -d --build django-web celery-worker
```

No requiere migraciones. Redis y el worker deben estar disponibles.

POST `/pagos/clientes/<id>/medir-consumo/` autenticado devuelve `measurement_id` (202). Consultar GET `/pagos/mediciones/<measurement_id>/` cada 2 segundos: `pending`, `running`, `completed` o `failed`. El token es exclusivo del usuario y caduca a los 5 minutos. Solo se admite una medición por cliente al mismo tiempo.

Lee contadores de la única cola /32 del cliente, sin alterar límites ni reiniciar contadores. Devuelve `upload_mbps`, `download_mbps`, `upload_mb`, `download_mb`, `duration_seconds`, `ip` y `queue_name`. MB usa 1,000,000 bytes. Promedia el tráfico observado durante al menos 30 segundos, incluidos los segundos sin tráfico. No es una prueba de velocidad máxima. FastTrack u otros caminos que eviten las colas producen mediciones incompletas.

Verificar en el servidor con un cliente conocido y tráfico controlado: comparación de contadores, cliente inactivo, cola inexistente, credenciales inválidas, Redis/worker detenidos y dos solicitudes simultáneas.
