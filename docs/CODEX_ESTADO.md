# Estado de Codex: TQT-Web

Actualizado: 2026-10-21 22:56 UTC
Commit de referencia: `df5d11e6492d` (puede no incluir cambios pendientes)

## v1.4.38 (2026-10-23, Claude Code, rama colores-impresora-caiquen)
- Impresora: acento gris grafito (`css/impresora.css`, `impresora_acceso.html`). Caiquén: rojo #EF4444 (`modulos.py` acento, `css/caiquen*.css`, `caiquen*.html`; neutros rotados a tinte rojo). v1.4.37 confirmada en producción.
- Documentación TEAM HW (`modulos.DOCUMENTACION` = `documentacion-hw`, ruta `/documentacion` → `static/documentacion/index.html`, prefijo `/static/documentacion`, icono `ciudad` en inicio.js; entra con /login general). Contenido en `documentacion.js` (`PROYECTOS`: un capítulo por módulo; al agregar un módulo, agregarlo ahí y su foto en `documentacion/img`). Acceso Caiquén: escena J1939 de tractocamión. Portal: `inicio.js` con una órbita por módulo (`it.ang`, `o.w` ∝ k^-1.5, `--p` profundidad, `data-tapada`).
- Evidencia: capturas de /inicio, /caiquen, /impresora , /documentacion (1440/390 y movimiento reducido) y accesos sin errores JS; pruebas de módulos OK.

## v1.4.37 (2026-10-23, Claude Code, commit 8e781da)
- Módulo Caiquén: archivos `caiquen*` clonados de Sigfox (colores rotados a azul acero), `parse_caiquen`/`CAIQUEN_RE` (QR PROVISIONAL CQ-0001), rechazos cruzados en TQT/TPMS/AJ/SL/Sigfox, `modulos.CAIQUEN` disponible, costeo `caiquen` (tarjeta Caiquén).
- Evidencia: test_caiquen + suites de módulos (43 pruebas) OK.
- Pendiente: QR real de Caiquén (ajustar regex en models y common.js).

## v1.4.36 (2026-10-23, Claude Code, commit 3221659)
- `MODULOS_COSTEO` suma `tpms` (tarjeta TPMS) y `speedlocker` (tarjeta SpeedLocker); `tpms.html`/`speedlocker.html` cargan `costeo.js`/`materiales.js` (ns TPMS / SL). v1.4.35 confirmada desplegada (prod sirve `costeo.css`).
- Evidencia: test_costeo (5) + test_materiales (2) OK; importación de los cotizadores reales en BD aislada = Excel (TPMS 439.91, SpeedLocker 544.06).

## v1.4.35 (2026-10-23, Claude Code, rama inventario-modulos → main)
- Inventario de materiales por módulo (`services/materiales.py`, rutas `/api/<slug>/materiales` en `routers/costeo.py`, `js/materiales.js`, estilos en `css/costeo.css`). Placa realizada = `programada_en`; consumo por lista de materiales de Costos (snapshot), devuelto al desprogramar/eliminar; activación por fecha (`costeo_meta.consumo_desde`); AJ asigna RX/TX en `costeo_pcb_tarjeta`.
- Evidencia: test_materiales (2) + test_costeo + qa_version OK.
- Pendiente: alertas por correo de stock mínimo y pedidos (TQT los tiene); autoasignar RX/TX si el QR llega a distinguirlo.

## v1.4.34 (2026-10-23, Claude Code, commit c52e5e0)
- Costos por módulo (opción A, fase 1): pestaña «Costos» en AntiJammer y Sigfox con un solo motor (`services/costeo.py`, `routers/costeo.py` → `/api/<slug>/costos`, `js/costeo.js` con `data-ns`/`data-base`, `css/costeo.css`). Tablas `costeo_componentes`/`costeo_meta` con `modulo`: materiales y tipo de cambio propios por módulo. Costo por tarjeta (cada QR = una tarjeta; AJ RX/TX, Sigfox una), recurrentes (licencia) aparte. Importar Excel del cotizador (filas «RX y TX» repartidas) y exportar con fórmulas.
- Evidencia: test_costeo (4) + sigfox + antijammer + qa_version OK; importando los Excel corregidos da RX 931.47 / TX 875.82 / AJ 1807.29 y Sigfox 1226.74 + licencia 92.50 (igual que Excel recalculado). Capturas 1440/390 sin desborde ni errores JS.
- Pendiente: fase 2 (existencias, movimientos, stock mínimo, pedidos), fase 3 (consumo automático al programar una PCB; requiere saber si un QR AJ es RX o TX), extender a SpeedLocker/TPMS; cargar los cotizadores en producción tras desplegar.
- v1.4.32 y v1.4.33 ya están en main (`57a44de`, `0c65512`).

## v1.4.33 (2026-10-22, Claude Code, commit 0c65512)
- Rama `skudo-sigfox` avanzada (fast-forward) a `57a44de` (v1.4.32 SpeedLocker) para clonar ese módulo.
- Módulo Skudo Sigfox (`skudo-sigfox`, #A855F7), clon de SpeedLocker: `/sigfox`, `/sigfox/acceso`, API `/api/sigfox/*`, tablas `sigfox_pcb`/`sigfox_eventos` (BEGIN IMMEDIATE). QR PROVISIONAL `SF-0001` → `SF-V1-0001` (`models._SIGFOX_REGEX`, `VERSION_SIGFOX = "1"`, espejo `T.esSigfox`); rechazos cruzados con TQT/TPMS/AntiJammer/SpeedLocker.
- Evidencia: test_sigfox + test_speedlocker + test_antijammer + test_tpms + test_qa_version_hoy OK (35 tests); `node --check` OK en common/recibir/antijammer/speedlocker. Pendiente: foto del QR real, prueba con celular y Docker.

## v1.4.32 (2026-10-22, Claude Code, commit 57a44de)
- Módulo SpeedLocker (`speedlocker`, #38BDF8), clon de AntiJammer: `/speedlocker`, `/speedlocker/acceso`, API `/api/speedlocker/*`, tablas `speedlocker_pcb`/`speedlocker_eventos` (`_asegurar` con BEGIN IMMEDIATE). QR real `SL-0024` → `SL-V2-0024` (sin versión = V2, `models.VERSION_SPEEDLOCKER`) (leído de foto de placa V2.0) (`models._SPEEDLOCKER_REGEX`, espejo `T.esSpeedlocker`); rechazos cruzados con TQT/TPMS/AntiJammer.
- Evidencia: test_speedlocker + test_antijammer + test_tpms + test_qa_version_hoy OK (29 tests); `node --check` OK en common/recibir/antijammer. Pendiente: QR real de la placa, prueba con celular y Docker.

## v1.4.30–v1.4.31 (2026-10-22, Claude Code, rama tpms-boton-escaneo → main)
- v1.4.30: TPMS con «Botón de escaneo» en la cabecera (`js/tpms_escaner.js`: `/api/escaner/*`, WS `ESCANEO_REMOTO` + sondeo HTTP). Recibir registra la placa y Consultar abre su ficha.
- v1.4.31: módulo Skudo AntiJammer (`skudo-antijammer`, #39FF14), clon de TPMS: `/antijammer`, `/antijammer/acceso`, API `/api/antijammer/*`, tablas `antijammer_pcb`/`antijammer_eventos`; `_asegurar` con BEGIN IMMEDIATE (fix v1.4.29). QR real `SJ_0052` → `SJ-V1-0052` (`models._ANTIJAMMER_REGEX`, espejo `T.esAntijammer`); Escáner TQT y TPMS lo rechazan.
- Evidencia: test_antijammer + test_tpms + test_qa_version_hoy OK; `node --check` OK; Docker local 1.4.31. Sin prueba con celular real vinculado.

## Avance reportado
Comandos integrado y publicado en GitHub JairMolina/escanertqt, rama codex/comandos-r1-local, commit funcional df5d11e, sobre web1.4.28/main7fe97eb. Gestion > Comandos es nativo, con37 comandos y28 valores de fabrica, filtros, comparacion, favoritos, constructor reactivo y catalogo extensible. Plataforma inicial; CRLF manual solo Serial/GPS; BLE y acuse originales. URL local http://localhost:18086/monitor#/comandos, base de prueba nueva. Git pull --ff-only origin main completo sin cambios remotos nuevos y push de rama confirmado. No se desplego produccion ni se integro a main.

## Siguiente paso
Revisar/integrar codex/comandos-r1-local a main cuando se solicite; despliegue de produccion pendiente de instruccion expresa. Checkout activo C:/Users/usuario/Documents/Codex/2026-10-19/new-chat/work/tqt-web-comandos. Checkout registrado anterior permanece con su rama y cambios documentales, sin reset/stash. Consultar docs/COMANDOS_R1_INTEGRACION.md; completar sincronizacion central del presente checkpoint.

## Evidencia
52Python,9Node,16escenarios Playwright y enlace movil aprobados; clipboard real y capturas1440/1024/390 claro/oscuro sin desborde ni errores JS/HTTP. Compose/build OK, contenedor tqt-comandos-qa-web-1 healthy en127.0.0.1:18086. git pull --ff-only origin main: Already up to date. CM git push: Commits enviados codex/comandos-r1-local. Sin datos, capturas, contrasenas de QA ni bases en commit. CM, ui-ux-pro-max y ECC E2E/verificacion aplicados.
