# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 22:50 UTC
Commit de referencia: `b6b2aaa` (rama codex/r2-serial-monitor, desplegada)

## Avance reportado
Rama codex/r2-serial-monitor (sobre 1.3.78): v1.3.79 monitor serial R2, grabación serial a 921600 con respaldo 115200, eventos WS tras OTA verificada; R1 ESP32 con firmware fijo ESP32_BLE_SERIAL 1.0 (sin catálogo ni subida, sin borrar NVS) y candado de orden R2 MAC → STM32 R1 verificado → ESP32 R1. DESPLEGADA 2026-10-14 ~17:40 CST (servidor/compose.yml monta ../firmware/esp32_r1; respaldo del compose anterior fuera del repo).

## Siguiente paso
Probar en hardware R2 (monitor, polaridad RTS/DTR de «Reiniciar placa», grabación a 921600 con el adaptador USB–TTL real). Desplegar solo con autorización expresa. Despliegue requiere montar ../firmware/esp32_r1 en servidor/compose.yml (no versionado) o reconstruir imagen. R1 con STM32 grabado fuera del J-Link web quedan bloqueadas por el candado. Pendiente de decisión: semáforo STM32 (verde sin J-Link verificado) y si una tarjeta sin R3 debe mostrarse como R1/R2 programadas.

## Evidencia
pytest test_esp32_firmware, test_esp32_ota, test_api, test_db: 59 correctas, 1 falla ajena (test_17 certificado: certs/ ignorado en el worktree). node --check sec_programacion.js correcto. Sin prueba física.

## Anterior
Prueba OTA fisica0069 iniciada pero NO verificada: usuario aclara sigue Enviando, servidor job45226b5e1a6c36611ddf8b80 prepared con INFO autentica aceptada. Preparada web1.3.78: ventana8paquetes compatibleFW4.1 reduce consultasestado, progresoKB/porcentaje/velocidad/ETA y diagnosticochunk. Aun sin desplegar; prod1.3.77, serial0069 si verificada.

## Siguiente paso
Usuario debe detener OTA actual en navegador si sigue enviando, o esperar conclusion. Requiere autorizacion expresa despliegue1.3.78 segunAGENTS; no reiniciar con OTA activa. Despues probar avance real y medir velocidad/chunk; investigar transporte si sigue lento. No declarar OTA fisica verificada hasta jobverified. Imagen/credencial privada0069 enAppData, COM3cerrado; no se necesita serial para esta mejoraweb.

## Evidencia
Node4escenarios receptorcola8:16/180bytes,offsets/bytes exactos,69/9lecturas fixture8197bytes,cancelacionyrecuperacion sinregrabar. Backend14testsOTA correctos;Playwrightaislado progreso25%250/1000KB25KBsETA30s,cancelar restaura controles;desktop1366/mobile390 sin desborde. nodecheck/diffcheckcorrectos. ServerPCB66 FW4.1/MAC8C:8C:29:C3:D6:A6 jobprepared sourcepart65536 appa3b32eb... SinexitoOTA aun. CMcheckpoint/Git/memoria,ECCsecurity/verificacion.
