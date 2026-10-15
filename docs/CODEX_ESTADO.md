# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 17:23 UTC
Commit de referencia: `4cd65a0e92e6` (puede no incluir cambios pendientes)

## Avance reportado
Correccion local1.3.82: R2 con FW/MAC borrados en inventario puede intentar OTA si conserva credencial. El dispositivo autentica FW4.0+, identidad, protocolo y arranque antes de transmitir. FW registrado <4.0 bloquea el intento. MAC ausente solo se guarda tras nuevo arranque; rechazo MAC duplicada/cambio identidad. Playwright comprobo0069 Sin programar con boton BLE habilitado, sin grabar ni restaurar los datos borrados por usuario.17 pruebas OTA y13 R2/agente OK.

## Siguiente paso
Produccion sigue1.3.80; pendiente despliegue1.3.82 y actualizacion agentes. Usuario puede probar OTA desde web local18082. No se ejecuto nueva grabacion fisica en esta correccion.

## Evidencia
tests/test_esp32_ota.py; docs/R2_FLUJO_AUTOMATICO.md; Playwright capability eligible=true/current_fw vacio y boton habilitado
