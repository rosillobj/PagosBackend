# Ping desde el servidor

En Sectores y herramientas: introducir una dirección IPv4 o IPv6 y pulsar Iniciar ping. Se ejecuta desde el contenedor celery-worker, con las rutas de red de ese servidor, no desde el teléfono. Admite IP literales, no nombres de dominio. Usa un paquete por segundo, hasta 20 paquetes y un límite de 20 segundos; el reporte llega al terminar y muestra la salida, paquetes, pérdida y latencias. La espera en cola puede añadir tiempo.

POST `/pagos/ping/` con `{"address":"192.168.1.146"}` devuelve `ping_token`. GET `/pagos/ping/<ping_token>/` devuelve pending/running/completed/failed. `completed` contiene `status` completed/error para el resultado del comando. Ambos requieren autenticación. Tokens ligados al usuario, resultados expiran en 15 minutos y solo se admite un ping simultáneo. No modifica registros ni configuración de equipos; escribe únicamente estado temporal en Redis. El comando usa argumentos separados sin shell y valida IP en servidor.

Requiere Redis, Celery, iputils-ping y NET_RAW (ya presentes en Dockerfile/compose). No requiere migraciones. Desplegar web y worker juntos:

```sh
docker compose up -d --build django-web celery-worker
```

Pruebas: `python manage.py test pagos.test_ping_probe`. Las pruebas simulan subprocess; la conectividad real se valida desde el servidor.
