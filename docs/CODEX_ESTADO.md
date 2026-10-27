# Estado de Codex: TQT-Web

Actualizado:2026-10-27. Código de referencia:a1ea3d57d6907ef668e0d0156567a14edfe26243.

## Avance reportado

Claude v1.4.58: alta automática de candados R1/R2 en Skytec al imprimir etiquetas (TQT_SKYTEC_* en .env); R2 habilita «Actualizar por Bluetooth» tras la base genérica. Pendiente: verificar el alta real en Skytec con credenciales en el servidor.
Claude v1.4.57: aviso en Pruebas TQT a cuentas con agente/puente viejo (agentes/desactualizados); Raspberry en agente 1.4.56.

Claude v1.4.56: agentes y puentes BLE de Pruebas TQT separados por cuenta (test_station.propia; cancelar solo dueño/admin); agente con keep-alive HTTPS (comandos BLE ya no vencen por handshakes lentos; send 20 s); sin confirm() en Pruebas automáticas. Pendiente: re-descargar el puente de cada laptop y actualizar el agente de la Raspberry.

Claude v1.4.55: /stations de Pruebas TQT omite puentes «solo BLE» (verificado en producción 1.4.54: la Raspberry ya no aparece). Agente de la Raspberry actualizado a 1.4.51-pruebas-auto.

Claude v1.4.54: Pruebas TQT ya no lista ni usa la Raspberry de Pruebas automáticas como puente Bluetooth ni como agente (test_station.RASPBERRY/no_raspberry; antes el escaneo/conexión BLE podía hacerse con el Bluetooth de la Raspberry). v1.4.53: scroll del esquema de Diagrama.

Claude v1.4.52: Pruebas automáticas con sesiones separadas (la Raspberry es de una cuenta a la vez; pantalla «Raspberry ocupada», 409 con quién la usa; cada cuenta ve solo sus campañas; admin «Detener y liberar») y rediseño de Diagrama (sec_diagrama.css/js, diagrama_svg.js; datos y lógica sin cambios).

Claude, v1.4.51 (1.4.50 sin usar; rama luna-pruebas-automaticas sobre 1.4.49; publicada antes como «v1.4.51» y desplegada en b7e9554): luna «Pruebas automáticas» en /inicio y submódulo /pruebas-automaticas: campañas de resistencia que repiten las 14 etapas de Pruebas TQT en UN banco, la Raspberry de la DYMO (tablas tqt_resistencia, tqt_resistencia_ciclos, tqt_resistencia_banco; services/pruebas_auto.py encadena en test_station.claim). Agente de pruebas para Linux: iniciar.sh, candado fcntl, puerto serie by-id recordado, subida de agent.log a petición. Logs .txt por ciclo, campaña y agente. No libera tarjetas ni cambia estados de fabricación.

Web1.4.49 publicada enmain ydesplegada conautorización expresa sobre1.4.48/2fa6fd2. Nueva secciónnativa Diagrama debajo deComandos,con armazón/temas actuales;HW20/HW30,6grupos,SVG/fichas/búsqueda,comparación,láminas/AK7V,revisionlocal/exportJSON. Siniframe ni shell duplicado;datos19/18 y6JPEG delHTML conservados conhash. Consultor puedeleer,sin privilegiosextra. Revisiones locales porHW no registranPruebasTQT. SourceoriginalSHA25671cf74e44789024439da9f2a21053dfd985794f5584221cafa15f417b93b1d73. Ver docs/DIAGRAMA_TQT.md. AjusteSTM32vigencia1.4.48 permanece;FW4.4 ya estabaaprobado,no se cambió.

## Siguiente paso

Pruebas automáticas: desplegar y vincular la Raspberry (paso 1 de /pruebas-automaticas), probar con hardware real (BLE a R2, desconexión USB a mitad de ciclo). Desplegar 1.4.51 (arreglo de reconexión USB del agente y huella ?v= en estáticos) y actualizar agent.py en la Raspberry.

RecargarCtrl+F5 yabrir /monitor#/diagrama,debajo deComandos. Las marcasderevisión duran en ese navegador y puedenexportarse;no certifican tarjetas. Proximastareas partir deorigin/main y comprobar servidor antes deactualizar. No repetir limpiezadeagentes,aprobarfirmware ni ejecutar banco por estecambio. Checkoutactivo work/tqt-fw-beta-20261026,rama codex/diagrama-tqt-20261027.

## Evidencia

Pruebas automáticas: 10 casos tests/test_pruebas_auto.py + regresión Pruebas TQT/módulos/versión (89 OK tras rebase sobre 1.4.49); capturas 1280/390 claro/oscuro con Raspberry simulada; ZIP del agente con iniciar.sh y serial_port verificado. Sin hardware real. station/test_station/tests: 1 falla preexistente (test_reporting CSV).

13gruposPlaywright+16Node+7PythonPASS;datos/imágenes conhash,fuentes/pinout conservados,permisoscatálogo/JPEG,teclado/foco,zoom,exportreal,consultor,recuperación/aborto,navegación.0JSerrors/HTTPinesperados/escriturasAPIproducción enQA. Capturas1440/1024/390,claro/oscuro revisadas,sindesborde. JSsyntax/diff/ComposeQAOK. Producciónrunninghealthy,quick_checkok,health interno/públicook:true,loginHTTP200/1.4.49,catálogoanónimo401,7archivosGit=servidor y6JPEGverificados. Backup predeploy_1.4.49_20261027_101445.db integrity_checkok,SHA256c1bf8508650af65b601314e31b14964afb7703a65fd51eb812a5eb94826ec335. Inventario idéntico/todosIDsprevios conservados;hubo1pruebaweb/5comandos nuevos concurrentes,pruebaterminada(noatribuida aDiagrama). ui-ux-pro-max/design-system parareutilización;ECCE2E/verificación yCMcheckpoint/memoria. Originales delusuario no respaldados enMiniPC/Gitpor estatarea.
