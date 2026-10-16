# Estado de Codex: TQT-Web

Actualizado: 2026-10-16 19:36 UTC
Commit de referencia: `01c769968089` (puede no incluir cambios pendientes)

## Avance reportado
Validacion local 1.4.2 conserva Web Serial y recupera exclusivamente BLE Windows/Bleak por MAC con puente ble_only. Conexion automatica R1/R2 con nombres antiguos; autorizacion por operador y comandos de un solo uso. Sustituye modo Windows completo 1.4.1. Ver docs/VALIDACION_142.md.

## Siguiente paso
Produccion sigue 1.4.0 sin desplegar. Revisar calidad UART: 28 de 99 lineas ilegibles excluidas; causa fisica no demostrada. No repetir movimientos sin nueva autorizacion. Puente privado BLE-Preview142 listo; Android y Skytec pendientes.

## Evidencia
Prueba fisica autorizada 0039 COM7 run44d7b1fc0e23708d0817f0bf09613c8c:14/14,108.2s,final abierto,aprobado_con_advertencias,43 S29 y ambas MAC Windows coincidentes.23 Python+14 JS+UI PASS.Playwright BLE real R1/R2 sin COM. ECC backend/seguridad aplicados.No firmware/eFuses ni produccion modificados.
