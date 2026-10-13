# Cancelación de programación STM32 — v1.3.71

En Programación R1/R3, seleccionar la estación y pulsar **Detener y cancelar programación**. Cancela los trabajos pendientes de esa estación; si está grabando, solicita al agente cerrar el proceso J-Link de ese trabajo. El bloqueo permanece hasta que el agente confirma que terminó. No afecta trabajos de otras estaciones ni cancela Pruebas TQT COM/BLE.

El botón sigue disponible mientras se programa y puede usarse sin una placa seleccionada. Al abrir la sección se recupera el trabajo activo de la estación, con su progreso. Un trabajo cancelado queda en historial y nunca registra firmware verificado, incluso si después llega un resultado de verificación. Si se detuvo durante la escritura, comprobar la tarjeta y volver a prepararla antes de repetir.

Contrato: POST /api/stm32/stations/{sid}/cancel requiere sesión de operador y protección de origen. Una cola pendiente pasa a cancelled; un trabajo running conserva ese estado y cancel_requested hasta el resultado del agente. POST /api/stm32/agent/jobs/{jid}/control requiere bearer del propietario; comunica la cancelación y renueva el heartbeat mientras J-Link trabaja. El agente solo termina el proceso que él creó, conserva la evidencia local y no repite grabaciones al reintentar un reporte.

Requiere agente STM32 v1.3.71. Los agentes de esta laptop fueron actualizados en %LOCALAPPDATA%/TQT/STM32Agent, con copia previa agent_pre_1371.py y configuraciones privadas conservadas. Para otras laptops actualizar el agente antes de usar cancelación en una grabación activa. El agente COM/BLE de Test Station es independiente y su heartbeat no anuncia presencia de J-Link.

## Incidente y evidencia

- R3 0039 estaba bloqueada por trabajo queued fbfa860f35229109b8d843276f6ede23 en estación 10bdf456ab4857f132646b40; fue cancelado a solicitud del usuario y quedó registrado en Movimientos. No había grabación activa.
- Estación de la pantalla «Lap Leo 13-10-2026»: a067f7abc49096cc65a520ce. Online confirmada después de actualizar el agente. Se corrigió el acceso a campos R2 inexistentes al recibir una R3.
- 29 pruebas STM32 correctas, incluidas cancelación antes/durante Commander simulado, propiedad/autenticación, reintento tardío sin actualizar firmware, bloqueo hasta confirmación y vencimiento de cola. 11 pruebas de integración TQT correctas.
- Playwright verificó el botón en R3 y su endpoint real en Docker local, mensaje de cancelación y vista móvil de 390 px sin desbordamiento después de completar el cambio de tamaño. No se ejecutó una nueva grabación física para esta verificación.
- Producción v1.3.71: commit de aplicación 4c9b4c14c8d3f20dbe33502a0dd3c514b9c281d1. Contenedor healthy, API pública ok, SQLite integrity_check=ok, cero trabajos activos al cierre.
- Respaldo previo: /home/orangepi/escanertqt/servidor/data/respaldos/pre-tqt-1371-20261013T233704Z. Código y SQLite respaldados y SHA256 registrados; no se modificó Compose ni Cloudflare.
- Capacidad ECC backend aplicada para revisar estados y persistencia; verificaciones ejecutables y simulador de proceso confirmaron la exclusión entre cancelación y registro de firmware.
