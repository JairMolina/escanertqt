# Estado de Codex: TQT-Web

Actualizado: 2026-10-16 00:30 UTC
Commit de referencia: `5a5e89b16bb3` (puede no incluir cambios pendientes)

## Avance reportado
Preparado encargo detallado para compañero en docs/ENCARGO_VALIDACION_SERIAL_OTA.md:13 requisitos Validacion, motor14etapas directo WebSerial/WebBluetooth, indicadores/sensores/historial/FW, identidad0042 a0044 con confirmacion y continuidad, dos etiquetas Aprobada+cable, estado comun R1/R3 y ajusteOTA por eventos. Skytec queda pendiente sin integrar. BaseGit actualizada ff-only a5a5e89b web1.3.92 preservando ultimos cambiosDYMO. Solo documentacion, no implementacion/despliegue/hardware.

## Siguiente paso
Compañero debe retomar ENCARGO_VALIDACION_SERIAL_OTA.md, inspeccionar contratos y portar motor sin perder evidencia. Mantener base4.0 fija, no eFuses. Limites explicitos: JLinkSWD no reemplazable porWebSerial, MAC no expuesta directamente porWebBluetooth, permisos nativos, DYMO directo requiere runtime fabricante. AppAndroid TQT conserva especificacion aparte APP_TQT_ANDROID.md. Autorizar banco y despliegue antes de ejecutar.

## Evidencia
Revision fuentes sec_validacion, contrato14etapas, engine/protocol/ble Python, APIvalidacion, transporteR2 y DYMOvigente1.3.92. ON/OFF BLE ya presentes en codigo: investigar visibilidad/habilitacion sin duplicar. ContratoONsensorcierre/OFFsensorapertura documentado. RequisitoOTA deriva confirmacion fisica usuario visible~2min vs pestañaoculta. Revision documental/diff; no pruebas runtime nuevas. Adjuntos pendientes0.
