# Indicador de vigencia STM32 — 1.4.48, 2026-10-27

Problema: el panel derecho se ponía verde por existir una grabación verificada, incluso si esa grabación llevaba FW4.3 y ya había FW4.4 aprobado. La lista sí avisaba «Desactualizada». La evidencia histórica era correcta; el color confundía verificación con vigencia.

R1/R3 usan ahora la misma comparación numérica para lista y panel: instalada frente a la versión aprobada más alta del mismo hardware. Historial verificado vigente: verde. Firmware anterior: naranja con texto «Desactualizada». Se muestran las versiones instalada/vigente. Sin catálogo confirmado no se asegura vigencia; sin firmware sigue rojo. Intentos posteriores sin verificar y errores conservan sus advertencias.

Elegir otro firmware a programar no cambia el contenido histórico ni el estado de actualización. Las imágenes beta y las de otro HW no elevan la versión vigente. No se cambia la API, el inventario, el agente, los trabajos ni los firmwares.

Evidencia aislada: 8 grupos nuevos Playwright (colores CSS renderizados naranja/verde, instalado/vigente, selector independiente, beta/otroHW, resultado incierto, catálogo caído, sinFW y R3), 5 grupos de estado histórico y 6 de agente fijo; todos PASS, sin erroresJS y móvil390 sin desborde. Solo los dos trabajos simulados de la regresión histórica; ninguna escritura a hardware real. 11 pruebas Python de versión/estado PASS, sintaxisJS, revisión de diff y ComposeQA correctos. ui-ux-pro-max: color acompañado de texto usando los componentes existentes; ECCverificación y suitePlaywright existente.

Base GitHub/producción comprobada: main454add0, web1.4.47, árbol limpio. Rama de esta corrección: codex/stm32-fw-indicador-20261027. La autorización expresa se recibió y se aplicó1.4.48;resultado debajo. No se aprueba firmware ni se programa ninguna tarjeta.

## Despliegue verificado

Usuario autorizó expresamente desplegar la corrección. Publicado código f608baf857dd0e023e6063d55110bdeb505a5ffc en main sobre454add0, fast-forward de OrangePi y recreación exclusiva de tqt;cloudflared continuó activo. Web1.4.48 runninghealthy, quick_checkok, salud interna/pública ok:true y loginHTTP200/version1.4.48.

Respaldo /backups/predeploy_1.4.48_20261027_093845.db, integrity_checkok, SHA256dcecdd6731321644cf646e2358f339d35b0c2658b300fd73e3a57baae6cc5845.0trabajos activos;conteos de inventario/historial idénticos antes/después:94trabajosSTM32,50pruebas,239comandos,446PCB,100tarjetas,1884escaneos,21registros de estaciones incluidos los lógicos.

Verificación solo de registros reales:0054 tiene última grabación verificada4.4 y vigenteaprobado4.4(verde);0055 tiene última grabación verificada4.3 y vigenteaprobado4.4(naranja). Ambas sin resultado físico incierto registrado. El catálogo ya marca4.4 aprobado; esta tarea no cambió aprobaciones ni comprobó un nuevo banco físico.

Los SHA256 del JS y CSS en Git coinciden con los archivos utilizados por producción:JS0dbebb2c115d864819f65e7932df8f4194459ca4f1227b76742afd55c09a203b;CSS5199c1523d7cc732269d889b36f0040a6d209a40c5d208e85fce09536383f730. Caché1448. RecargarCtrl+F5 para ver el ajuste.
