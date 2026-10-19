# Inventario de IP y antenas

La app inicia `POST /pagos/ips-disponibles/escanear/` con `start: 21` y `end: 254` y consulta `GET /pagos/ips-disponibles/escaneos/<scan_id>/` cada dos segundos. Ambos requieren autenticación. El resultado solo puede consultarlo quien inició la tarea y caduca a los diez minutos. Solo se ejecuta un escaneo de red a la vez. No se reserva ni se asigna ninguna dirección.

El GET anterior `/pagos/ips-disponibles/` sigue devolviendo disponibilidad según la base de clientes, sin escanear. Las direcciones reservadas están centralizadas en `pagos/ip_inventory.py`, incluidos los routers 179 y 254. Los sectores consultados son los mismos grupos de Ubiquiti M2, M5, AC y MikroTik de la app.

## Fuentes

- Clientes: se vuelven a leer al finalizar el escaneo.
- Ping desde el worker: dos paquetes por dirección y hasta 32 direcciones simultáneas. Una sola respuesta se considera alcanzable. Error de permisos, falta del ejecutable o timeout del proceso se muestran como error, no como dirección disponible.
- Sectores Ubiquiti: lista de asociados de `sta.cgi`, usando las credenciales específicas M/AC.
- Sectores MikroTik: `/interface/wireless/registration-table/print` usando admin y la contraseña configurada para estos sectores.
- ARP del router principal: ayuda a relacionar MAC de antenas asociadas con IP. Sus entradas no se consideran por sí solas una prueba de conexión activa. Se usan `MIKROTIK_API_HOST`, `MIKROTIK_API_USER`, `MIKROTIK_API_PASSWORD` y `MIKROTIK_API_PORT`, compartidas con la medición de consumo.

`disponibles` contiene las IP sin cliente y no reservadas. `sin_respuesta_ping` incluye todas las direcciones sin respuesta, aunque estén asignadas o reservadas. `resultados` incluye cliente, asociación, reserva y resultado de ping por dirección. `candidatas_disponibles` solo contiene IP sin asignación, reserva, asociación ni respuesta, cuando se consultaron todos los sectores y se pudieron resolver las IP de todas las asociaciones. Cualquier error de ping hace que el escaneo sea incompleto. Una candidata no garantiza disponibilidad: puede existir un equipo apagado o que bloquee ICMP.

## Despliegue

Actualizar código y reconstruir:

```sh
docker compose up -d --build django-web celery-worker
docker compose restart frontend-proxy
```

El worker necesita Redis, `ping`, `NET_RAW`, acceso a los sectores y al API del router. El Dockerfile y Compose actuales ya incluyen ping y NET_RAW. No requiere migraciones. El scan tiene un límite de cuatro minutos de ejecución normal y la app espera hasta cinco minutos; los errores y los sectores inaccesibles quedan visibles en el resultado.

## Validación

Las pruebas de clasificación están en `pagos/test_ip_inventory.py`. Probar además en el servidor: una IP asignada apagada, un equipo no registrado que responde, una antena asociada que bloquea ICMP, un sector inaccesible, dos escaneos simultáneos y Redis/worker detenidos. No cambiar IP de clientes como parte de esta verificación.
