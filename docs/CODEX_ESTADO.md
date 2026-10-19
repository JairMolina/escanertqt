# Estado de Codex: TQT-Web

Actualizado: 2026-10-19 (Claude Code)
Commit de referencia: `dcd0ae8` (v1.4.8; producción en 1.4.6 hasta que se despliegue)

## v1.4.7–v1.4.8 (2026-10-19, Claude Code)
- v1.4.7: consumo de materiales por evento (R1/R2 programadas, R3 asignada, gabinete colocado); migración `migr_consumo_146` + tabla `inv_tqtr_consumo_base` (solo desde hoy); `consumir_por_evento` serializado.
- v1.4.8: criterio único de «programada» (`db._R1R2_PROGRAMADAS`, `T.programada`/`T.conFw`); reporte por fecha corregido; STM32 y programación por lote notifican la tarjeta.
- Evidencia: suites de inventario, programación, emparejado, DYMO, admin y API OK (test_correo_excel solo falla en conjunto, preexistente; pasa aislado). Docker local 1.4.8 healthy con la BD de producción 1.4.6 del 2026-10-19 (migración: base placas 34, r3 26, gabinete 19). Sin prueba física.
- Pendiente de decisión: «Pendientes» de MAC y firmware solo miran MAC; OTA migration_required queda verified sin guardar firmware; vista de estado R2 por versión.

## v1.4.5–v1.4.6 (2026-10-19, Claude Code)
- v1.4.5: zona «Cable R3» en Etiquetas DYMO (TQT: 0000 / R3: 0000), parámetro `r3` en `/api/dymo/cable/*` y DYMO compartida.
- v1.4.6: impresión automática del cable R3 en la DYMO compartida al asignar una R3 (`app/services/cable_r3_auto.py`, gancho en `_notificar_tarjeta`), interruptor en Administración › Resumen (apagado por defecto). Crea la tabla `dymo_cable_r3_hechas` sola.
- Evidencia: 89 pruebas Python OK (test_cable_r3_auto, test_dymo_cable, test_dymo_remoto, test_dymo, test_admin, test_api, test_qa_version_hoy); Docker local 1.4.6 healthy. Sin prueba física con la Raspberry ni revisión visual en navegador.
- Pendiente: desplegar 1.4.4→1.4.6 en producción, activar el interruptor y probar una asignación real de R3.

## Avance reportado
Desplegada1.4.3 autorizada porusuario enOrangePi /home/orangepi/escanertqt commit11cc0585dc430208d1c1f2e83f3dd423e8badacf. Fastforward desde76d71a1 y recreate solo servicio tqt con servidor/compose.yml. Datos/volumenes/tunel conservados. Loginpublico confirma1.4.3 y apihealthOK.

## Siguiente paso
Revisar operacion de puente BLE Windows por usuario en produccion; pruebas fisicas previas locales14/14 no repetidas. UART28/99 lineas corruptas pendiente diagnostico. Previewlocal no reiniciado. Android/Skytec pendientes.

## Evidencia
Sin trabajos activos antes de despliegue; respaldo SQLite predeploy_1.4.3_20261016_134402.db en /backups servidor. ContenedorAPP_VERSION1.4.3 y arranqueOK; httpsinventariotqt.site/login muestra1.4.3, apihealthok. 502 transitorio durante arranque resuelto; recursosstatic protegidos requieren sesion. Pruebas previas24Python14JSUIpass.

## Nota operativa R2 (2026-10-16)

Documentado en R2_ALTA_GENERICA_42.md el inicio de programar_base.ps1 con ExecutionPolicy Bypass limitado al proceso. El usuario reporto bloqueo de PowerShell; no confirmo nueva grabacion. Se mantiene BIN generico4.0 fijo seguido de alta y OTA web con datos/credencial por unidad; evidencia previa0067 FW4.2. Sin cambios de codigo ni nueva prueba fisica.
