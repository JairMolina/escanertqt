# Despliegue 1.4.81 — 2026-10-31

## Resultado

Orange Pi pasó de `8e48393` / 1.4.80 a `2c05557` / 1.4.81 por fast-forward; GitHub `main` también (sin force push). `2c05557` es el merge de `bc987a8` (rama `comandos-pruebas-auto-1.4.78`, un commit sobre `02f93ee`) sobre `8e48393`, porque `main` llevaba el merge y los docs de 1.4.80 (único conflicto: la cabecera de `docs/CODEX_ESTADO.md`). No incluye «R3 automática». No toca firmware, motor, station/ ni esquema de BD.

Cambio: tras PPON/POFF en el panel «Comandos», la web pide STATUS y lee los sensores del perno hasta ~30 s (PPON espera ON 0 · OFF 1; POFF espera ON 1 · OFF 0) e informa «SÍ leyó… se destrabó» (MOV antes → después), «ya estaba» o «NO leyó… sigue trabado». `GET /api/pruebas-auto/banco` expone `estado.sensores` (ON/OFF/TQT/MOV/err/PB); `fields` sigue sin exponerse.

## Antes de publicar

- `python -m unittest tests.test_pruebas_auto tests.test_qa_version_hoy` sobre `2c05557`: 34 tests OK en 41,25 s (contenedor desechable de `escaner-tqt:web` + `httpx2`; nada instalado en producción).
- Campaña «Prueba8» (`8ca730d8a0fcf32b55c0a6af`): `activa`, 19 ciclos, ningún run no terminado, 0 jobs STM32 activos.

## Respaldo y aplicación

- `/backups/predeploy_1.4.81_20261031.db` (54 321 152 bytes, `sqlite3.backup` por pasos, 6,8 s). SHA256 `1be58287260bf379e798f65a4defd35cb9162d23d7bf45870302fb3994116e6a`; `quick_check` e `integrity_check` = ok.
- Checkout: `fetch` + `merge --ff-only 2c05557` (alpine/git). Solo `tqt`: `docker compose -f servidor/compose.yml up -d --no-deps --no-build --force-recreate tqt`. Cloudflared sin tocar (Up 9 días).

## Verificación posterior

- Contenedor `healthy`; `/api/health` interno y público `{"ok":true}`; `APP_VERSION 1.4.81`; `login.js?v=1.4.81.639ba5fe`.
- `/pruebas-automaticas` 302 sin sesión; `/api/pruebas-auto/estado`, `/api/pruebas-auto/banco` y `POST /api/pruebas-auto/comando` 401 «Sin sesión.» (sin sensores sin sesión).
- 430 archivos de `app/` y `station/`: SHA256 iguales entre checkout y contenedor; `pruebas_auto.html` `62bb4d4a…`, `pruebas_auto.js` `c1d98ec4…`, `pruebas_auto.css` `f98500d7…`, `routers/pruebas_auto.py` `a5ca2885…`, `services/pruebas_auto.py` `f9118ded…`, `config.py` `2ce2288a…`, iguales a los blobs de Git.
- `quick_check` = ok. Contra el respaldo: cero IDs perdidos en pcb_inventario (446), tarjetas_produccion (100), escaneos (2541), stm32_jobs (223), tqt_test_runs (190), tqt_test_commands (662), esp32_ota_jobs (93), tqt_resistencia (10), tqt_resistencia_ciclos (75); cero filas modificadas en pcb_inventario y tarjetas_produccion.
- Prueba8: `activa`, mismo `actualizado` (1793468633.9114878), 19 ciclos, sin ciclo en curso. No se pausó, detuvo ni interrumpió.
- Logs 3 min tras el arranque: 0 errores 5xx, Traceback o `database is locked`.

## Límites y pendientes

- No se probó en navegador ni con la Raspberry real. No se envió PPON/POFF/STATUS ni ningún comando físico a la R1.
- Pendiente (lo prueba el usuario): pausar la campaña, pulsar ON/OFF y revisar que el mensaje diga si el sensor leyó la llegada del perno («SÍ leyó» / «ya estaba» / «NO leyó»); confirmar que MOV cambia.
- Rollback: `reset --hard 8e48393` en el checkout + `restart tqt` (código 1.4.80 = 02f93ee); la BD no cambió de esquema.
