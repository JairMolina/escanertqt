
## 2026-10-13 20:27 UTC | 4bfbc88aa104
Avance: Pruebas TQT 0.6.3 integradas solo en Docker local; dos pruebas físicas R1 0036 COM10/R2 0077 aprobaron 14/14 con historial independiente y LOG completo; inventario original intacto.
Siguiente: Mantener desarrollo local; revisar deuda de regresión Linux preexistente y no publicar/desplegar sin autorización.
Evidencia: docs/PRUEBAS_TQT_LOCAL.md; 41 simuladores originales, 11 pruebas TQT y 22 STM32 correctas; SHA256 LOG igual entre Windows y web; baseline 610 vs integración 618 sin fallos nuevos.

## 2026-10-13 21:14 UTC | 3ca48b5d0318
Avance: Integracion local terminada en codex/tqt-test-station: commits 3129648 y 3ca48b5. Agente Windows oculto y Docker saludable en localhost:18080. Dos pruebas fisicas independientes de R1 0036 / COM10, 14/14 aprobadas, inventario original conservado. Reporte con JSON, LOG original y PDF; sensores S29 interpretados.
Siguiente: Revision del usuario en Docker local. No publicar ni desplegar sin autorizacion. Deuda de regresion previa documentada.
Evidencia: 41 pruebas originales, 11 de integracion y 22 STM32 correctas. Comparacion de regresion sin nuevos fallos; interfaz movil sin desborde y PDF de 7 paginas verificado. LOG web y original SHA256 identicos.

## 2026-10-13 21:32 UTC | 41ed4f27aeed
Avance: v1.3.70 publicada en GitHub main y desplegada en inventariotqt.site por autorizacion expresa. Commit de aplicacion 41ed4f2; Orange Pi 192.168.4.70 via MiniPc, /home/orangepi/escanertqt. Agente developer4 online, oculto y con inicio automatico. Respaldo pre-tqt-1370-20261013T212830Z verificado.
Siguiente: Uso operativo desde la web publicada; conectar COM/BLE y ejecutar solo cuando el banco este libre. Deuda de regresion previa documentada; no se realizaron movimientos adicionales durante el despliegue.
Evidencia: Contenedor healthy, API publica ok, runtime 1.3.70, cuatro tablas nuevas. 100 tarjetas y 300 PCB intactas; 22 tablas anteriores comparadas, solo heartbeat de estaciones cambia. 11 casos de integracion correctos; dos pruebas fisicas previas 14/14.

## 2026-10-13 23:39 UTC | 4c9b4c14c8d3
Avance: v1.3.71 desplegada: boton Detener y cancelar programacion STM32, recuperacion del trabajo al recargar y correccion del agente R3. Trabajo pendiente de R3 0039 cancelado sin grabacion; estacion Lap Leo 13-10-2026 online con agente actualizado. Commit aplicacion 4c9b4c1.
Siguiente: Recargar web con Ctrl+F5 y usar estacion Lap Leo 13-10-2026. Otras laptops requieren agente actualizado para detener J-Link activo; no se ejecutaron nuevas grabaciones fisicas.
Evidencia: 29 pruebas STM32 y 11 TQT correctas; Playwright comprobo boton y cancelacion en Docker local. Produccion healthy, API ok, SQLite ok, cero trabajos activos. Respaldo pre-tqt-1371-20261013T233704Z. ECC backend para estados y persistencia.

## 2026-10-14 00:31 UTC | cdad30fa90f6
Avance: v1.3.72 desplegada: catalogo persistente HEX R1/R3, selector del firmware compatible mas reciente y trabajos fijados a la version elegida. Commit aplicacion cdad30f; produccion saludable y catalogo solo R1 4.3 / R3 1.0. V1.1 aportado usado solo para validar y cancelado antes de guardarlo.
Siguiente: Recargar la web y usar Subir HEX > confirmar HW/FW > Guardar firmware. El usuario elegira que archivos registrar; no cargar automaticamente el V1.1 aportado para prueba.
Evidencia: 37 casos STM32/catalogo y 11 TQT correctos. Playwright valido selector, formulario, cancelacion de prueba V1.1, duplicado, persistencia tras recrear Docker y movil 390 px sin desborde. Respaldo pre-tqt-1372-20261014T002844Z, SQLite ok, 100 tarjetas y 300 PCB. ECC backend y seguridad.

## 2026-10-14 19:44 UTC | cdd39b11115b
Avance: R2 FW4.0 y web1.3.73 preparados en codex/esp32-r2-v4 desde GitHub cdd39b1. Catalogo persistente BIN/HEX ESP32 con perfil interno HW/FW, nombre desde inventario, selector mas reciente compatible y verificacion INFO. Copia TQT_R2_V4_0_14_10_2026 creada junto al original intacto. Orange Pi recuperada por reinicio segun usuario; produccion no modificada.
Siguiente: Desplegar rama aprobada en Orange Pi por peticion expresa y validar V4.0 en una R2 fisica autorizada. No programar plantilla 0000 directamente. La instancia LAN de recuperacion y su BD se conservaron; preview separado solo contiene registros e imagenes simulados.
Evidencia: Arduino core3.3.12: compilacion y script exportador BIN/HEX correctos, 1105967 bytes (84%) y RAM41660 (12%). Esptool5.3.1 valido checksum/SHA del binario personalizado. 14 tests ESP32, 37 STM32/catalogo y 13 programacion lote OK. Playwright: BIN/HEX, cancelar/guardar, 4.10>4.9, version anterior, HW incompatible, rechazo FW discordante y MAC duplicada, flujo serial simulado exitoso, persistencia tras recrear, Tab/Escape y movil390 sin desborde. Compose y node --check OK. Original e3bb4e47a701 respaldado en MiniPC, 0 pendientes. ECC HW/FW, CPP, backend, seguridad y verificacion; ui-ux-pro-max.

## 2026-10-14 20:12 UTC | 0e8bedcf1157
Avance: Web1.3.76 desplegada en Orange Pi desde GitHub codex/esp32-r2-v4, commit aplicacion 0e8bedc. Integra R2 V4.0 con catalogo BIN/HEX/nombre de inventario y conserva cambios de produccion1.3.73-1.3.75 de semaforo, Pruebas y estacion J-Link local. Montaje R2 readonly; solo servicio tqt recreado. Catalogo real R2 FW4.0/HW3.0.
Siguiente: Validar R2 V4.0 en hardware cuando el usuario indique tarjeta y autorice prueba. No se programo ninguna placa durante despliegue. GitHub/prod usan rama codex/esp32-r2-v4; main GitHub sigue separado. Instancia LAN recuperacion y originales intactos; vista previa aislada se detiene al cerrar.
Evidencia: API local/publica HTTPS200 version1.3.76; imagen R2 0013 preparada/validada sin grabar, perfil4.0/3.0/nombre correcto; HTML/JS cache1376. Contenedor healthy, cloudflared sin reinicio. SQLite integrity ok y hashes identicos de100 tarjetas/300PCB/7usuarios. Respaldo pre-r2-v4-1376-20261014T200710Z.db SHA d665ad29f0d8064d45c7164f46bc2f895b0fc50909cf23f241c0c1fa31e9d424; compose previo20261014T200829Z. Integracion51 tests correctos (37STM32+14ESP32), node --check y Playwright preservan orden R2/R1/R3 y selector. Original R2 respaldado en MiniPC, 0 adjuntos pendientes. CM memoria/checkpoint; ECC verificacion.
