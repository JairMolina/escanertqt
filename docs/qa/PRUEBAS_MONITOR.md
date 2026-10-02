# QA Pruebas de calidad / Monitor / Lotes / WebSocket

Agente QA-PRUEBAS-MONITOR. Tests: `tests/test_qa_pruebas.py` (14 tests). Servidor real en el puerto 8453 con carpetas temporales; navegador Chrome + Playwright (390x844 y 1280x800).

## Bugs encontrados y corregidos

| Bug | Sev. | Causa | Arreglo | Test |
|---|---|---|---|---|
| El monitor mostraba 0 PCB y daba 422 en consola: pedía `/api/pcb?limit=5000` y el backend limita `limit` (el tope cambió a 1000 mientras otro agente editaba) | alta | Tope fijo del front frente a un límite del backend | `app/static/js/monitor.js` `fetchAll()` pagina inventario (1000) y tarjetas (500) hasta traerlo todo | UI manual (302 tarjetas / 906 PCB: KPIs = `/api/stats`) |
| Broadcast WS secuencial: un celular lento o colgado frenaba el aviso a todos | alta | `await send_text` uno por uno sin timeout | `app/routers/ws.py` `broadcast`: `asyncio.gather` + `wait_for(SEND_TIMEOUT=3s)`, el lento se descarta | `test_cliente_lento_no_bloquea` |
| Un mensaje WS JSON no-objeto (`[1]`, `123`, `null`, `{"action":null}`) lanzaba AttributeError y cerraba el socket del cliente | media | `msg.get` sin validar tipo | `ws.py` valida `dict` y `str(action or "")` | `test_ping_pong_y_mensajes_hostiles` |
| Un cliente WS podía emitir `TARJETA_ESCANEADA` a todos con payload arbitrario (`BROADCAST_SCAN`), evento que la SPEC dice que ya no existe | media | Acción heredada de v1 | `ws.py`: ahora responde ACK, no reenvía | mismo test |
| Conexión WS que se caía durante el saludo inicial quedaba registrada (fuga en `active_connections`); además `get_stats` bloqueaba el event loop | media | Sin try/except tras `accept`; llamadas DB síncronas en async | `ws.py` `connect`: `run_in_threadpool` + `disconnect` en error | cubierto por los tests de WS |
| Búsqueda `search=%` o `_` devolvía TODAS las tarjetas (comodines LIKE) | media | Sin escape | `app/database/db.py` `list_tarjetas`: `ESCAPE '!'` | `test_busqueda_comodines_literales` |
| `POST /api/pruebas/lote` con `lote_id` inexistente daba 500 | media | `NoEncontradoError` sin capturar | `app/routers/pruebas.py` -> 404 | `test_masivo_atomico_...` |
| `estado`/`etapa` vacíos (`""`) se guardaban como PENDIENTE; `no  aplica` (doble espacio) y `prueba-pcb` (guion) daban 400 | baja | Alias `""` y normalización débil | `models.py`: `min_length=1` en `PruebaUpdate/PruebaLoteUpdate`, `re.sub` de espacios/guiones | `test_alias_y_variantes`, `test_invalidos_400_y_404` |
| `POST /api/lotes` con la misma clave en dos peticiones simultáneas: 500 por IntegrityError | baja | Comprobación previa sin atomicidad | `app/routers/api.py` captura `sqlite3.IntegrityError` -> 409 | `test_lotes` (409 secuencial) |
| Refresco en vivo en Pruebas (modo Unitario) reconstruía la vista completa y arrancaba OTRA cámara sin parar la anterior | media | `vistaUnit()` desde el handler WS | `pruebas.js`: `state.repaint` repinta solo el detalle | UI (1 solo `<video>`) |
| Monitor en móvil: la tabla "necesitan atención" ensanchaba toda la página (scroll horizontal) | media | `grid-template-columns: 1fr` sin `minmax(0,...)` en `.two` | `app/static/css/app.css` | UI: `scrollWidth <= innerWidth` |
| "Eliminar" PCB en el monitor borraba sin confirmar, junto a "Guardar" | media | Sin confirmación | `monitor.js` `confirm()` | UI (diálogo capturado, la PCB sigue si se cancela) |
| `GET /favicon.ico` 404 = error rojo en consola de cada página | baja | Sin ruta | `app/main.py` responde 204 | UI |
| Sincronizar Excel con más de 100 tarjetas mostraba solo "sincronizado con 100" y ocultaba los avisos ("218 no caben", "R3 no está en la plantilla") | media | El banner ignoraba `avisos` | `monitor.js` muestra banner de avisos | UI |

## Probado y correcto
- Derivación de `estado_general` con las 3125 combinaciones de 5 etapas (FALLA gana, RETRABAJO, LIBERADO solo con OK/NO APLICA, PENDIENTE, EN PROCESO). Tarjeta sin R2 nunca LIBERADA, aunque se marquen todas OK.
- Cada etapa por cada estado, mayúsculas/minúsculas, `NO APLICA`/`NO_APLICA`/`no-aplica`/`N/A`; 400, 404, 422. `estado_pcb` de R1/R2 derivado de "Prueba PCB".
- Masivo: atomicidad (una inexistente = nada cambia), duplicados en la lista, 0 y 501 ids (422), bitácora `PRUEBA` por tarjeta.
- Concurrencia: 5 hilos marcando 5 etapas de la misma tarjeta, todos 200, resultado LIBERADO correcto.
- `/api/stats` (lote vacío, lote inexistente, sin división por cero), filtros, paginación y límites, caracteres especiales `% _ ' \ !` e inyección SQL, `by-mac` con 4 formatos, aislamiento entre lotes, crear/activar lote (mes/año inválidos, 409 duplicado, 404).
- WS: ping/pong, 50 clientes reciben `PRUEBA_ACTUALIZADA` y `PRUEBAS_LOTE_ACTUALIZADAS` con forma `{evento,timestamp,data}`, `data.stats`, `data.tarjeta`.
- UI `/pruebas` (móvil): buscar por número, expandir etapa, botones color+icono+texto, doble toque sin duplicar, refresco en vivo por WS, búsqueda hostil, masivo con id inexistente muestra el error del backend, Por etapa monta cámara falsa.
- UI `/monitor` con 302 tarjetas y 906 PCB: carga 0,6 s, KPIs idénticos a `/api/stats` (también tras un cambio en vivo: 0 liberadas/12 detenidas), filtros y búsqueda instantáneos, `%` no filtra todo, sync Excel OK y 423 (mensaje "El Excel está abierto"), diálogo de nuevo lote, feed de alertas. Consola JS sin errores (salvo el 423 simulado a propósito). Capturas en el scratchpad de la sesión (`monitor_*.png`, `pruebas_*.png`).

## No verificado / riesgos abiertos
- No probado en iOS/Safari ni con cámara real (solo cámara falsa de Chrome). No se probó "QR de etiqueta" con lector real.
- Monitor con 0 tarjetas: visto en captura (estado vacío correcto, 0 en KPIs); no se revisó con lector de pantalla.
- La plantilla Excel admite 100 tarjetas; un lote de 300 solo sincroniza 100 (ahora se avisa, es decisión de diseño de `docs/SPEC_v2.md` 7.11).
- El servidor de pruebas en 8453 se cayó una vez sin traza en el log (probablemente un proceso ajeno al agente); no pude atribuirlo.
- Los WS de `Deshacer` en Por etapa restauran el estado previo capturado; con dos operadores sobre la misma tarjeta el "deshacer" pisa el cambio del otro (last-write-wins). Pendiente de decisión.

## Preguntas
- ¿Debe `estado_general` inválido en `GET /api/tarjetas?estado_general=XX` responder 400 en vez de lista vacía? Hoy devuelve vacío.

## Suite completa
`python -m unittest discover -s tests`: 301 tests, 1 fallo y 1 error AJENOS a mi área, de otros agentes en curso: `test_excel_dymo.test_04_api_verify` ("No se puede escribir sobre la carpeta de plantillas", Excel) y `test_qa_dymo...test_27` (error en la primera corrida; al re-ejecutar el módulo solo, pasa). Mi módulo: 14/14 OK.
