# QA Seguridad / Admin / Docker

Alcance: (A) /admin y autenticación, (B) auditoría de seguridad de toda la API, (C) Docker y despliegue.
Pruebas en vivo: servidor local en 8456 (`TQT_DOCS=1`, carpetas temporales) + Playwright; Docker con `-p qadocker` sobre una **copia** del árbol (scratchpad), para no tocar `certs/`, `respaldos/`, `excel_mensual/` ni `exports/` reales. Docker terminado con `down -v`; sin contenedores ni volúmenes residuales.

## Bugs encontrados y arreglados

| # | Bug | Sev. | Causa | Arreglo | Test |
|---|---|---|---|---|---|
| 1 | `POST /api/lotes` aceptaba cualquier `ruta_excel` (p. ej. `C:/Windows/win.ini`) y `POST /api/excel/sync` la usaba como destino de escritura, sin contraseña | **Alta** | `ruta_permitida` solo se aplicaba al parámetro `excel_path`, no a la ruta guardada en el lote | `app/routers/api.py` (create_lote valida) y `app/routers/excel_dymo.py` `ejecutar_sync_excel` (valida también la ruta guardada) | `test_ruta_excel_del_lote_no_puede_apuntar_fuera`, `test_sincronizar_ignora_rutas_peligrosas_guardadas_en_lotes_antiguos` |
| 2 | `GET /api/admin/export/excel?ruta=CON` / `aux` / `NUL.xlsx` / `COM1.xlsx` / `%2e%2e/x.xlsx` creaba carpetas/archivos con nombres reservados de Windows **dentro del proyecto** (imposibles de borrar desde el Explorador). Además se podía sobrescribir `templates/*.xlsx`. Reproducido: los creé en el árbol real y los limpié con `\\?\` | **Alta** | `_raiz_permitida` admitía todo el proyecto y no filtraba nombres reservados | `ruta_permitida()` en `app/routers/excel_dymo.py:60` (NUL, nombres reservados, `templates/` solo en escritura; `verify`/`import` siguen pudiendo leer la plantilla) | `test_export_ruta_no_escribe_fuera_ni_nombres_reservados` |
| 3 | Ids enormes (`/api/tarjetas/10**30`, `ids:[10**30]`, `lote_id=`, `offset=`) devolvían **500** (OverflowError de SQLite) en ~15 rutas | Media | Sin manejo global | `@app.exception_handler(OverflowError)` -> 422, `app/main.py:75` | `test_enteros_gigantes_dan_422_no_500`, `test_objetivos_inexistentes_e_invalidos_sin_respaldo` |
| 4 | Sin cabeceras de seguridad (nosniff, X-Frame-Options, Referrer-Policy, frame-ancestors) ni `Cache-Control` en `/api` | Media | No existían | Middleware `seguridad` en `app/main.py:98` | `test_cabeceras_de_seguridad`, `test_api_no_se_guarda_en_cache` |
| 5 | CSRF: cualquier web abierta en el celular/PC podía hacer POST sin cuerpo (`/api/recepcion/confirmar`, `/api/emparejar/auto`, `/api/excel/sync`, activar lote…) con `fetch(mode:'no-cors')` | Media | Sin comprobación de `Origin` | Mismo middleware (403 si `Origin` != `Host` en métodos que cambian datos) | `test_csrf_...`, `test_origen_distinto` |
| 6 | WebSocket `/ws` aceptaba conexiones desde otros sitios (leer eventos/stats de la planta, emitir `BROADCAST_SCAN`) | Media | Sin comprobación de `Origin` | `app/routers/ws.py` (cierre 1008) | `test_websocket_entre_sitios_rechazado` |
| 7 | UI /admin: tras **cambiar la clave** el servidor invalida todos los tokens y devuelve uno nuevo, pero `admin.js` no lo adoptaba: la siguiente acción expulsaba al login | Media | Token nuevo ignorado | `app/static/js/admin.js` (submit de `formClave`) | Playwright: "Tras cambiar clave sigue en sesión" (E2E manual, ver abajo) |
| 8 | `respaldar.ps1` **nunca funcionó** en Windows PowerShell 5.1: pasaba el código Python con `python -c` y PS 5.1 elimina las comillas dobles (SyntaxError). Reproducido | **Alta** (los respaldos programados fallaban) | Paso de argumentos a ejecutables nativos | `respaldar.ps1` reescrito: código por stdin (`python -`), `integrity_check`, rotación solo de `tqt_AAAAMMDD_HHMM.db` (30), código de salida | Probado en el contenedor: genera `.db` válido y rota a 30 |
| 9 | `desplegar.ps1`: contraseña de admin con `$`, `#` o comillas se corrompía en `.env` (Compose interpola); `docker compose up` (stderr) y `docker info` abortaban con error crudo bajo `$ErrorActionPreference=Stop` en PS 5.1; regla de firewall con `-Profile Any` sin restringir a la LAN; sin simulación | Media | Escritura de `.env` y manejo de stderr | `desplegar.ps1`: `.env` con comillas simples y UTF-8 sin BOM, `-WhatIf`, `-RemoteAddress LocalSubnet`, validación de IP, aviso si no llega a `healthy` | Probado: contraseña `pa$$w#rd "x" y` llega literal al contenedor; `-WhatIf` no escribe nada; el parser de PowerShell da 0 errores en ambos scripts |

## Matriz ruta x método (¿requiere token?)

Con token (`X-Admin-Token`): todo `/api/admin/*` salvo `GET /estado` y `POST /login`; `GET /api/export/excel`, `POST /api/excel/import`, `POST /api/excel/create-monthly`. Verificado 401 sin cabecera / vacía / manipulada, y 503 con admin deshabilitado.

Abiertas (decisión del usuario, ver ADMIN.md): `/api/config|status|stats|lotes|tarjetas*|pcb*|recepcion*|emparejar*|ajustes|dymo/*`, `POST /api/lotes` (crea lote), `POST /api/lotes/{id}/activar`, `PUT/PATCH/DELETE` de tarjeta y PCB individuales, pruebas, `POST /api/excel/sync`, `POST /api/sync/excel`, `GET /api/excel/verify`, `/cert`, `/ws`.
Candidatas a proteger si el usuario quiere endurecer más (no las cambié, es decisión suya): `POST /api/lotes` y `POST /api/lotes/{id}/activar` (cambian el lote activo de toda la planta), `POST /api/emparejar/auto` y `POST /api/pcb/version` (masivas pero reversibles). Las acciones normales del taller (escanear, MAC, pruebas, etiquetas) deben seguir abiertas.

## Casos que pasaron
- Login correcto/incorrecto/vacío/sin cuerpo/tipo erróneo/100 KB/JSON anidado 50 000 niveles; bloqueo tras 5 fallos (429 + Retry-After, ni la clave correcta entra bloqueado), desbloqueo con reloj inyectado, reinicio del contador tras acierto; admin deshabilitado (503, mensaje claro), clave < 8 = deshabilitado.
- Token: cabecera ausente/vacía, firma o cuerpo alterados, `a.b.c`, bytes no ASCII, Bearer y `?token=` no valen, caducado (30 min), invalidado al cambiar la clave.
- Cambio de clave: <8, igual, actual incorrecta, >200; tokens viejos mueren y el nuevo funciona; la clave sobrevive al reset.
- Destructivas: confirmaciones vacías/minúsculas/espacios/`\n`/cruzadas rechazadas **sin respaldo ni cambios**; objetivos inexistentes 404 sin respaldo; listas de 2001 y enteros gigantes 422; respaldo previo restaurable (`integrity_check ok` y mismos conteos que antes del borrado); bitácora `ADMIN_*`; reset conserva lotes y clave.
- Exportación: solo con token, descarga xlsx, lote inexistente 404, rutas maliciosas (`..`, UNC, `C:\Windows`, reservados, NUL, >500) rechazadas y nada creado en el proyecto.
- SQL injection en `search`, `estado_general`, `q`, `codigo`, `by-mac`, ids y `ids=` de DYMO: parametrizado, sin 500, tabla intacta.
- XSS almacenado (`<img onerror>`, `"><script>` en nombre de lote, operador, notas, firmware, MAC/etapa inválidas): la API responde JSON con `nosniff`; DYMO HTML/SVG/XML lo escapan. **Playwright** en `/`, `/emparejar`, `/programar`, `/pruebas` (y `?q=<img…>`), `/monitor`, `/dymo` (y `?tarjeta=<img…>`), `/api/dymo/preview`, `/api/dymo/svg`, `/admin`: ningún diálogo ni `window.__x` ejecutado. El frontend no usa `innerHTML` en ningún archivo.
- Estáticos: `/static/../`, `%2e%2e`, `..%2f`, `..%5c`, `.env`, `.db`, `certs/key.pem`, `docs/`, `app/*.py`, `/static/CON`, `%00`, directorios -> 404. `/cert` solo entrega el certificado (sin `PRIVATE`). `/docs`, `/redoc`, `/openapi.json` apagados por defecto.
- CORS: sin cabeceras `Access-Control-*`; preflight 405. Métodos inesperados 405. Host falso: sin efecto. Errores 4xx/5xx sin trazas ni rutas del servidor (salvo el mensaje de ruta permitida, que menciona `TQT_EXCEL_DIR`: baja).
- UI /admin (Playwright, 39 comprobaciones): login incorrecto/correcto -> resumen -> seleccionar -> eliminar tarjetas -> eliminar PCB -> vaciar y borrar todo (botón deshabilitado hasta teclear `VACIAR` / `BORRAR TODO` exactos; minúsculas o incompleto no habilita) -> exportar (descarga .xlsx) -> cambiar clave (sigue en sesión) -> 401 devuelve al login y borra la sesión -> cerrar sesión (recargar pide login) -> caducidad (reloj simulado +31 min). Token nunca en la URL ni en localStorage.

## Docker (C)
- Build limpio `--no-cache` OK (~4 s con capas base en caché); imagen 261 MB (63 MB de contenido); usuario `tqt` (uid 10001); `/app` sin `.db`, `.env`, `key.pem`, `docs`, `tests`, `*.md`; `TZ=America/Mexico_City` (hora CST dentro del contenedor).
- Healthcheck pasa a `healthy` en ~10 s; política `unless-stopped`; logs `json-file` 10 MB x 5.
- `docker compose restart` y `down`/`up` **conservan** la BD (volumen `tqt_db`); `down -v` **la borra** (comprobado: tras `down -v` el inventario y los lotes personalizados desaparecen y queda un lote por defecto). Ya está documentado en DESPLIEGUE.md.
- Sin `TQT_HOST_IP` Compose falla con "Ejecuta .\desplegar.ps1 o crea .env".
- Certificado: se reutiliza si la IP está en el SAN; al cambiar `TQT_HOST_IP` (192.168.3.36 -> 10.9.8.7) se regenera (`openssl s_client`: SAN `IP:10.9.8.7`). Nota: cambia también la clave privada, hay que reinstalar el perfil en iPhone.
- Acceso por IP LAN desde esta misma PC (`curl -k https://192.168.3.36:8443/api/config`) OK.
- Respaldo dentro del contenedor (`respaldar.ps1`): `.db` válido, `integrity_check ok`, con 33 archivos programados previos rota a 30 y conserva el respaldo de admin (`..._reset_total.db`) aparte. El respaldo de admin también se crea correctamente en el bind mount `./respaldos` con el usuario no root.
- `desplegar.ps1` y `respaldar.ps1`: 0 errores del parser de PowerShell; `desplegar.ps1 -WhatIf` verificado; DESPLIEGUE.md actualizado a lo que hace el script.

## No verificado / límites
- **Otro dispositivo real en la WiFi**: no hay segundo equipo. Solo probé por la IP LAN desde esta PC. Además **no existe la regla de firewall `Escaner TQT 8443`** en esta PC (no soy administrador y no creé reglas): un celular no conectará hasta ejecutar `desplegar.ps1` como administrador.
- La creación real de la regla de firewall no se ejecutó (solo lectura de la lógica y `-WhatIf`).
- Apagar Docker Desktop para probar el mensaje "no está en ejecución" no se hizo (afectaría a otros agentes); se cambió a manejo robusto de `docker info` y se validó por lectura.
- Reinicio de la PC / arranque automático de Docker Desktop.
- Symlinks: en Windows sin privilegios no se pudieron crear; `Path.resolve()` ya los sigue antes de comprobar la carpeta permitida.

## Riesgos abiertos / preguntas
1. "Cerrar sesión" no revoca el token en el servidor (sin estado): sigue válido hasta 30 min si alguien lo copió. Aceptable en LAN; revocación real requeriría lista de tokens o contador de sesión. ¿Se quiere?
2. `POST /api/lotes` y `activar` siguen abiertos (cualquiera en la WiFi puede cambiar el lote activo). ¿Protegerlos con el token de admin o con PIN de operador?
3. El token vive en `sessionStorage` (por pestaña, no persistente); un XSS futuro podría leerlo. Hoy no hay XSS (sin `innerHTML`); no se añadió CSP de scripts porque las páginas usan un script inline para el tema (habría que moverlo a un archivo).
4. Rotación de `respaldar.ps1` solo cuenta los programados; los de admin se acumulan (documentado en ADMIN.md).
5. Detrás del puente de Docker Desktop todas las IP pueden ser la misma: el bloqueo de 5 intentos sería compartido (fallo seguro, ya documentado).
6. Mensajes de error de ruta y `excel_path` de `/api/excel/sync` muestran rutas del servidor (usuario de Windows): baja, solo LAN.
7. `/api/excel/verify` y `/api/dymo/*` abiertos: leen datos de producción sin contraseña (decisión de diseño v1).

## Resultado de la suite
`python -m unittest tests.test_qa_seguridad`: 33 tests OK. Suite completa `python -m unittest discover -s tests`: **Ran 335 tests ... OK**.

## Archivos tocados (ajenos con Edit mínimo)
`app/main.py`, `app/routers/ws.py`, `app/routers/api.py` (validar `ruta_excel`), `app/routers/excel_dymo.py` (`ruta_permitida` con `solo_lectura`, validar ruta del lote), `app/static/js/admin.js`, `desplegar.ps1`, `respaldar.ps1`, `docs/ADMIN.md`, `docs/DESPLIEGUE.md`, `tests/test_qa_seguridad.py`.
