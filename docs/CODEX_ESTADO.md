# Estado de Codex: TQT-Web

Actualizado: 2026-10-16 19:42 UTC
Commit de referencia: `8983d9972364` (puede no incluir cambios pendientes)

## Avance reportado
Integracion 1.4.3 sobre version REAL de produccion1.4.1 commit76d71a128a44778686027164181a468ff805e7f4; ese commit no estaba en GitHub y se recupero solo codigo por bundle. Conservadas liberacion COM al salir y recuperacion tarjeta bloqueada por pestaña abandonada de otro operador, junto con cambios141/142: distribucion, WebSerial y BLE Windows por MAC.

## Siguiente paso
Produccion comprobada sana en1.4.1; no desplegada1.4.3 ni reiniciada OrangePi. Preview backend aun requiere recarga/reinicio para version143. UART28/99 lineas corruptas pendiente diagnostico. Sin repetir prueba fisica; Android/Skytec pendientes.

## Evidencia
Origen76d71a1 contenedorOrangePi APP_VERSION1.4.1 y healthOK. Integracion24Python+14JS+UI PASS y diffsinmarcadores. Prueba fisica previa142 run44d7b1fc0e23708d0817f0bf09613c8c 14/14aprobada conadvertencias; no repetida. ECCverification aplicada pruebas/regresion y revisiondiff. Sin datos/credenciales publicados.
