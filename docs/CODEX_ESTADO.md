# Estado de Codex: TQT-Web

Actualizado: 2026-10-16 19:45 UTC
Commit de referencia: `11cc0585dc43` (puede no incluir cambios pendientes)

## Avance reportado
Desplegada1.4.3 autorizada porusuario enOrangePi /home/orangepi/escanertqt commit11cc0585dc430208d1c1f2e83f3dd423e8badacf. Fastforward desde76d71a1 y recreate solo servicio tqt con servidor/compose.yml. Datos/volumenes/tunel conservados. Loginpublico confirma1.4.3 y apihealthOK.

## Siguiente paso
Revisar operacion de puente BLE Windows por usuario en produccion; pruebas fisicas previas locales14/14 no repetidas. UART28/99 lineas corruptas pendiente diagnostico. Previewlocal no reiniciado. Android/Skytec pendientes.

## Evidencia
Sin trabajos activos antes de despliegue; respaldo SQLite predeploy_1.4.3_20261016_134402.db en /backups servidor. ContenedorAPP_VERSION1.4.3 y arranqueOK; httpsinventariotqt.site/login muestra1.4.3, apihealthok. 502 transitorio durante arranque resuelto; recursosstatic protegidos requieren sesion. Pruebas previas24Python14JSUIpass.
