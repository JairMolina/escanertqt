# Despliegue 1.4.79 — 2026-10-31

## Resultado

Orange Pi pasó por fast-forward de `a8da9ba` / 1.4.77 a `9236b54` / 1.4.79 (panel «Comandos» en Pruebas automáticas). GitHub `main` pasó de `a8da9ba` a `9236b54` también por fast-forward, sin force push. No incluye la tarea «R3 automática» (cambios sin commitear de otro trabajo). No cambia firmware, motor ni esquema de BD.

## Antes de publicar

- `9236b54` en origin (rama `comandos-pruebas-auto-1.4.78`), descendiente directo de `a8da9ba`; árbol de producción limpio en main = origin/main; contenedor en 1.4.77 y healthy.
- `python -m unittest tests.test_pruebas_auto tests.test_qa_version_hoy`: 32 tests OK (contenedor desechable con la imagen de producción más `httpx2`, que la imagen no trae; no se instaló nada en producción).

## Campaña existente

«Prueba8» (`8ca730d8a0fcf32b55c0a6af`, 64 ciclos, pausa 3600 s, 17 ciclos guardados): `activa` antes y después, mismo `actualizado`, sin ciclo en curso al reiniciar (en pausa entre ciclos). No se detuvo ni pausó. El código bloquea el panel «Comandos» y el endpoint durante un ciclo (JS `run`, backend «bloqueado», cubierto por test); no se probó en navegador.

## Respaldo y aplicación

- Respaldo en el servidor: `/backups/predeploy_1.4.79_20261031.db` (54 284 288 bytes, `sqlite3.backup` por pasos, 12,9 s). SHA256 `15d5534eb991831b013b3ea8e3b41582d56e301405b4e464a5d59f2bc7cf8ec9`; `quick_check` e `integrity_check` = ok.
- Checkout `/home/orangepi/escanertqt`: `merge --ff-only 9236b54` con alpine/git.
- Solo `tqt`: `docker compose -f servidor/compose.yml up -d --no-deps --no-build --force-recreate tqt`. Cloudflared conservó ID y hora de inicio.

## Verificación posterior

- Contenedor `healthy`; `/api/health` interno y público `{"ok":true}`; `APP_VERSION 1.4.79`; login público con `login.js?v=1.4.79.639ba5fe`.
- `/pruebas-automaticas` responde 302 sin sesión (redirige a login); `/api/pruebas-auto/estado` y `POST /api/pruebas-auto/comando` responden 401 «Sin sesión.» sin cookie. No se envió ningún comando a la R1.
- 430 archivos de `app/` y `station/` con SHA256 iguales entre checkout y contenedor. `pruebas_auto.js` `eec9860c…2990`, `pruebas_auto.css` `b037c60a…a453`, `pruebas_auto.html` `2e7f2e5f…3ecf`, `routers/pruebas_auto.py` `cf9794ce…e271`, `config.py` `36d0b86e…1a7f`, todos iguales a los blobs de Git.
- `quick_check` = ok. Contra el respaldo: cero IDs perdidos en pcb_inventario (446), tarjetas_produccion (100), escaneos (2541), stm32_jobs (223), tqt_test_runs (188), tqt_test_commands (659), esp32_ota_jobs (93), tqt_resistencia (10); cero filas previas modificadas en pcb_inventario y tarjetas_produccion. Foto previa a nueva actividad.
- Logs 10 min tras el arranque: 0 errores 5xx, Traceback o `database is locked`.

## Límites

No se probó el panel en navegador (no hay en la Pi) ni con la Raspberry real. No se ejecutó PPON/POFF en producción. Rollback disponible: `reset --hard a8da9ba` en el checkout + `restart tqt`; la BD no cambió de esquema, no requiere restauración.
