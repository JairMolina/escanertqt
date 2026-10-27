# Cierre de agentes y actualización 1.4.47 — 2026-10-27

## Base verificada y alcance

Usuario solicitó comprobar el último Git, aplicar el pendiente con versión nueva, guardar Git/memoria y desplegar. `origin/main` y OrangePi estaban limpios en `04676c5`, web 1.4.46. La rama anterior `codex/gestionar-agentes-20261026` / `0ca9d86` ya es antecesora de main: no se repiten ni sobrescriben sus funciones. Se parte de main en `codex/cierre-agentes-20261027`.

Servidor: `/home/orangepi/escanertqt`, SSH por MiniPc a `orangepi@192.168.4.70`, Compose `servidor/compose.yml`. La asociación del agente corresponde al usuario de la **web TQT**, confirmada por el usuario. Se conserva propietario de registro separado del operador que inicia cada trabajo.

## Limpieza comprobada

La consulta actual encontró 20 registros físicos ya revocados, cero agentes vigentes, un banco lógico de navegador y cero trabajos STM32/pruebas/comandos/verificaciones R2 activos. Auditoría de retirada: cuenta developer4, 2026-10-26 23:44–23:45 UTC. Son acciones previas; esta sesión no volvió a revocar los registros.

En esta laptop sí quedaban duplicados: cuatro procesos Python con rutas exactas de agentes TQT, seis accesos de inicio y siete carpetas (cinco STM32Agent, una TestStationAgent y un entorno BLE auxiliar). Se verificaron los destinos absolutos dentro de las raíces previstas antes de mover, se detuvieron únicamente esos cuatro procesos y se pusieron carpetas/accesos en cuarentena privada bajo `%LOCALAPPDATA%/TQT/RemovedAgents/20261027_091731`. No se eliminó código, credenciales OTA/R2, LocalWeb ni DYMO. El respaldo privado no se incluye en Git ni se transmite a memoria central.

No se crea un agente nuevo automáticamente. Para volver a programar, iniciar sesión en la web e instalar **uno** desde la configuración del equipo. Su nombre incluirá la cuenta web; el historial identifica al operador de cada trabajo. Las instalaciones de otras laptops solo tienen sus credenciales revocadas; la web no desinstala sus archivos Windows.

## Verificación y despliegue

Verificación local aprobada: 122 pruebas Python en bases aisladas, 9 pruebas Node de Comandos y 15 grupos Playwright de borrado/agente fijo/estado STM32. Móvil390 sin desborde y sin erroresJS; ComposeQA y revisión de diff correctos. El respaldo SQLite nuevo, la comprobación de actividad, el fast-forward y la recreación exclusiva de tqt se completaron como se registra abajo. No se modificó el túnel ni la infraestructura compartida.

La actualización conserva FW4.4 beta pendiente de banco físico y aprobación humana. No realiza grabaciones, lecturas de sondas, resets de tarjetas ni movimientos del banco.

## Resultado observado

Desplegada 1.4.47, commit de código 23a7d8da8ae35030497b296a0488310dceec9b31, publicado por fast-forward en main y rama de tarea. OrangePi actualizado desde 04676c5 limpio. Solo se recreó tqt; cloudflared continuó activo. Se reutiliza la imagen vigente: no cambian dependencias y la aplicación se monta en lectura desde el checkout.

Respaldo /backups/predeploy_1.4.47_20261027_092049.db; integrity_check=ok; SHA256 d51ad4340fb1e321341685fb46e7b4ce067e2167ec6ef37b0551403b7fa44b11. Cero trabajos activos al respaldar.

Comprobado: contenedor running healthy, APP_VERSION1.4.47, SQLite quick_checkok, salud interna/pública ok:true y login público HTTP200 con versión1.4.47. Conteos idénticos antes/después:94 trabajosSTM32,50 pruebas,239 comandos,446PCB,100tarjetas,1883escaneos,20registros físicos revocados,0agentes vigentes y1banco lógico. No se borraron ni reescribieron historiales.

Laptop comprobada:0procesos de agentes y0arranquesTQT; carpetasSTM32/TestStation vacías; respaldo privado existente; LocalWeb/R2 preservados. La limpieza solicitada está completa. Instalar un solo agente nuevo con la cuenta web cuando se necesite programar.

CM para checkpoint y sincronización documental; Git nativo en checkout aislado para preservar cambios del checkout registrado. ECCbackend/seguridad/verificación y pruebas existentes para permisos, revocación y regresiones. Respaldos SQLite y credenciales quedan fuera de Git/memoria.
