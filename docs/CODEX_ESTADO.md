# Estado de Codex: TQT-Web

Actualizado: 2026-10-16 19:07 UTC
Commit de referencia: `f689b7d8193e` (puede no incluir cambios pendientes)

## Avance reportado
Implementada local1.4.1 sobre produccion1.4.0/f689b7d en codex/ajustes-web-20261016: Validacion encabezado3paneles con manuales, selectorizquierdo estiloProgramacion, Enterexacto, historialantesR1R2. WebBLE admite alias mismosrol/HW/numero y preconexionR1R2. Recuperado modo WindowsporMAC solo enValidacion usando motoranterior pyserial/Bleak completo; necesitaagente y su serial. GuardiaON/OFFserial con S29fresco/ambasMAC/motorreposo. Sin despliegue ni grabacion/movimientos. Docs VALIDACION_141.md y CHANGELOG.

## Siguiente paso
Validar fisicamente nombres antiguos R1/R2 y automatico porMAC con agenteWindows instalado, antes de desplegar1.4.1 con autorizacion. Local http://127.0.0.1:18084/monitor#/validacion usa volumen nuevo tarjetas sinteticas. WebBluetooth sigue necesitando permiso nativo inicial y no exponeMAC; WindowsporMAC recupera serial+BLE del agente entero, no puentehibrido. No modificados firmware ni programacionR1R3. AppAndroid TQT y Skytec siguen pendientes segun docs.

## Evidencia
13 pruebasJS motor incl nuevas identidadalias/ambiguedad/numeroincorrecto/guardiamanual PASS; sec_validacion_ui PASS;16backend test_test_station_web PASS. Playwright1440/390 sinoverflow ni pageerrors, seleccion42Enter y3paneles/14filas/ordenhistorial. AlternanciaWindows/navegador con estacionesmock PASS. Docker tqt-validacion141-web-1/baseaislada. CapturasQA outputs/validacion_141. 5originales aportados respaldados/verificadosMiniPC connotasCM. Skillui-ux-pro-max usada distribucion/estadosresponsive; ECCverificacion no disponible, verificacion nativa realizada. Produccionno tocada.
