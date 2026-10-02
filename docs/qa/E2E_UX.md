# QA E2E / UX del frontend (agente QA-E2E-UX, puerto 8457)

Entorno: Chrome 153 (Playwright 1.63) contra un servidor aislado (BD/Excel/exports/respaldos en carpetas temporales). Cámara falsa de Chrome con la foto real
`tests/fixtures/qr_R3_V30_0084_invertido.jpg` y, para el resto, una cámara de `canvas` con QR invertidos generados en pantalla. Scripts en `tests/e2e/` (ver su README);
pruebas sin navegador en `tests/test_qa_e2e.py` (15 tests). Resultado de la suite completa al terminar: **Ran 350 tests, OK**.

## Bugs encontrados y arreglados

| # | Bug | Sev. | Causa | Arreglo (archivo) | Regresión |
|---|---|---|---|---|---|
| 1 | Inventario vacío en Monitor, lista de PCB de /admin vacía y sin detección instantánea de repetidas en Recibir | **Alta** | `GET /api/pcb?limit=5000` respondía **422** (la API topaba en 1000) y el frontend lo pide en monitor.js, admin.js y recibir.js | `app/routers/inventario.py` (`le=5000`) | `test_qa_e2e.TestPaginasServidas.test_frontend_pide_limites_que_la_api_acepta` |
| 2 | 404 en cada carga de cada página (sin favicon, sin manifest) | Media | No existían `/favicon.ico` ni iconos | `app/static/icons/*` (svg, png 180/192/512, maskable, `manifest.webmanifest`), `<link>` en las 7 páginas, ruta `/favicon.ico` en `app/main.py` | `test_metadatos_por_pagina`, `test_manifest_y_iconos`, `test_paginas_y_favicon_200` |
| 3 | Contraste insuficiente (WCAG AA) en tema claro y oscuro: `--faint` 3.1:1 (hora del feed, ranuras vacías), `--ok`, `--warn`, `--r1/r2/r3` (chips), `--line-2` (bordes de controles 1.9:1), texto blanco sobre `--bad` claro (2.8:1 en oscuro, botón "Borrar todo" y "Falla" pulsado), estado "Pendiente" pulsado, foco dorado 2.5:1 sobre fondo claro | Media | Tokens y colores de texto fijos | `app/static/css/app.css` (tokens en los 3 bloques, texto `var(--bg)` sobre rellenos semánticos, foco con `--accent-text`), `admin.html` | `test_tokens_cumplen_aa_en_ambos_temas`, `test_texto_atenuado_legible` |
| 4 | Objetivos táctiles < 44 px: `btn-sm` 40, enlace de marca 34, estado de la cámara 40, pestañas y selects del monitor 40, `iconbtn` 43 | Media | CSS | `app.css`, `monitor.html` | `test_objetivos_tactiles_minimos` + `auditoria.py` (0 en 70 combinaciones) |
| 5 | axe **crítico**: `role="list"` vacío sin hijos (Emparejar, Programar); `role="listitem"` sobre `<button>` anulaba la semántica de botón; sin `<h1>` en 6 páginas; `/admin` sin `<main>` en el login; `.stage-preview` con scroll no enfocable; cabeceras `<th>` vacías; leyenda roja de DYMO 3.2:1 | Media/alta | Marcado | `emparejar.js`, `programar.js`, `recibir.js`, `pruebas.js`, `*.html` | `test_botones_sin_rol_listitem`, `test_metadatos_por_pagina` (h1) + axe |
| 6 | `confirm()` nativo al eliminar PCB en el monitor (criterio de diseño: sin diálogos nativos) | Media | Añadido por otro agente | `monitor.js`: doble toque en la propia hoja ("Confirmar eliminar", 5 s) | `test_sin_dialogos_nativos` |
| 7 | Un 500 del servidor al escanear se mostraba como "Sin conexión" | Baja | Mismo mensaje para red caída y 5xx | `recibir.js` ("El servidor falló: se reintentará solo") | (navegador: `robustez.py http500`) |
| 8 | Con la red caída el indicador en móvil era solo un punto rojo (etiqueta oculta a <=420 px) | Baja | `@media` ocultaba también "Sin red" | `app.css` (oculta la etiqueta solo si está "En línea") | `robustez.py caida` |
| 9 | Etiquetas de contadores cortadas a 320 px ("COMPLE…"); visor ocupaba 56 % de la pantalla en móvil horizontal; marca del monitor cortada 7 px | Baja | CSS | `app.css` | `auditoria.py` (clipped=0) |
| 10 | Textos: aviso DYMO "Todavía R1 aún no es FUNCIONAL" y banner de Excel con "Excel sincronizado" repetido | Baja | Copy | `dymo.js`, `monitor.js` | — |
| 11 | Carga 490 KB por página (jsQR 251 KB sin comprimir) | Baja | Sin compresión | `GZipMiddleware` en `app/main.py` (jsQR 251 -> 55 KB) | `test_gzip_en_estaticos_grandes` |
| 12 | `pruebas.js`: búsqueda de 400 caracteres generaba 422 en consola | Baja | Sin `maxlength` | `pruebas.js` (`maxlength=40`) | — |

Cambios de backend (Edit mínimo): `app/routers/inventario.py` (límite 5000) y `app/main.py` (ruta `/favicon.ico` + GZip). No cambian contrato salvo `limit` máx. 1000 -> 5000 en `GET /api/pcb`.

## 1) Recorrido de punta a punta (Chrome, servidor nuevo) — PASA
- **Recibir**: foto real invertida leída por cámara falsa de Chrome (`TQT-R3-V30-0084`, ~600-1100 ms desde cargar la página, 6/6 veces); 3 QR invertidos más generados en pantalla; 4 R1 y 4 R2 con "Agregar sin QR" (cantidad 4). Contadores 4/4/4, total 12, aviso de huecos/desbalance, hoja "Confirmar 12 placas". Tras confirmar: lista vacía, inventario R1/R2/R3 = 4/4/4.
- **Emparejar**: 4 series con R1+R2 (0001-0004; la 0004 sin R3 se une igual, marcada "Incompleta"), R3 0084 queda suelta. `Emparejar todas` crea 4 tarjetas.
- **Programar**: 8 MAC tecleadas (R1 y R2 de cada tarjeta) con validación en vivo; la lista pasa a "Todo tiene MAC".
- **Pruebas**: 0001 con 5 etapas OK -> LIBERADO; 0002 con Prueba PCB FALLA -> DETENIDO; 0003 -> EN PROCESO. Reemplazo: en Emparejar la R3 de 0002 se marca falla y se sustituye por la suelta 0084 -> tarjeta **IMPAR** (0002 con R3 0084), pruebas de la 0002 vuelven a PENDIENTE (regla documentada en SPEC 7.4).
- **Monitor**: KPI tarjetas 4 / liberadas 1 / en proceso 2 / pendientes 1 y KPI PCB 12 / asignadas 11 / falla 1 coinciden con `/api/stats`, inventario y tarjetas.
- **DYMO**: etiqueta 0001 = `TQT-R1-V30-0001 / 70:4b:ca:5b:9f:01 / TQT-R2-V30-0001 / 70:4b:ca:5b:9f:02` (4 líneas, MAC en minúsculas), estado FINAL para 0001 e IDENTIFICACION para el resto; coincide con `trama_lineas` de la API.
- **Excel**: sincroniza 4 tarjetas; el libro contiene MAC, estados y pruebas (revisado con openpyxl).
- **/admin**: login, resumen (4 tarjetas, 12 PCB, bitácora).
- Consola limpia, cero 4xx/5xx y cero hosts externos en Recibir/Emparejar/Programar/Pruebas/Monitor/Admin.

## 2) Calidad transversal (7 páginas x 5 tamaños x 2 temas = 70 combinaciones, `auditoria.json`)
Resultado final: **0** errores/warnings de consola, **0** peticiones 4xx/5xx o fallidas, **0** hosts externos, **0** scroll horizontal, **0** desbordes fuera de pantalla, **0** textos cortados, **0** objetivos < 44 px, **0** campos sin etiqueta, pestaña inferior activa correcta en las 4 pantallas móviles, `lang="es"`, viewport, `<title>` único, favicon y manifest en todas, foco visible en todos los elementos tabulados (y orden lógico; el "salto arriba" que se ve al final es la vuelta del ciclo de Tab), `aria-live` en la lectura de Recibir (`#readout`), Programar (`#activo`, `#macHint`), Pruebas (detalle e historial), toasts y avisos. `prefers-reduced-motion`: con la preferencia activa y un escaneo hecho no queda ninguna animación corriendo (`document.getAnimations()` = 0).
axe-core 4.10.2 (inyectado desde carpeta temporal, no está en `app/static`): 0 violaciones en las 70 combinaciones (320/390/1280) y en estados interactivos (todas las hojas, tarjeta abierta, teclado MAC, monitor inventario/tarjetas, cada pestaña de admin, ambos temas): `axe_estados.py`. Antes de los arreglos había 1 crítico, 4 serios y varios moderados (tabla de arriba).
Contraste calculado (`tests/e2e/contraste.py`): todos los pares de texto >= 4.5:1 en claro y oscuro; bordes de control (`--line-2`) >= 3.9:1. Único par bajo 3:1: `--accent` sobre `--bg` claro (2.5:1), usado solo como marco decorativo del visor (el texto de acento usa `--accent-text`).
Revisadas capturas a 320/360/390/768/1280 en ambos temas: sin solapes ni cortes tras los arreglos.

## 3) Robustez
| Caso | Resultado |
|---|---|
| Servidor caído y vuelto a levantar con Recibir abierta | Indicador pasa a "Sin red" (rojo), la placa leída sin red queda "Sin enviar: toca para reintentar", se **reenvía sola** al reconectar el WS (reconexión automática), no se pierde nada (el servidor tiene todas las lecturas) |
| 500 simulados (`page.route`) | Escaneo: fila pendiente con reintento automático; confirmar: error en la hoja sin cerrarla; las 4 pantallas con la API en 500 no lanzan excepciones y muestran estados vacíos/avisos |
| Respuestas lentas (3 s en POST) | Confirmar lote, Programar (guardar MAC) y Pruebas masivo deshabilitan el botón y envían 1 sola petición con doble clic; Emparejar auto también (otro agente añadió el guard mientras se probaba) |
| Datos vacíos (BD nueva) | Las 7 páginas muestran estados vacíos sin errores |
| Textos largos / hostiles | QR de 165 caracteres, HTML en el QR (se muestra como texto, sin ejecutar), filtros de 400 caracteres: sin scroll horizontal ni roturas |
| 300 PCB | Recibir con 300 en el borrador: listo en ~1.0 s; emparejar auto 100 tarjetas 0.84 s; Monitor inventario (301 filas) 0.4 s; sincronizar Excel 0.7 s; DYMO con 100 tarjetas 1.5 s. Mayor tarea larga 289 ms (primer escaneo, calentamiento). UI no se congela |
| Recarga a mitad de flujo | Borrador de Recibir persiste (servidor); modo de Pruebas persiste; **se pierde** la MAC a medio teclear en Programar y la hoja abierta (esperable) |
| Botón Atrás | Entre pantallas vuelve bien (pestaña activa correcta, WS reconecta). **Con una hoja abierta, Atrás sale de la página** (las hojas no usan el historial) — ver riesgos |
| Cambio de tema en caliente | Cambia al instante (fondo, `meta theme-color`), persiste entre páginas |
| Móvil horizontal 844x390 | Sin scroll horizontal; visor reducido con `@media (orientation: landscape)` para dejar ver lectura y contadores |

## 4) Rendimiento del escaneo (Chrome de escritorio, QR invertido en `canvas`, jsQR — `BarcodeDetector` no existe en este Chrome de Windows)
| Métrica (30 lecturas, 0 perdidas) | QR 320 px | QR 180 px | QR normal 320 px |
|---|---|---|---|
| QR en fotograma -> sonido (`playScan`) P50 / P95 | **107 / 156 ms** | 99 / 192 ms | 92 / 158 ms |
| -> confirmación visual P50 / P95 | 115 / 164 ms | 110 / 204 ms | 116 / 180 ms |
| -> confirmación del servidor P50 / P95 | 129 / 186 ms | 135 / 225 ms | 145 / 206 ms |
Objetivo < 500 ms cumplido con margen y < 150 ms en mediana. El primer escaneo tras cargar tarda ~340 ms (calentamiento). Incluye el retardo de `captureStream` (1-2 fotogramas); en un celular real dependerá de la cámara y el CPU (no medido).
Carga por página (390x844, sin caché, tras gzip): `/` 199 KB, `/emparejar` 196, `/programar` 193, `/pruebas` 178, `/monitor` 111, `/dymo` 195, `/admin` 89 KB; FCP 64-160 ms, load 75-155 ms; 0 scripts bloqueantes en `<head>` (todos al final del `<body>`), 1 hoja CSS (31 KB). Antes del gzip: 455-565 KB por página.

## No verificado
Cámara y latencia en celular real (Android/iOS), Safari/iOS (`BarcodeDetector`, sonido, `100dvh`, PWA "Añadir a inicio"), impresión DYMO física (aquí DYMO Connect responde "impresora desconectada"), lector de pantalla real (solo axe), Excel de escritorio, red WiFi con pérdidas reales (solo caída total y 500 simulados).

## Riesgos abiertos y preguntas
1. Android: **Atrás con una hoja abierta sale de la página** (y con la cámara activa). Recomendable que `TQT.sheet()` use `history.pushState`/`popstate`; no se implementó porque hojas apiladas (tarjeta -> reemplazo) exigen gestionar la pila con cuidado.
2. Sin preferencia guardada el tema es siempre oscuro; `DISENO.md` dice que respeta `prefers-color-scheme` (el `<script>` de cabecera lo ignora). ¿Decisión de diseño (oscuro por defecto en taller) o error? No se cambió.
3. Inconsistencia de "incompleta": Emparejar marca "Incompleta" a una tarjeta sin R3, mientras el Monitor ("Todo en orden: ninguna tarjeta incompleta") y `/api/stats.incompletas` solo cuentan sin R1 o sin R2 (SPEC: completa = R1+R2). ¿R3 obligatoria?
4. Avisos de recepción ruidosos cuando la serie salta mucho (con 0084 entre 0001-0003 dice "faltan 80 series"). Es correcto según la regla de huecos, pero asusta; ¿tope o agrupar?
5. Sincronizar Excel muestra un aviso por tarjeta ("no está en la lista de la plantilla; usé la fila 2 (antes ID 0011)"), 4 avisos en un lote de 4; y R3 no aparece en el Excel (plantilla sin columna). Área del agente Excel; se reporta.
6. Copys menores: Programar dice "Todo tiene MAC" aun cuando no hay ninguna placa; la tabla del monitor dice "No hay placas con esos filtros" con la BD vacía.
7. La MAC a medio teclear y la placa activa de Programar no sobreviven a una recarga (posible `sessionStorage`).
8. Los tests de navegador dependen de Chrome instalado y de un servidor aislado; no se incluyen en `unittest discover`.
9. Nota de proceso: otro agente mató por error todos los `python run_server.py` durante la sesión (el servidor 8457 se relanzó); no es un bug de la app.
