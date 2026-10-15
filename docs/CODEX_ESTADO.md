# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 15:53 UTC
Commit de referencia: `e718d327f6c8` (puede no incluir cambios pendientes)

## Avance reportado
Integrada base Orange Pi e718d32 (1.3.79) en rama codex/r2-ota-rapida. Web 1.3.80 agrega transporte R2 OTA 500 bytes NR+notificaciones, compatibilidad 4.1, plantilla 4.1.1 sin clave. Preservados monitor serial, R1 y reportes. ECC verificacion aplicada. 35 pruebas ESP32 previas y 15 OTA finales OK; 7 escenarios JS OK; Playwright selecciona 4.1.1 y conserva UI R2. Respaldo productivo consistente pre-r2-ota-1380-20261015T155249Z.db.

## Siguiente paso
Desplegar commit revisado y verificar API publica, catalogo y datos. Medir OTA real de Chrome posteriormente; no se afirma tiempo fisico del navegador.

## Evidencia
docs/ESP32_R2_OTA_PRUEBA_AISLADA.md; tests/esp32_ota_transport.cjs; tests/test_esp32_ota.py
