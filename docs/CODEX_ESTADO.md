# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 17:03 UTC
Commit de referencia: `c0912136159a` (puede no incluir cambios pendientes)

## Avance reportado
Implementada web1.3.81 local en codex/r2-flujo-automatico: R2 por defecto, etapas R2-R1-R3, BLE preferido, USB/velocidad en mantenimiento, semaforos ligados a evidencia MAC/HW/FW/hash; agente verifica automaticamente sin selector y guarda metodo/fechas/intentos/errores. Base4.0 OTA rapida compilada sin reemplazar4.0original;4.1eslenta,4.1.1rapida compatible. Pruebas fisicas0069: COM4 CH340460800, base4.0 escrita17.2s hashOK; BLE automatico2.85s; OTA4.0a4.1.1 APIlocal71.698s,15.47KiB/s,hash/nonce/particion/arranqueOK; web local real verifica viaagente sin selector. 97 casos Python (ESP3236,STM3237,TestStation11,R2/agente13) y JS7; Playwright serial simulado fallback460800a115200 y estados/mobile. SQLite aislado integro y persistente. Originales3 respaldados. CM, ECC HWFW/C++/seguridad/verificacion y ui-ux-pro-max aplicados.

## Siguiente paso
Pendiente despliegue1.3.81 y actualizar agente Windows en estaciones; produccion sigue1.3.80 sin tocar datos. R20069 fisica finalmente4.1.1 desconectada BLE. Pendientes fisicos: transferencia OTA por WebBluetooth, grabacion WebSerial completa, fallback115200 real y cortes/rollback. No usar bases/credenciales del entorno aislado como produccion.

## Evidencia
docs/R2_FLUJO_AUTOMATICO.md; tests/test_r2_programming.py; tests/test_r2_agent.py; tests/r2_auto_ui.playwright.js; outputs/r2_ble_probe/ota_base40_to_latest_api_result.json
