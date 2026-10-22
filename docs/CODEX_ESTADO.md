# Estado de Codex: TQT-Web

Actualizado: 2026-10-21 22:56 UTC
Commit de referencia: `df5d11e6492d` (puede no incluir cambios pendientes)

## v1.4.33 (2026-10-22, Claude Code, rama skudo-sigfox, sin commit)
- Rama `skudo-sigfox` avanzada (fast-forward) a `57a44de` (v1.4.32 SpeedLocker) para clonar ese módulo.
- Módulo Skudo Sigfox (`skudo-sigfox`, #A855F7), clon de SpeedLocker: `/sigfox`, `/sigfox/acceso`, API `/api/sigfox/*`, tablas `sigfox_pcb`/`sigfox_eventos` (BEGIN IMMEDIATE). QR PROVISIONAL `SF-0001` → `SF-V1-0001` (`models._SIGFOX_REGEX`, `VERSION_SIGFOX = "1"`, espejo `T.esSigfox`); rechazos cruzados con TQT/TPMS/AntiJammer/SpeedLocker.
- Evidencia: test_sigfox + test_speedlocker + test_antijammer + test_tpms + test_qa_version_hoy OK (35 tests); `node --check` OK en common/recibir/antijammer/speedlocker. Pendiente: foto del QR real, prueba con celular y Docker.

## v1.4.32 (2026-10-22, Claude Code, rama speedlocker, sin commit)
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
