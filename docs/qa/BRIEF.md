# Brief común para los agentes de QA (léelo completo antes de empezar)

## El proyecto
**Escaner TQT**: web app mobile-first para una planta que fabrica tarjetas electrónicas TQT. Reemplaza un Excel manual.
Flujo real: llegan PCB con un QR grabado (blanco sobre negro, INVERTIDO) que contiene el nombre `TQT-R3-V30-0084` (tipo R1|R2|R3, versión, serie).
1) **Recibir**: la cámara del celular registra cada PCB automáticamente; el operador confirma el lote o edita/elimina. 2) **Emparejar** R1+R2+R3 por número (o tarjetas "impares" tras reemplazar PCB falladas). 3) **Programar**: la MAC de R1 y R2 se TECLEA a mano (R3 no tiene MAC). 4) **Pruebas** (Soldadura, Programación, Prueba PCB, Integración, Prueba Final: PENDIENTE|OK|FALLA|RETRABAJO|NO APLICA → estado general PENDIENTE|EN PROCESO|RETRABAJO|DETENIDO|LIBERADO). 5) **Etiqueta DYMO** 30334 (57×32 mm) con 4 líneas: nombre R1 / MAC r1 (minúsculas) / nombre R2 / MAC r2. 6) **Excel mensual** con la plantilla `templates/Control_Produccion_TQT_Template.xlsx` sin romper fórmulas/validaciones. 7) **/admin** con contraseña (borrar, vaciar, exportar).
Lee `docs/SPEC_v2.md` (contrato de API/dominio), y según tu área `docs/ADMIN.md`, `docs/DYMO.md`, `docs/DISENO.md`, `docs/DESPLIEGUE.md`.

## Estructura
`app/main.py` (FastAPI, páginas), `app/routers/*.py`, `app/database/{db,models,inventario,admin_ops}.py`, `app/services/{excel_sync,dymo_service,admin_auth,admin_dep,ws_manager?}.py`,
`app/static/*.html` + `js/*.js` + `css/app.css` (frontend vanilla, sin CDN), `tests/` (unittest, ~178 tests, ~30 s), `docker-compose.yml`, `Dockerfile`, `desplegar.ps1`.
Páginas: `/` Recibir, `/emparejar`, `/programar`, `/pruebas`, `/monitor`, `/dymo`, `/admin`. WebSocket `/ws`.

## REGLAS DURAS (no negociables)
1. **Nunca toques datos reales**: `tqt_produccion.db*`, `excel_mensual/`, `respaldos/`, `.env`, `certs/`, ni el Excel del Escritorio `Control_Produccion_TQT_Septiembre.xlsx` (solo lectura/copia). Todo servidor/prueba que lances usa carpetas temporales:
   `TQT_DB_PATH=<tmp>/x.db TQT_EXCEL_DIR=<tmp>/xl TQT_EXPORTS_DIR=<tmp>/ex TQT_BACKUP_DIR=<tmp>/bk TQT_ADMIN_PASSWORD=ClaveQA-12345 HTTPS_PORT=<TU PUERTO> TQT_HOST_IP=127.0.0.1` y `python run_server.py` en segundo plano (certificados: usa `certs/` existente, solo lectura; si falla, copia a tmp con la variable que corresponda o usa TestClient). Tu carpeta temporal: el directorio scratchpad de tu sesión (o `tempfile.mkdtemp()`).
2. **Puertos**: usa SOLO el puerto asignado a tu área (ver tu prompt). El puerto 8443 es solo del agente de Docker.
3. **Edición concurrente**: otros 6 agentes editan este mismo árbol a la vez. Usa siempre **Edit** (reemplazos exactos y pequeños), nunca reescribas archivos enteros con Write si ya existen, y relee justo antes de editar. Tu dueño de archivos principal está en tu prompt; puedes arreglar bugs en otros archivos solo con un Edit mínimo y anotándolo en tu informe. No renombres/borres archivos ajenos ni cambies contratos de API sin actualizar `docs/SPEC_v2.md` y los tests afectados.
4. **Tests**: añade pruebas de regresión en `tests/test_qa_<tuárea>.py` (unittest; usa el aislamiento de `tests/_aislamiento.py` como los demás tests; mira uno existente, p. ej. `tests/test_inventario.py`). Corre tu módulo y, al final, la suite completa: `python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED|FAIL:|ERROR:)"`. Si falla algo ajeno a tu cambio, reintenta una vez (otros agentes editan a la vez) y repórtalo.
5. **Entorno Windows**: shell Git Bash (`/tmp` de Bash NO es visible para Python de Windows: usa rutas `C:/...` o `tempfile`). PowerShell disponible. Playwright/Chrome están disponibles para pruebas de navegador (`pip list | grep -i playwright`; si falta el navegador, `python -m playwright install chromium`). Cámara falsa: `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream [--use-file-for-fake-video-capture=archivo.mjpeg|.y4m]`. Imagen de prueba real: `tests/fixtures/qr_R3_V30_0084_invertido.jpg`.
6. **Método**: (a) lee el código de tu área; (b) diseña casos incluidos límites, entradas hostiles, dobles clics, concurrencia, estados vacíos, red caída, orden inesperado; (c) EJECÚTALOS de verdad (API con TestClient o servidor real, UI con navegador y capturas); (d) cada bug real: reprodúcelo, corrígelo con el cambio mínimo correcto, añade test de regresión, vuelve a correr. No "arregles" comportamiento que sea decisión de diseño documentada (SPEC_v2/ADMIN/DYMO); si dudas, repórtalo como pregunta.
7. **Presupuesto**: sé eficiente, tope orientativo ~60 llamadas a herramientas. Si te cortan (límite de sesión), tu progreso debe estar en `docs/qa/<TUÁREA>.md` (actualízalo al ir encontrando/arreglando cosas, no solo al final).
8. **No mientas**: si algo no pudiste verificar (hardware, iOS, Excel de escritorio, impresión), dilo.

## Informe final (breve, español) y archivo `docs/qa/<TUÁREA>.md`
Tabla: bug | severidad (crítica/alta/media/baja) | causa | archivo:línea del arreglo | test de regresión. Luego: casos probados que pasaron, lo no verificable, riesgos abiertos, preguntas para el usuario. Resultado real de la suite completa al terminar.
