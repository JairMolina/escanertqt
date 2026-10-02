# Pruebas de navegador (Playwright + Chrome)

Scripts de QA E2E/UX. **No** los recoge `python -m unittest discover` (no son `test_*.py` y necesitan navegador y un servidor).
Las comprobaciones que corren sin navegador están en `tests/test_qa_e2e.py`.

## Requisitos
- `pip install playwright` y Google Chrome instalado (se usa `channel="chrome"`; si no está, cae a Chromium: `python -m playwright install chromium`).
- Para `auditoria.py` y `axe_estados.py`: bajar axe-core a una carpeta TEMPORAL (no al repo) y apuntar `TQT_AXE`:
  `curl -L -o %TEMP%\axe.min.js https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js`
- Un servidor **aislado** (nunca la BD real): `python tests/e2e/servidor.py 8457 <carpeta_tmp>` (usa `TQT_DB_PATH`, `TQT_EXCEL_DIR`,
  `TQT_EXPORTS_DIR`, `TQT_BACKUP_DIR` temporales, contraseña admin `ClaveQA-12345`, `TQT_HOST_IP=127.0.0.1`), o en Windows desacoplado de la consola:
  `powershell -NoProfile -File tests/e2e/reinicia.ps1 -Tmp <carpeta_tmp> [-Keep]` (mata el servidor del puerto y arranca uno nuevo; sin `-Keep` borra los datos).

## Variables
`TQT_BASE` (por defecto `https://127.0.0.1:8457`), `TQT_SHOTS` (capturas y JSON), `TQT_AXE`, `TQT_TMP` (carpeta del servidor, para `robustez.py caida`), `TQT_EXCEL_DIR`.
Usa rutas absolutas y sin `..` para `TQT_SHOTS` (Chrome no abre `--use-file-for-fake-video-capture` con `..` en la ruta).

## Scripts
| Script | Qué hace |
|---|---|
| `flujo.py` + `flujo2.py` | Recorrido completo sobre un servidor NUEVO: foto real invertida (cámara falsa de Chrome) + QR generados en pantalla, 12 PCB, confirmar, emparejar, programar 8 MAC tecleadas, pruebas (OK / FALLA), reemplazo de R3 fallada por una suelta (tarjeta impar), monitor, DYMO (4 líneas), sincronizar Excel, /admin. Ejecutar en ese orden. |
| `auditoria.py` | 7 páginas x 5 tamaños (320x640 ... 1280x800) x 2 temas: consola, peticiones 4xx/5xx/externas, scroll horizontal, objetivos < 44 px, texto cortado, etiquetas, pestaña activa, `<title>`/lang/viewport/favicon/manifest, foco por Tab y axe-core. Salida `auditoria.json`. |
| `axe_estados.py` | axe-core con hojas abiertas, tarjeta abierta, teclado MAC, monitor y admin con sesión. |
| `latencia.py [N]` | Latencia QR en fotograma -> sonido / confirmación visual / confirmación del servidor (P50/P95) y peso/tiempos de carga de cada página. |
| `foto_real.py [N]` | Lee `tests/fixtures/qr_R3_V30_0084_invertido.jpg` con la cámara falsa de Chrome N veces. |
| `robustez.py [sección...]` | `caida` (mata y relanza el servidor con la página abierta), `http500`, `lento` (3 s: doble envío), `largo`, `recarga` (+ Atrás), `tema`, `horizontal`. |
| `volumen.py vacio\|volumen` | Estados vacíos (BD nueva) y 300 PCB (tareas largas, tiempos de pintado, Excel, DYMO). |
| `contraste.py` | Contraste WCAG de los tokens de `app.css` (también lo usa `tests/test_qa_e2e.py`). |

Nota: en `/dymo` Chrome registra `ERR_CONNECTION_REFUSED` hacia `127.0.0.1:41951-41960` (descubrimiento del servicio local DYMO Connect): es esperado y los scripts lo filtran.
