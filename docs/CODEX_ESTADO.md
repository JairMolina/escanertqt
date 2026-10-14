# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 19:44 UTC
Commit de referencia: `cdd39b11115b` (puede no incluir cambios pendientes)

## Avance reportado
R2 FW4.0 y web1.3.73 preparados en codex/esp32-r2-v4 desde GitHub cdd39b1. Catalogo persistente BIN/HEX ESP32 con perfil interno HW/FW, nombre desde inventario, selector mas reciente compatible y verificacion INFO. Copia TQT_R2_V4_0_14_10_2026 creada junto al original intacto. Orange Pi recuperada por reinicio segun usuario; produccion no modificada.

## Siguiente paso
Desplegar rama aprobada en Orange Pi por peticion expresa y validar V4.0 en una R2 fisica autorizada. No programar plantilla 0000 directamente. La instancia LAN de recuperacion y su BD se conservaron; preview separado solo contiene registros e imagenes simulados.

## Evidencia
Arduino core3.3.12: compilacion y script exportador BIN/HEX correctos, 1105967 bytes (84%) y RAM41660 (12%). Esptool5.3.1 valido checksum/SHA del binario personalizado. 14 tests ESP32, 37 STM32/catalogo y 13 programacion lote OK. Playwright: BIN/HEX, cancelar/guardar, 4.10>4.9, version anterior, HW incompatible, rechazo FW discordante y MAC duplicada, flujo serial simulado exitoso, persistencia tras recrear, Tab/Escape y movil390 sin desborde. Compose y node --check OK. Original e3bb4e47a701 respaldado en MiniPC, 0 pendientes. ECC HW/FW, CPP, backend, seguridad y verificacion; ui-ux-pro-max.
