# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 21:21 UTC
Commit de referencia: `d8d149305ba8` (puede no incluir cambios pendientes)

## Avance reportado
Local1.3.86 corrige desconexion GATT al segundo paso de nombre exacto. R2 0067 ya tiene compatibilidad4.2 name_format2, verificada fisicamente por BLE: MAC8C:8C:29:C3:D7:EA, particion0x10000, app860e91765f971a975869262346ca8f87f0ce8689e2df7eaceef2fb3e92bdad84. Se reutiliza conexion validada y se reintentan servicios/caracteristicas/INFO antes de autorizar trabajo. No nueva grabacion serial ni eFuses.

## Siguiente paso
Usuario debe recargar local18082 conCtrlF5 y comprobar1.3.86, actualizar0067 a4.2 porBLE; solo falta paso final para nombre TQT-R2-V30-0067. Verificar lectura fisica final y cierreDB. Produccion sin cambios.

## Evidencia
12 escenarios transporte pasan, incluido GATTdisconnected durante descubrimiento del segundo paso y sin trabajos duplicados; nodecheck ydiffcheckOK. Playwright1.3.86/1386,botoBLEhabilitado,sinerroresJS. DB puente8ff1da75607b4d959b4dc454 verified; lecturaBLEindependiente boot_validtrue,name_format2. Suites previas18R2+40ESP32sin cambiosbackend en esta correccion.
