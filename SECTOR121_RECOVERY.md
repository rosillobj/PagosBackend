# Recuperación automática del sector 121

Monitor Celery Beat cada cinco minutos. Opt-in con `SECTOR121_RECOVERY_ENABLED=true` en `.env.prod` tanto para worker como beat. No se ejecutó en equipos reales durante el desarrollo.

## Flujo

1. Dos pings cortos a `192.168.1.121`; basta una respuesta. Un error de ejecución/permisos de ping aborta y no equivale a una antena caída.
2. Si responde, corre la revisión anterior de los cuatro clientes del sector y su reinicio HTTPS, bajo el mismo bloqueo. Durante la hora posterior a un intento de recuperación, omite ese reinicio anterior.
3. Si no responde, valida primero el respaldo local, busca `.20` y autentica por SSH como `ubnt` con la contraseña inicial configurada (default `ubnt`).
4. Exige MAC `B4:FB:E4:5A:0E:0D`, modelo Rocket M2, sysid `0xe868` y firmware XW 6.x antes de cualquier modificación. La primera clave SSH se acepta en esta sesión solo tras estas comprobaciones; se exige la misma en las reconexiones. Es una comprobación de identidad operacional, no un anclaje criptográfico previo independiente.
5. Conserva la configuración actual de la antena en una clave privada de Redis `sector121:pre-restore:<id>`, por siete días. No hay endpoint HTTP para esa copia. Redis contiene material confidencial.
6. Si falta `/etc/persistent/ct`, ejecuta `touch /etc/persistent/ct && save`, reinicia y espera un arranque distinto con SSH listo durante un máximo de 30 segundos. Si el marcador ya existe, no repite el primer reinicio. La placa indica ~40 s de reinicio: el límite solicitado de 30 puede ser insuficiente; en ese caso se notifica y se detiene sin aplicar el respaldo.
7. Si `.121` volvió antes de escribir el respaldo, cancela para evitar duplicar IPs.
8. Transfiere el archivo a `/tmp/sector121-restore.cfg` mediante SSH/stdin (no requiere SFTP), comprueba MD5 de la transferencia dentro de la conexión SSH y ejecuta `cfgmtd -f /tmp/sector121-restore.cfg -w -p /etc/`. Un fallo de transferencia o del comando impide el siguiente paso.
9. Reinicia y espera hasta 60 s por `.121`, comprobando ping, SSH, MAC y nuevo boot ID. La verificación utiliza el usuario/contraseña restaurados configurados; por defecto, las credenciales existentes del sector 121 (`sector_credentials(121)`). Si el respaldo tiene otra contraseña, es necesario configurar la variable correspondiente.
10. Notifica recuperación, cancelación o fallo al usuario 1 de la app (configurable). No anuncia éxito solo por recibir ping. Suprime avisos idénticos por una hora; no envía avisos en cada consulta saludable.

Cada intento que inicia cambios tiene un enfriamiento de una hora, incluso si falla; el monitor sigue consultando cada cinco minutos. Esto evita reinicios/restauraciones repetidos mientras se revisa un fallo. Un bloqueo Redis con propietario coordina todas las operaciones del sector. Soft/hard time limits: 230/250 s; lock 280 s; entradas Beat expiran en 60 s para no acumular recuperaciones antiguas tras una caída del worker. La exclusión es entre estas tareas del backend; no coordina acciones manuales externas sobre la antena.

## Respaldo y variables

Ubicación confirmada en el servidor:
`/home/bercy/NewPagos/PagosBackend/Respaldo121/XW-B4FBE45A0E0D.cfg`.

El worker recibe `./Respaldo121` como bind mount **de solo lectura** en `/app/Respaldo121`. La carpeta debe existir; no se crea silenciosamente. Está excluida de Git y del contexto de construcción de Docker para no distribuir credenciales en imágenes.

Variables en `.env.prod` (no publicar credenciales):

```dotenv
SECTOR121_RECOVERY_ENABLED=false
SECTOR121_NOTIFY_USER_ID=1
SECTOR121_BACKUP_PATH=/app/Respaldo121/XW-B4FBE45A0E0D.cfg
# Opcionales: SECTOR121_DEFAULT_USER, SECTOR121_DEFAULT_PASSWORD,
# SECTOR121_RESTORED_USER, SECTOR121_RESTORED_PASSWORD.
```

El respaldo debe ser texto, hasta 1 MB, contener la IP `.121` en un `netconf.N.ip` y tener configuración `wireless.*`. Si declara modelo/MAC diferentes se rechaza. No se puede garantizar la compatibilidad completa de una configuración airOS solo con esas validaciones; usar únicamente el respaldo confirmado de esta Rocket M2, no archivos de otros dispositivos.

## Despliegue

1. Subir los cambios de código y actualizar el checkout del servidor. Conservar la carpeta privada Respaldo121 fuera de Git. Mantener inicialmente `SECTOR121_RECOVERY_ENABLED=false`.
2. Reconstruir worker y beat para instalar Paramiko y cargar el código, conservando el contenedor web y el proxy actuales:

```sh
cd ~/NewPagos/PagosBackend
test -f Respaldo121/XW-B4FBE45A0E0D.cfg
docker compose up -d --build --no-deps celery-worker celery-beat
```

3. Validar el respaldo sin conectar ni modificar antenas:

```sh
docker compose exec -T celery-worker python manage.py check_sector121_recovery
```

Si el worker no puede leerlo, ajustar **solo** esos dos objetos usando el GID real del contenedor (sin chown recursivo):

```sh
worker_gid=$(docker compose exec -T celery-worker id -g)
sudo chgrp "$worker_gid" Respaldo121 Respaldo121/XW-B4FBE45A0E0D.cfg
sudo chmod 750 Respaldo121
sudo chmod 640 Respaldo121/XW-B4FBE45A0E0D.cfg
```

4. Confirmar el usuario y contraseña que quedarán después de restaurar el respaldo. Verificar que el usuario de notificación tiene token Expo registrado. Cambiar `SECTOR121_RECOVERY_ENABLED=true` y recrear los servicios para tomar las variables:

```sh
docker compose up -d --force-recreate --no-deps celery-worker celery-beat
docker compose exec -T celery-worker python manage.py check_sector121_recovery
docker compose exec -T celery-worker celery -A pagosNew inspect ping --timeout=10
docker compose logs --since=5m --tail=100 celery-worker celery-beat
```

Al activarse se sustituye la entrada Beat antigua de auto-reboot-121 por el monitor, que ejecuta la revisión antigua cuando el sector está saludable. La tarea antigua sigue registrada, pero no ejecuta cambios por separado cuando la recuperación está activada. El sector 127 permanece igual.

No hacer una prueba real bajando el sector: inspeccionar primero la validación local y los logs del siguiente ciclo saludable. Para ver el estado público sin contraseñas:

```sh
docker compose exec -T celery-worker python manage.py shell -c 'from pagos.traffic import storage; print(storage().get("sector121:recovery:status"))'
```

No ejecutar `FLUSHALL`, ni borrar bloqueos/cooldowns de una operación activa. Para desactivar: poner la variable en false y recrear worker y beat; la revisión antigua vuelve a programarse.

## Validación

`python manage.py test pagos.test_sector121_recovery`

Pruebas simuladas de flujo, plazos, identidad, checksum, flash, conservación del backup, exclusión mutua, enfriamiento y coordinación con la tarea anterior. Falta validar SSH/comandos/credenciales y el respaldo real en la red de producción; ninguna prueba de desarrollo tocó antenas ni envió notificaciones.
