# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 21:19 UTC
Commit de referencia: `f7fb240fb3f5` (puede no incluir cambios pendientes)

## Avance reportado
R2 FW4.1 y web1.3.77 implementadas: OTA Bluetooth autenticada/cifrada por unidad, instalacion serial inicial, catalogo y verificacion de reinicio/particion, cancelar y recuperar resultado pendiente. Proyecto V4.1 independiente con BIN/HEX, V3.1/V4.0 intactos. Todavia sin desplegar ni programar hardware.

## Siguiente paso
Autorizacion expresa para desplegar web1.3.77 en Orange Pi segun AGENTS.md; despues prueba R2 0069/COM3. Usuario sostiene contactos: avisar solo al estar listo; no abrir puerto antes de LISTO. Produccion sigue1.3.76/f7fb240; main separado. No se detecta adaptador serial conectado al consultar Windows.

## Evidencia
Arduino ESP32 core3.3.12:1130943 bytes86%,RAM42196 12%; rollback SDK y simbolo verifyRollbackLater nativo. BIN1196624 SHA3b1c3a42e51b99cc91bf770780d287f5c6604787d83eee9dced8224e97c9d08a; checksum/SHA nativos y HEX identico. Docker78 pruebas correctas(28ESP32/OTA+37STM32+13lote),node--check,diff--check. Playwright contexto aislado: envio6285paquetes,2jobsverificados(incluye recuperacion trasHTTP503),1cancelado;V4.0sinOTA;escritorio1366/movil390sin desborde. Solo DB sintetica. CM checkpoint/Git/memoria;ECC HW-FW/CPP/security/verification.
