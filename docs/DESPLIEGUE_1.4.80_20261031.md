# Despliegue 1.4.80 — 2026-10-31

## Resultado

Orange Pi pasó de `20adc8f` / 1.4.79 a `b92279f` / 1.4.80 por fast-forward; GitHub `main` también (sin force push). `b92279f` es el merge de `02f93ee` (rama `comandos-pruebas-auto-1.4.78`, con `6bc5738`, `00bda31` y `02f93ee`) sobre `20adc8f`. Único conflicto: la cabecera de `docs/CODEX_ESTADO.md`. No incluye «R3 automática». No toca firmware, motor, station/ ni esquema de BD (el marcador `destrabe` va en el JSON de `tqt_test_runs.context`).

Nota: lo desplegado como 1.4.79 era `9236b54` (+ docs `20adc8f`); `6bc5738` (PPON/POFF con la tarjeta de la campaña activa o pausada) no estaba en producción y entra con 1.4.80.

## Antes de publicar

- `python -m unittest tests.test_pruebas_auto tests.test_qa_version_hoy` sobre `b92279f`: 33 tests OK en 36,95 s (contenedor desechable de `escaner-tqt:web` + `httpx2`; nada instalado en producción).
- Campaña «Prueba8» (`8ca730d8a0fcf32b55c0a6af`): `activa`, 19 ciclos guardados, ningún run no terminado, 0 jobs STM32 activos.

## Respaldo y aplicación

- `/backups/predeploy_1.4.80_20261031.db` (54 321 152 bytes, `sqlite3.backup` por pasos, 6,9 s). SHA256 `f60cc441f84d56be9e7b6fc0aa434bd3036b5272f0c826f7cbe3ce1d05214f17`; `quick_check` e `integrity_check` = ok.
- Checkout: `fetch` + `merge --ff-only b92279f` (alpine/git). Solo `tqt`: `docker compose -f servidor/compose.yml up -d --no-deps --no-build --force-recreate tqt`. Cloudflared sin tocar (Up 9 días).

## Verificación posterior

- Contenedor `healthy`; `/api/health` interno y público `{"ok":true}`; `APP_VERSION 1.4.80`; `login.js?v=1.4.80.639ba5fe`.
- `/pruebas-automaticas` 302 sin sesión; `/api/pruebas-auto/estado` y `POST /api/pruebas-auto/comando` 401 «Sin sesión.».
- 430 archivos de `app/` y `station/`: SHA256 iguales entre checkout y contenedor; `pruebas_auto.html` `62bb4d4a…`, `pruebas_auto.js` `a27c9169…`, `pruebas_auto.css` `b037c60a…`, `routers/pruebas_auto.py` `a5ca2885…`, `services/pruebas_auto.py` `34aa0a09…`, `config.py` `cb436980…`, iguales a los blobs de Git.
- `quick_check` = ok. Contra el respaldo: cero IDs perdidos en pcb_inventario (446), tarjetas_produccion (100), escaneos (2541), stm32_jobs (223), tqt_test_runs (190), tqt_test_commands (660), esp32_ota_jobs (93), tqt_resistencia (10), tqt_resistencia_ciclos (75); cero filas modificadas en pcb_inventario y tarjetas_produccion.
- Prueba8: `activa`, mismo `actualizado` (1793468633.9114878), 19 ciclos, sin ciclo en curso. No se pausó, detuvo ni interrumpió.
- Logs 3 min tras el arranque: 0 errores 5xx, Traceback o `database is locked`.

## Límites y pendientes

- No se probó en navegador (no hay en la Pi) ni con la Raspberry real. No se envió PPON/POFF ni ningún comando físico.
- Pendiente (lo prueba el usuario): con un ciclo en curso, pulsar ON/OFF → confirmar → la campaña queda pausada y se envía el comando → reanudar; el ciclo interrumpido queda `destrabe` y no cuenta como falla. Revisar que la barra de pausa entre ciclos ya no parpadea. Probar también PPON/POFF con la tarjeta de la campaña activa/pausada (6bc5738).
- Rollback: `reset --hard 20adc8f` en el checkout + `restart tqt`; la BD no cambió de esquema.
