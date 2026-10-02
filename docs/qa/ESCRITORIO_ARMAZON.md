# Consola de escritorio: armazón y secciones (etapas 2 y 3)

## Qué se hizo, por archivo
| Archivo | Cambio |
|---|---|
| `app/static/monitor.html` | Ahora es la consola ("Consola · Escáner TQT"). Sin cámara. `<!-- SECCIONES -->` con los `sec_*.js`; el agente de MAC ya añadió su script bajo `<!-- sec_macs -->`. Mantiene sesión por cookie y `?lote=`. |
| `app/static/js/escritorio.js` (nuevo) | Armazón: `TQTEscritorio.registrar`, router por hash (`#/id?param`), barra lateral colapsable (`[`), cabecera (título, selector de lote con menú y "Usar o crear lote…" que reutiliza la hoja de `common.js` con su flujo 401, actualizar, punto WS, tema, atajos, Versión móvil, Cerrar sesión), atajos (`/`, `g`+letra, `[`, `?`), foco, datos compartidos con caché invalidada por WS, actividad en vivo global y utilidades (`util.tabla` con orden, selección y teclado; fichas de placa). |
| `app/static/css/escritorio.css` (nuevo) | Estilos densos sobre los tokens de `app.css` (oscuro/claro). |
| `sec_resumen.js`, `sec_inventario.js`, `sec_tarjetas.js`, `sec_consultar.js`, `sec_lotes.js`, `sec_excel.js`, `sec_enlaces.js` (nuevos) | Secciones del contrato. Movimientos, Etiquetas y Administración son enlaces a `/admin#movimientos`, `/dymo` y `/admin`. |
| `app/static/js/monitor.js` | Borrado (nada lo referencia). |
| `app/static/js/common.js` | Edit mínimo: exporta `openLotes` y añade 9 iconos (dash, card, shield, logout, phone, sidebar, external, help, sort). |
| Tests adaptados | `tests/test_qa_consulta.py` (logo va a `#/resumen`, la consola no carga jsQR/scanner/visor; `?lote=`), `tests/e2e/{ficha_consultar,diseno_consultar,axe_estados,flujo2,volumen}.py` a los nuevos selectores. |
| `tests/e2e/escritorio_armazon.py` (nuevo) | Servidor aislado en 8464, siembra 97 PCB (R1/R2/R3, versiones V30/V31, tarjetas impares, 20 con MAC+firmware, 2 sin confirmar), recorre las 7 secciones a 1440x900, 1280x800 y 1024x768 en oscuro y claro, más teclado, flujos y una pasada sin contraseña (`--sin-clave`). |

Caché `?v=20260924esc3`.

## Resultado
- `escritorio_armazon.py` completo: **159/159** (con `--sin-clave`: 163/163 en la corrida anterior a los últimos retoques de CSS): 0 errores de consola, 0 respuestas 4xx/5xx inesperadas (el 404 de "código inexistente" se descuenta a propósito), 0 peticiones a cámara/jsQR y `getUserMedia` nunca llamado, sin scroll horizontal, axe-core sin violaciones (7 secciones x 6 combinaciones, con panel abierto), atajos, foco, flechas/Espacio/Enter en tablas, panel con Esc, consulta con texto de 4 líneas/MAC, menú de lote, hoja de lotes, sincronizar Excel, descarga `.xlsx` por fetch+blob, evento WS que actualiza Resumen, Versión móvil (`tqt.vista=movil` y `/`), cerrar sesión.
- Suite completa: `Ran 413 tests ... OK`.
- Capturas: `docs/qa/escritorio/` (`<seccion>_<ancho>_<tema>.png`, 44 archivos).

## Autocrítica de diseño (aplicada)
- El panel de detalle de Tarjetas a 1024 recortaba "Estado": ahora en contenedor angosto se oculta el firmware de la fila y se reducen paddings.
- MAC desbordaba la tarjeta de placa a 1440: tamaño por container query.
- Aparecía el recuadro de foco en el título tras navegar: se quitó (el foco sigue ahí para lectores de pantalla).
- KPIs de PCB quedaban 5+1 a 1024: rejilla de 6/3/2 columnas por container query.
- Encabezados h3 saltaban de nivel y el panel era un `aside` anidado (axe): corregido.
- Gráficas según `dataviz`: barras de 10 px con extremo redondeado, escalonado de un solo tono por tipo (con forma R1 cuadrado/R2 círculo/R3 rombo), partes de un todo con separación de 2 px y leyenda con cifras, vista como tabla en `<details>`.

## No verificado / riesgos
- Solo Chrome (Playwright); no Safari/Firefox ni pantallas táctiles reales.
- Tooltips de barras solo por `title`/`aria-label` (sin hover propio).
- Cambiar de lote "activo" con contraseña caducada depende del redirect a `/admin?next=/monitor` de `common.js`; probado el menú y la hoja, no la caducidad real.
- El toast verde de `common.js` tiene contraste bajo en oscuro (código ajeno, sin tocar).
- Movimientos/Etiquetas/Administración siguen siendo páginas aparte (etapa 4).
- La sección MAC la aporta el otro agente; aquí solo se comprobó que se monta y no rompe axe.
