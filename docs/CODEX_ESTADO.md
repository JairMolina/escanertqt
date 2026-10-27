# Estado de Codex: TQT-Web

Actualizado:2026-10-27. Código de referencia:f608baf857dd0e023e6063d55110bdeb505a5ffc.

## Avance reportado

Web1.4.48 publicada enmain y desplegada con autorización del usuario sobre1.4.47/454add0. En programaciónR1/R3, lista y panel comparan FW registrado con el último aprobado del mismoHW;naranja/Desactualizada si anterior,verde si verificada/vigente. Selector no modifica historial;beta/otroHW no cuentan;sin catálogo no se da falsoverde. Producción confirma0054verificada4.4/vigente4.4 y0055verificada4.3/vigente4.4. El catálogo ya marca4.4 aprobado;no se cambió su aprobación ni se programó hardware. Ver docs/STM32_INDICADOR_VIGENCIA.md.

## Siguiente paso

RecargarCtrl+F5 en web1.4.48 y comprobar los colores. Para cambios futuros partir deorigin/main y consultar servidor real. La limpieza anterior de agentes está completa;no repetirla. Instalar un agente nuevo cuando se requiera programar. Esta tarea no hace nuevas pruebas físicas. Checkout activo work/tqt-fw-beta-20261026,rama codex/stm32-fw-indicador-20261027.

## Evidencia

19gruposPlaywrightPASS(8vigencia+5historial+6agentefijo),CSSnaranja/verde renderizado,0JSerrors,móvil390;11Pythonversion/estadoPASS;JSsyntax/diff/ComposeQAOK. Produccióntqt runninghealthy,quick_checkok,health interno/públicook:true,loginHTTP200/1.4.48,JS/CSSGitcoinciden. Backup /backups/predeploy_1.4.48_20261027_093845.db integrity_checkok SHA256dcecdd6731321644cf646e2358f339d35b0c2658b300fd73e3a57baae6cc5845.0trabajos activos;inventario/historial sin cambios. ui-ux-pro-max(color acompañado de texto),ECCverificación yCMcheckpoint/memoria utilizados. Originales de capturas no copiados aGit/MiniPC por esta corrección.

## Preparada1.4.49 — Diagrama,2026-10-27

Nueva sección nativa debajo de Comandos,HW20/HW30,grupos/SVG/fichas,búsqueda,comparación,láminasAK7V,revisiónlocal/exportJSON. Datos e imágenes del HTML conservados conhash.13gruposUI+16Node+7PythonPASS;temas1440/1024/390,sin escriturasAPIproducción. Producción sigue1.4.48/2fa6fd2;pendiente autorización expresa de despliegue. Ver docs/DIAGRAMA_TQT.md.
