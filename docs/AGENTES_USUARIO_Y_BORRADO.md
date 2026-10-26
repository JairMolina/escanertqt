# Agentes por cuenta web y retirada segura — 1.4.44

Solicitud: limpiar todos los agentes físicos existentes, retirar las instalaciones duplicadas de esta laptop y permitir borrar agentes desde Programación. El usuario aclaró que la asociación corresponde a la cuenta de la web TQT, no al usuario de Windows.

## Comportamiento

- El registro toma el propietario de la sesión autenticada del servidor. Nombre nuevo: `usuario · nombre del equipo`; el selector muestra también el correo y el ID para distinguir equipos del mismo usuario. La cuenta se indica en la configuración del instalador sin pedir contraseñas adicionales.
- Quien inicia cada operación queda en `operator`, aunque utilice un agente registrado por otro usuario. Los trabajos STM32 nuevos guardan además una instantánea del ID, nombre y cuenta de registro del agente. La API de historial de pruebas expone ambos actores.
- R1/R3 tienen «Borrar agente» junto al selector fijo. Confirmación con nombre/ID; solo propietario o administrador. Las cuentas de consulta no pueden borrar.
- El servidor comprueba en una transacción grabaciones STM32, pruebas, comandos recientes, verificaciones R2 y reservas BLE de pruebas web. Responde 409 si están ocupados. La interfaz conserva la selección si se rechaza y la limpia después de un borrado correcto.
- Borrado lógico: `revoked_at` y `revoked_by`; permanecen las filas referenciadas por historiales. El token retirado devuelve HTTP410 y no puede recibir trabajos. Los clientes nuevos se detienen al recibir 410; los clientes antiguos no se desinstalan remotamente.
- Los bancos lógicos `web-*` son parte del historial del navegador y no son agentes de Windows: se conservan. Tampoco se afectan DYMO, firmware, inventario ni credenciales OTA.

## Evidencia local

122 pruebas Python aprobadas (incluida migración de una base antigua mientras otro escritor mantiene el bloqueo), con bases temporales aisladas. Incluyen permisos, revocación de tokens, operaciones activas, reserva BLE entre comandos, conservación de referencias, retirada atómica, actor de operación distinto del propietario y configuración del instalador. Actualizada la prueba de versión visible que todavía esperaba 1.4.39.

Playwright: cuatro grupos nuevos de borrado y once grupos de regresión (agente fijo y estado histórico) aprobados. Sin errores JS; móvil 390 sin desborde. Agentes y trabajos simulados; ninguna tarjeta programada ni movimientos físicos. Configuración Compose QA, sintaxis JS y revisión de diff correctas. Capacidades usadas: ECC backend, seguridad y verificación para transacciones, permisos y comprobaciones; continuidad documental CM.

## Estado de aplicación

Preparado sobre producción 1.4.43 / `38e1746d0627b82fe98d9bd7875e947c4eaecafa`, comprobada sin cambios remotos al preparar esta corrección. QA aislada: `http://127.0.0.1:18089/monitor#/programacion`.

Inventario de mantenimiento: 19 agentes físicos registrados; 0 trabajos activos al inspeccionar. Laptop: cinco instalaciones STM32 y una instalación TestStation, seis accesos de inicio automático; cuatro procesos STM32 activos observados. También existe el entorno auxiliar `.tqt/BLE-Preview142`. Estos conteos son diagnóstico, no afirman borrado ejecutado.

Pendiente: autorización expresa de despliegue según AGENTS.md, respaldo SQLite previo y nueva comprobación de trabajos activos. Después aplicar la retirada de todos los agentes físicos mediante `revoke_stations` y verificar que no cambió ningún historial. Detener solo procesos locales con rutas exactas de esos agentes y mover sus carpetas/accesos a cuarentena privada fuera de Git y CM; conservar LocalWeb, R2, DYMO y entornos de firmware. No crear automáticamente una estación nueva: el usuario instalará una sola con su cuenta cuando corresponda.
