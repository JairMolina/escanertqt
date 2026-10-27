# Diagrama TQT — sección nativa, 1.4.49

El usuario aportó `Diagrama_TQT.html` y pidió añadir «Diagrama» debajo de Comandos adaptado a la consola actual. No se incrusta el HTML completo ni se ejecuta su aplicación independiente: se conservan sus datos y láminas, y se integra una sección registrada en el armazón existente.

## Navegación y funcionamiento

- Ruta `#/diagrama`, Gestión, orden120 después de Comandos110; cabecera, menú lateral, lote y tema de la consola. Acceso de lectura también para consultor, sin ampliar permisos administrativos.
- HW20/HW30, seis grupos: alimentación R1/R2, GPS/RS485, R3/TIMER, motor, sensorM1 y sensorM2. Búsqueda por color, grupo, señal o destino; selección por lista o SVG con ratón/teclado; ficha de conexión, copia y rótulos.
- Vista general, láminas completas ampliables y tabla AK7V de12pines/colores. Comparación de hardware con filtro de diferencias. Se preservan las ambigüedades documentadas de color/rótulo; no se inventan funciones de pines ni compatibilidad porFW.
- Revisión local porHW en `tqt.diagrama.review.v1`, exportación JSON, filtro de pendientes/revisadas y reinicio limitado al HW elegido con confirmación. No registra pruebas, aprueba tarjetas ni modifica inventario. Sin almacenamiento disponible avisa que las marcas duran solo la sesión.
- Parámetros compartibles `hw`, `vista`, `grupo`, `cable`, `q`; independiente del lote. Láminas y catálogo requieren sesión y permiso EscánerTQT. No utiliza Serial/Bluetooth/agentes ni servicios externos.

## Archivos y trazabilidad

`sec_diagrama.js/css` usa los tokens/fuentes locales de la consola para sus dos temas. `diagrama_core.js` contiene búsqueda, comparación y revisión; `diagrama_svg.js` adapta únicamente el renderizador SVG puro del archivo aportado, con escape de textos y fuente local. No se copia la barra lateral ni la cabecera de ese archivo.

`app/static/catalogos/diagrama_tqt.json` conserva los19puntos de referencia HW20 y18HW30 (no cuentan cables físicos únicos), grupos, AK7V y límites del documento. Las6imágenes JPEG se extraen sin edición a `app/static/img/diagrama_tqt/` y se cargan cuando corresponde; se evita cargar el HTML original de1,7MB con todas las imágenes base64 incrustadas.

Utilidad reproducible: `python tools/extract_diagrama_reference.py RUTA_AL_HTML`. SHA256 del original `71cf74e44789024439da9f2a21053dfd985794f5584221cafa15f417b93b1d73`. El catálogo incluye huella del contenido canónico y de cada imagen; las pruebas las contrastan. El HTML original y la captura del usuario no se incluyen en Git ni se copian a memoria central en esta tarea.

## Verificación aislada

- 7pruebas Node nuevas: integridad de datos/imágenes, grupos/páginas/AK7V, búsqueda, diferencias, limpieza de marcas, exportación y escapeSVG. Más9regresiones de Comandos:16NodePASS.
- 7PythonPASS: versión visible y acceso autenticado al catálogo y6JPEG, consultor autorizado, anónimo/otro módulo bloqueados y administración conservada.
- 13gruposPlaywrightPASS: orden/navegación nativa; HW/SVGteclado; copiar conexión; búsqueda/vacío; comparación; originales/zoom/Escape/foco/AK7V; revisión persistente/exportación real; reinicio porHW; temas y1440/1024/390; enlaces y guía; consultor; error/recuperación; aborto y desmontaje. Sin erroresJS/HTTP inesperados ni escrituras de API de producción.
- Capturas sintéticas locales revisadas en claro/oscuro y móvil; sin desborde de página. El esquema/tabla pueden desplazarse dentro de su panel en móvil. SintaxisJS, diff y ComposeQA correctos.

ui-ux-pro-max y design-system para navegación, tokens, foco/teclado y reutilización del armazón; ECC E2E/verificación para interacciones, accesos y evidencia. No se añaden librerías, CDN ni herramientas autónomas.

## Estado

Base main/producción2fa6fd2, web1.4.48, comprobadas limpias al comenzar. Preparada1.4.49 en rama `codex/diagrama-tqt-20261027`, QAaislada `http://127.0.0.1:18089/monitor#/diagrama`. La autorización expresa fue recibida y se desplegó1.4.49;resultado debajo. No se programó hardware ni se cambiaron servicios compartidos.

## Despliegue verificado — 2026-10-27

El usuario autorizó expresamente desplegar Diagrama. Publicado código a1ea3d57d6907ef668e0d0156567a14edfe26243 en main sobre2fa6fd2;fast-forward de OrangePi y recreación exclusiva de tqt. Imagen vigente reutilizada(sin cambios de dependencias;app montada en lectura). Cloudflared continuó activo.

Respaldo previo /backups/predeploy_1.4.49_20261027_101445.db,integrity_checkok,SHA256c1bf8508650af65b601314e31b14964afb7703a65fd51eb812a5eb94826ec335. Se comprobó0trabajos activos al respaldar. Después apareció actividad concurrente legítima:ejecución web303f0a06 creada16:14:56UTC,terminada16:16:29UTC,con5comandos nuevos respecto al respaldo. La comparación por conteos estrictos se amplió para comprobar conservación de todas las claves previas,permitiendo esos nuevos registros;no se intervino ni se volvió a ejecutar esa prueba.

Comprobado:1.4.49,tqt runninghealthy,SQLite quick_checkok,health interno/públicook:true,loginHTTP200/version1.4.49,catálogo anónimoHTTP401. InventarioPCB ytarjetas idénticos al respaldo,todos losIDs históricos previos conservados. Conteos observados finales94trabajosSTM32,51pruebas,244comandos,446PCB,100tarjetas,1886escaneos,22registros deestaciones(incluidos lógicos).

Los7archivos de la función enGit(HTML,armazón,core,SVG,sección,CSS,catálogo) coinciden porSHA256 con los usados enproducción. Las6imágenes originales coinciden con el manifiesto. No se cambiaron aprobacionesFW,puertos,credenciales ni configuraciónCloudflare. Las pruebas físicas concurrentes pertenecen al flujo existente;Diagrama no envía comandos ni escribe resultados.

Abrir https://inventariotqt.site/monitor#/diagrama yrecargarCtrl+F5. Gestión muestraDiagrama debajo deComandos. Revisión local guarda solo en ese navegador;JSONexportadonoesunresultado dePruebasTQT. Se guardóGit/memoria;fuenteHTMLy capturaoriginalno se transmitieron aMiniPCni se añadieron aGit(únicamente los datos y láminas necesarios para la integración solicitada).
