# Memoria de TQT-Web

## Estado vigente — 2026-10-27

Web1.4.49 publicada enmain ydesplegada conautorización,códigoa1ea3d5,
sobre1.4.48/2fa6fd2. Diagrama debajo deComandos:secciónnativa con
armazón/fuentes/temas,HW20/HW30,6grupos,SVG/fichas,búsqueda,comparación,
láminas yAK7V. Datos19/18referencias y6JPEG delHTML conservados conhash;
noiframe ni appindependiente. Consultor puedeleer;marcasporHW solo en
navegador/exportJSON,no escribenPruebasTQT ni inventario.0accioneshardware.
13gruposPlaywright+16Node+7PythonPASS;claro/oscuro1440/1024/390,0errores,
permisos/confidencialidad,export/recarga ydesmontaje comprobados.
Producciónhealthy/quick_checkok/login1.4.49;catálogoanónimo401;archivosGit
=servidor y6JPEGverificados. Inventarioidéntico eIDshistóricos preservados;
1pruebaweb/5comandosnuevos concurrentes terminó;no fue ejecutada porDiagrama.
Backup/evidencia docs/DIAGRAMA_TQT.md. Abrir /monitor#/diagrama,Ctrl+F5.
Se conserva correcciónSTM32vigencia:0054FW4.4verde,0055FW4.3naranja frente
vigenteaprobado4.4. Esta tarea no cambiaaprobacionesFW ni prueba tarjetas.
OrangePi porMiniPc aorangepi@192.168.4.70,repo/home/orangepi/escanertqt;
solo tqt recreado,cloudflared intacto. Limpiezaagentes anterior completa.

Aplicación Inventario TQT (JairMolina/escanertqt): FastAPI, SQLite, WebSockets y HTML/JS. Mantener separada de TQT-OrangePi, que contiene infraestructura del servidor.

## Estado confirmado 2026-10-13

Versión 1.3.72 publicada en GitHub main y desplegada, por autorización expresa del usuario, en https://inventariotqt.site. Commit de aplicación cdad30fa90f61b5a471cff394ff42f7c1bacb047. Integra Test Station 0.6.3 en validacion y catálogo HEX, selección de firmware y cancelación STM32 en programacion. Se conserva Docker local de esta laptop, puerto loopback 18080 y volumen independiente con copia íntegra del inventario: 100 tarjetas y 300 PCB. Agente Windows saliente para COM/BLE; cinco módulos originales idénticos en SHA256, tiempos y 14 etapas conservados.

Dos pruebas físicas R1 0036 / COM10 / R2 0077 finalizaron 14/14 aprobadas, cada una con ID e historial independiente. Reportes con cotejo de inventario, JSON y LOG íntegro; las pruebas no autorizan liberar tarjetas. Datos originales de tarjetas, PCB e historial de fabricación permanecen idénticos.

## Accesos y límites

Web local http://localhost:18080/monitor#/validacion. Instrucciones y evidencias en docs/PRUEBAS_TQT_LOCAL.md. Base, respaldo, credenciales y reportes reales fuera de Git. CM preservó los originales aportados en almacenamiento privado central; no se indexan binarios ni bases.

Servidor actual: Orange Pi en 192.168.4.70, usuario orangepi, repositorio /home/orangepi/escanertqt; acceso SSH por salto MiniPc. Tailscale de Orange Pi aparece offline. La ruta antigua devsky fue sustituida durante la restauración anterior: no desplegar en ella. Respaldo previo de código y SQLite: servidor/data/respaldos/pre-tqt-1370-20261013T212830Z; integridad y SHA256 verificados. Se reinició solo escanertqt-tqt-1; no se cambió Cloudflare ni Compose del servidor.

Agente de producción instalado en %LOCALAPPDATA%/TQT/TestStationAgent/10bdf456ab4857f132646b40, reutiliza la estación autorizada Laptop TQT · developer4. Credencial privada fuera de Git; inicio automático con pythonw oculto. COM y BLE desconectados al cerrar el despliegue, sin ejecutar nuevos movimientos. Las dos pruebas de desarrollo permanecen en la copia local; no se importaron como pruebas de producción.

Hay deuda de regresión preexistente en pruebas Linux; la comparación con GitHub no encontró fallos nuevos. Consulte docs/DESPLIEGUE_TQT_1370.md y la guía local antes de reiniciar/restaurar; revise la tarjeta físicamente antes de repetir una ejecución interrumpida.

Corrección 1.3.71: trabajo fbfa860f35229109b8d843276f6ede23 de R3 0039 cancelado en espera a petición del usuario, sin grabaciones activas. Agente de pruebas COM/BLE ya no actualiza el heartbeat de programación STM32: no confundir online de pruebas con J-Link. Estación J-Link efectiva «Lap Leo 13-10-2026» (a067f7abc49096cc65a520ce) online; agentes STM32 instalados en esta laptop actualizados. Botón «Detener y cancelar programación» y recuperación del trabajo tras recargar. Respaldo pre-tqt-1371-20261013T233704Z. Ver docs/CANCELACION_STM32.md.

Catálogo 1.3.72: tabla persistente stm32_firmwares, subida validada con confirmación HW/FW R3, selector de la versión más alta compatible y snapshot inmutable en cada trabajo. R1 usa perfil interno y personalización por inventario. Respaldo de despliegue pre-tqt-1372-20261014T002844Z. 37 casos STM32/catálogo y 11 TQT correctos; Playwright verificó formulario y selector, duplicados, reinicio Docker y móvil. V1.1 aportado se usó solamente para validación y el formulario se canceló: no está registrado localmente ni en producción, ni se programó una tarjeta. Producción conserva solamente R1 4.3 y R3 1.0 al cierre; el usuario puede subir sus HEX después. Ver docs/CATALOGO_FIRMWARE_STM32.md.

## Despliegue verificado 2026-10-28

Producción TQT-Web 1.4.63, código 985d0d3, comprobado contra GitHub. Cierre verificable en docs/DESPLIEGUE_1.4.63_20261028.md. El borrador de los cinco bloques de Pruebas TQT permanece en codex/validacion-paneles-20261027 (work/tqt-fw-beta-20261026), incompleto y sin desplegar. No confundir ese pendiente con el despliegue del último Git. Usar main reciente para retomar y conservar cambios de terceros.
