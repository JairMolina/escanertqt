# Despliegue verificado de Pruebas TQT — 2026-10-13

El usuario autorizó publicar en GitHub, desplegar en la web y guardar la memoria. Versión de aplicación 1.3.70, commit `41ed4f27aeedff6248c31edef86ae8904829d0de`, en `JairMolina/escanertqt` main. Web: https://inventariotqt.site/monitor#/validacion.

## Destino y procedimiento real

Orange Pi `192.168.4.70`, usuario `orangepi`, repositorio `/home/orangepi/escanertqt`. SSH mediante salto `MiniPc`. Tailscale `100.115.212.105` no respondió; se reutilizó la red LAN documentada. No modificar la red para resolver esta desconexión. El acceso histórico de devsky corresponde a la instalación anterior.

Repositorio de producción limpio, base inicial `4bfbc88`, Compose existente validado. Sin trabajos STM32 activos antes de actualizar. El paquete Git contiene solamente commits posteriores a esa base; se verificó el SHA contra GitHub main antes de aplicar un avance directo. Se conserva la configuración privada de servidor y todos sus montajes.

Respaldo previo: `/home/orangepi/escanertqt/servidor/data/respaldos/pre-tqt-1370-20261013T212830Z/`. Contiene `source.tar.gz`, `produccion.db`, `SHA256SUMS`, `previous_commit.txt` y registro del avance Git. SQLite creada mediante backup en caliente y `integrity_check=ok`; SHA256 registrado antes de la actualización.

Se reinició únicamente `escanertqt-tqt-1`. No se reconstruyó la imagen porque app y station ya están montadas desde el repositorio y no cambiaron dependencias. No se modificó ni reinició el contenedor Cloudflare, ni Compose, puertos o servicios compartidos.

## Verificación

- Contenedor web saludable; API pública `/api/health` devuelve `{"ok":true}`.
- Runtime de producción devuelve versión 1.3.70 y las cuatro tablas nuevas `tqt_test_*`.
- Comparación de las 22 tablas previas contra el respaldo: solo `stm32_stations` cambió por los heartbeats del agente existente; tarjetas, PCB y los demás datos anteriores permanecieron iguales. 100 tarjetas y 300 PCB.
- Repetición de los 11 casos de integración en Docker local: correcta. Evidencia física previa: dos ejecuciones independientes de R1 0036 / COM10 / R2 0077, 14/14 aprobadas. No se ejecutó un tercer ciclo durante el despliegue.
- La página pública requiere iniciar sesión. La verificación visual e interacciones completas se hicieron previamente en Docker local; después del despliegue se verificaron servidor, API pública y autenticación real del agente.

## Agente de esta laptop

Instalado en `%LOCALAPPDATA%\TQT\TestStationAgent\10bdf456ab4857f132646b40`, con los módulos originales y la credencial de la estación ya autorizada «Laptop TQT · developer4». No contiene credenciales nuevas en Git. Reutiliza Python del banco 0.6.3. Agente online confirmado por el servidor; COM y BLE desconectados y sin ejecución activa.

Acceso directo `TQT Pruebas - developer4.lnk` en Inicio de Windows: pythonw en segundo plano, sin consola. Diagnóstico `agent.log`; evidencia y cola durables en `evidence/`. Para otra laptop se usa Descargar agente de pruebas desde la web y el inicio incluido en el ZIP privado. No compartir el ZIP personalizado ni config.json.

Las pruebas y registros de desarrollo siguen en el volumen local independiente. No se copiaron usuarios locales, base de desarrollo ni reportes de prueba al inventario de producción. Los nuevos registros de producción se crean al ejecutar desde esa web.

## Recuperación

Antes de revertir, comprobar que no hay prueba/programación activa. El respaldo conserva la versión anterior y datos previos; la aplicación anterior puede funcionar con las tablas adicionales sin borrarlas. Preparar la reversión de código en una rama y verificar el diff, luego reiniciar solo la web. Restaurar SQLite requiere una autorización específica si reemplaza evidencia posterior; no hacerlo automáticamente y no borrar volúmenes. No usar `git reset --hard` ni modificar el túnel para revertir.
