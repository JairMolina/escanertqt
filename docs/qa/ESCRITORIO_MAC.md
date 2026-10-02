# QA — Consola de escritorio, sección MAC y firmware (`#/macs`)

## Archivos
| Archivo | Cambio |
|---|---|
| `app/static/js/sec_macs.js` (nuevo) | Sección completa: Pendientes (captura rápida), Pegar varias (vista previa + guardado por lote), Con MAC (corregir, firmware, borrar). Se registra con `TQTEscritorio.registrar`. |
| `app/static/css/sec_macs.css` (nuevo) | Estilos solo con tokens de `app.css`, claro/oscuro, filas de alto fijo (sin saltos al validar). |
| `app/static/monitor.html` | Una línea `<link>` y una `<script>` en los marcadores `sec_macs`. |
| `app/database/inventario.py` | (a) `programar_lote`: SAVEPOINT por fila. (b) `listar_pcb`: tope de `limit` 1000 -> 5000 (el router ya permitía 5000). |
| `tests/test_qa_programacion_lote.py` (nuevo) | 13 pruebas. |
| `tests/e2e/escritorio_macs.py` (nuevo) | 79 comprobaciones en Chrome real (todas pasan). |

## Bugs encontrados
| Bug | Sev. | Causa | Arreglo | Regresión |
|---|---|---|---|---|
| En un lote, si el firmware de una fila era inválido la MAC de esa fila SE GUARDABA igualmente (fila marcada como error pero MAC escrita) | alta | `guardar_programacion` corre en la transacción compartida del lote; el `ValueError` se capturaba por fila sin revertir la MAC ya escrita | `inventario.py::programar_lote` (SAVEPOINT/ROLLBACK TO por fila) | `test_firmware_invalido_no_guarda_la_mac` |
| `GET /api/pcb?limit=5000` devolvía como mucho 1000 filas (la pantalla de pendientes/Con MAC quedaba truncada en silencio) | media | `min(limit, 1000)` en `listar_pcb` | `inventario.py::listar_pcb` | `test_lista_pcb_admite_limit_5000` (comprobación funcional básica; no siembra >1000) |

## Lo probado (pasa)
- Unittest: simular no guarda; guardado parcial con error por fila; MAC repetida dentro del lote y contra la BD; R3 rechazada; placa inexistente / sin identificar; `nombre` tolerante (`  tqt r2 v30 0010 `, `MAC: …`); firmware inválido; 500 items OK y 501 / lista vacía -> 422; misma MAC desde dos lotes simultáneos (solo una gana); la respuesta no incluye el `pcb` completo.
- E2E (Chrome, servidor aislado en 8465, datos sembrados por API): 20 MAC tecleadas con Enter encadenado (el foco salta solo); pegado en 7 formatos (`MAC: …`, `-`, `.`, espacios, `mac=`, con nombre de placa delante); Esc deshace; Backspace no se atasca en `:`; repetida en pantalla (ambas filas marcadas, Enter no guarda); repetida contra la BD (dice de qué placa); 409 del servidor mostrado tal cual; red caída y reintento con Enter; firmware por rol y "Otra versión…" (entra al catálogo); filtros; pegado masivo con vista previa (3 correctas / 5 con problema, R3, no registrada, formato, repetida) y "Revisar no guarda"; aviso de no deshacer + confirmación; guardado parcial; modo "asignar en orden"; Con MAC: corregir en sitio, Esc, firmware al elegirlo, repetida, borrar con confirmación en pantalla; dos pestañas (WS) sin perder lo tecleado ni el foco; teclado puro (flechas en pestañas, ↑/↓, Tab/Shift+Tab); 1440x900 y 1024x768 en oscuro y claro sin scroll horizontal de página; axe-core 0 violaciones (pendientes, pegar, con MAC × 2 tamaños × 2 temas); consola limpia y sin peticiones externas.
- Capturas: `docs/qa/escritorio/macs_*.png` (pendientes, duplicado, error de servidor, pegar previa/resultado, con MAC, borrar).

## Decisiones de diseño
- Guardar una fila en Pendientes la deja visible con ✓ (no desaparece bajo el cursor) hasta "Quitar guardadas". Si otra persona guarda una placa en la que se está tecleando, la fila queda marcada "ya no está pendiente" en vez de desaparecer.
- El firmware puede quedar en "Elegir…" (se guarda solo la MAC); recuerda el último por rol (localStorage con try/catch) y "Aplicar firmware R1/R2" lo pone a todas las visibles.
- Sonido apagado por defecto (toggle propio `tqt.macs.sonido`; no encontré un toggle general al que respetar). "Guardadas hoy" es un contador local del navegador (`tqt.macs.hoy`), no del servidor.
- El pegado masivo envía en tandas de 500 y detecta MAC repetidas dentro del texto en el cliente (así la vista previa no depende de las tandas).
- A ≤1180 px se oculta la columna "Hardware" (el nombre ya contiene V30).

## No verificado / riesgos
- Suite completa: 413 tests, 3 fallos AJENOS a mi trabajo, causados por el armazón nuevo (`monitor.js` eliminado, `/monitor` sin `<h1>`/`brand` a `/`): `test_qa_consulta.TestPruebasEliminado.test_frontend_hardware_firmware_y_selector_de_lote`, `...test_logo_del_monitor_lleva_al_escaner`, `test_qa_e2e.TestPaginasEstaticas.test_metadatos_por_pagina`. Todo lo demás pasa (incluido mi módulo).
- No probado con >1000 pendientes reales (rendimiento del DOM con 5000 filas); "Con MAC" pagina de 200 en 200.
- No probado con lector de pantalla real (solo axe-core y revisión de roles/etiquetas); sin pruebas en Safari/Firefox.
- El servidor de pruebas anterior compartió por error la carpeta `scratchpad/srv` (existía de otro agente) durante ~1 min: solo se abrió su `x.db` (init idempotente, sin escribir datos).
- Pregunta: ¿el "Guardadas hoy" debería salir del servidor (bitácora de movimientos) para que sea común a todos los operarios?
