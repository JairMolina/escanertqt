# Estado de Codex: TQT-Web

Actualizado: 2026-10-16 19:45 UTC
Commit de referencia: `11cc0585dc43` (puede no incluir cambios pendientes)

## Avance reportado
Desplegada1.4.3 autorizada porusuario enOrangePi /home/orangepi/escanertqt commit11cc0585dc430208d1c1f2e83f3dd423e8badacf. Fastforward desde76d71a1 y recreate solo servicio tqt con servidor/compose.yml. Datos/volumenes/tunel conservados. Loginpublico confirma1.4.3 y apihealthOK.

## Siguiente paso
Revisar operacion de puente BLE Windows por usuario en produccion; pruebas fisicas previas locales14/14 no repetidas. UART28/99 lineas corruptas pendiente diagnostico. Previewlocal no reiniciado. Android/Skytec pendientes.

## Evidencia
Sin trabajos activos antes de despliegue; respaldo SQLite predeploy_1.4.3_20261016_134402.db en /backups servidor. ContenedorAPP_VERSION1.4.3 y arranqueOK; httpsinventariotqt.site/login muestra1.4.3, apihealthok. 502 transitorio durante arranque resuelto; recursosstatic protegidos requieren sesion. Pruebas previas24Python14JSUIpass.

## Nota operativa R2 (2026-10-16)

Documentado en R2_ALTA_GENERICA_42.md el inicio de programar_base.ps1 con ExecutionPolicy Bypass limitado al proceso. El usuario reporto bloqueo de PowerShell; no confirmo nueva grabacion. Se mantiene BIN generico4.0 fijo seguido de alta y OTA web con datos/credencial por unidad; evidencia previa0067 FW4.2. Sin cambios de codigo ni nueva prueba fisica.

## 2026-10-19 — Grabacion base R2 por BOOT

programar_base.ps1 conserva Manual/Enter predeterminado y agrega -Modo Automatico: escucha ROM 115200 hasta boot:0x3 + waiting for download completos, libera COM antes de esptool y espera nuevo BOOT tras cada escritura. Error de escritura automatica detiene sin reintento. BIN fijo y hash sin cambios. Copia actualizada en la carpeta offline real FW_GENERAL_4_0/TQT_R2_BASE_V4_0_GENERIC. Pruebas PowerShell5.1: sintaxis,8casosROM y flujo acumulado PASS; -Comprobar Manual/Automatico reales PASS sin abrirCOM4. No grabacion fisica; pendiente usuario probar nuevoBOOT con monitorserial cerrado. Documentacion en README del firmware. Produccion sigue1.4.3 sin nuevos despliegues.

## 2026-10-19 — Continuidad tras fallo de esptool

Sustituida detencion automatica por mensaje y retorno a espera de un nuevo BOOT+RESET. Mantiene sesion abierta; no reintenta escritura sin nuevo evento. Prueba simulada fallo -> esperaBOOT -> exito -> esperaBOOT PASS, ademas8casosROM y -Comprobar real sin abrir COM4. Script actualizado en carpeta offline. No interrumpida ni ejecutada grabacion fisica; el proceso ya abierto requiere reiniciar script una vez al finalizar escritura para cargar el cambio. Reemplaza decision anterior de detener por fallo. BIN y web sin cambios.
