# Cierre de agentes y actualización 1.4.47 — 2026-10-27

## Base verificada y alcance

Usuario solicitó comprobar el último Git, aplicar el pendiente con versión nueva, guardar Git/memoria y desplegar. `origin/main` y OrangePi estaban limpios en `04676c5`, web 1.4.46. La rama anterior `codex/gestionar-agentes-20261026` / `0ca9d86` ya es antecesora de main: no se repiten ni sobrescriben sus funciones. Se parte de main en `codex/cierre-agentes-20261027`.

Servidor: `/home/orangepi/escanertqt`, SSH por MiniPc a `orangepi@192.168.4.70`, Compose `servidor/compose.yml`. La asociación del agente corresponde al usuario de la **web TQT**, confirmada por el usuario. Se conserva propietario de registro separado del operador que inicia cada trabajo.

## Limpieza comprobada

La consulta actual encontró 20 registros físicos ya revocados, cero agentes vigentes, un banco lógico de navegador y cero trabajos STM32/pruebas/comandos/verificaciones R2 activos. Auditoría de retirada: cuenta developer4, 2026-10-26 23:44–23:45 UTC. Son acciones previas; esta sesión no volvió a revocar los registros.

En esta laptop sí quedaban duplicados: cuatro procesos Python con rutas exactas de agentes TQT, seis accesos de inicio y siete carpetas (cinco STM32Agent, una TestStationAgent y un entorno BLE auxiliar). Se verificaron los destinos absolutos dentro de las raíces previstas antes de mover, se detuvieron únicamente esos cuatro procesos y se pusieron carpetas/accesos en cuarentena privada bajo `%LOCALAPPDATA%/TQT/RemovedAgents/20261027_091731`. No se eliminó código, credenciales OTA/R2, LocalWeb ni DYMO. El respaldo privado no se incluye en Git ni se transmite a memoria central.

No se crea un agente nuevo automáticamente. Para volver a programar, iniciar sesión en la web e instalar **uno** desde la configuración del equipo. Su nombre incluirá la cuenta web; el historial identifica al operador de cada trabajo. Las instalaciones de otras laptops solo tienen sus credenciales revocadas; la web no desinstala sus archivos Windows.

## Verificación y despliegue

Verificación local aprobada: 122 pruebas Python en bases aisladas, 9 pruebas Node de Comandos y 15 grupos Playwright de borrado/agente fijo/estado STM32. Móvil390 sin desborde y sin erroresJS; ComposeQA y revisión de diff correctos. Pendiente respaldo SQLite nuevo, nueva comprobación de actividad, fast-forward de producción y recreación exclusiva del servicio `tqt`. No se modificará el túnel ni la infraestructura compartida. Se registrará aquí el resultado observado; todavía no se declara desplegada.

La actualización conserva FW4.4 beta pendiente de banco físico y aprobación humana. No realiza grabaciones, lecturas de sondas, resets de tarjetas ni movimientos del banco.
