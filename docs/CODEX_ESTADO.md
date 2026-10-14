# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 20:12 UTC
Commit de referencia: `0e8bedcf1157` (puede no incluir cambios pendientes)

## Avance reportado
Web1.3.76 desplegada en Orange Pi desde GitHub codex/esp32-r2-v4, commit aplicacion 0e8bedc. Integra R2 V4.0 con catalogo BIN/HEX/nombre de inventario y conserva cambios de produccion1.3.73-1.3.75 de semaforo, Pruebas y estacion J-Link local. Montaje R2 readonly; solo servicio tqt recreado. Catalogo real R2 FW4.0/HW3.0.

## Siguiente paso
Validar R2 V4.0 en hardware cuando el usuario indique tarjeta y autorice prueba. No se programo ninguna placa durante despliegue. GitHub/prod usan rama codex/esp32-r2-v4; main GitHub sigue separado. Instancia LAN recuperacion y originales intactos; vista previa aislada se detiene al cerrar.

## Evidencia
API local/publica HTTPS200 version1.3.76; imagen R2 0013 preparada/validada sin grabar, perfil4.0/3.0/nombre correcto; HTML/JS cache1376. Contenedor healthy, cloudflared sin reinicio. SQLite integrity ok y hashes identicos de100 tarjetas/300PCB/7usuarios. Respaldo pre-r2-v4-1376-20261014T200710Z.db SHA d665ad29f0d8064d45c7164f46bc2f895b0fc50909cf23f241c0c1fa31e9d424; compose previo20261014T200829Z. Integracion51 tests correctos (37STM32+14ESP32), node --check y Playwright preservan orden R2/R1/R3 y selector. Original R2 respaldado en MiniPC, 0 adjuntos pendientes. CM memoria/checkpoint; ECC verificacion.
