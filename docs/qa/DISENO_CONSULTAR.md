# Diseño de /consultar, firmware en Programar y selector de lote (agente FRONTEND-DISEÑO)

Prueba real: `tests/e2e/diseno_consultar.py` (servidor aislado en 8462, con y sin `TQT_ADMIN_PASSWORD`; Chrome real, cámara falsa por canvas,
axe-core desde una carpeta temporal). Capturas en `docs/qa/capturas_consultar/` (390x844 y 1280x800, oscuro y claro).
Resultado: TODO OK (aprox. 130 comprobaciones, 16 pasadas de axe con 0 violaciones).

## Crítica de la pantalla original (design-critique / accessibility-review / ux-copy)
| Hallazgo | Sev. | Arreglo |
|---|---|---|
| El visor 16:9 (~200 px) empujaba la ficha bajo el pliegue | alta | Con resultado el visor pasa a franja de 60 px (`data-has="1"`, transición de altura); "Nueva consulta" lo devuelve. En 390x844 se ven el número, el estado y la R1 completa con MAC y firmware |
| El "0021" era un título más | alta | Héroe: mono 56–104 px, rótulo serigráfico "TARJETA", badge de estado y origen de la lectura ("Leída de la etiqueta") |
| Las tres placas eran idénticas, MAC pequeña | media | Cada placa: filete lateral del color de su tipo (R1/R2/R3), chip + nombre mono + ciclo, MAC grande (`user-select:all`) con botón copiar de 44 px, rejilla Hardware / Firmware / Serie que se adapta (container query) |
| Acciones sin jerarquía | media | Primaria "Etiqueta DYMO" (oro), secundaria "Copiar datos", "Nueva consulta" junto al héroe; en móvil la barra de acciones es sticky sobre la barra de pestañas |
| Sin estado de carga; error genérico | media | Esqueleto con `role=status`/`aria-busy`; error con causa (no registrada / sin conexión) + salida "Nueva consulta"; vacío con instrucción |
| Escritorio: una columna larga | media | Visor + búsqueda a la izquierda (sticky, 340 px) y ficha en 3 columnas |
| Movimiento | baja | Entrada suave de la ficha, esqueleto y transición del visor; todo cae a ~0 ms con `prefers-reduced-motion` (regla global existente) |

## Cambios por archivo
- `app/static/consultar.html`, `js/consultar.js`: rediseño completo de la ficha (arriba), rótulos **Hardware V30 / Firmware 4.1**, "Sin firmware" / "Sin MAC todavía" como aviso suave, R3 con la línea "La R3 no lleva MAC ni firmware" (sin dato de firmware). Se lee `p.firmware` de cada PCB (R1/R2). Recarga silenciosa por WebSocket sin parpadeo de esqueleto.
- `app/static/programar.html` (solo versión de caché), `js/programar.js`: **eliminado `renderR3` y todo `firmware_r3`**; al escanear una R3 solo sale el aviso amable. Selector de firmware por rol (`GET /api/firmware`; R1 = Principal, R2 = Respaldo) + "Otra versión…" con campo de texto; guarda MAC + firmware con **una sola** `PUT /api/pcb/{id}/programacion`; recuerda el último firmware por rol (`localStorage`, con try/catch) y lo preselecciona; si la placa ya tiene firmware lo muestra; errores del servidor tal cual. Las filas pendientes muestran "Hardware V30".
- `app/static/js/common.js` (`mountShell`): el sub-título del encabezado es ahora un `<button class="brand-sub">` (con chevrón, zona táctil ampliada) separado del enlace del logo (que sigue yendo a `/`). Abre la hoja **Lotes**: lista de `GET /api/lotes` (nombre "Septiembre 2026", badge Activo, nº de tarjetas), **Usar este lote** (`POST /api/lotes/{id}/activar`; el texto avisa que cambia para todos los celulares), **Ver en el monitor** (`/monitor?lote=<id>`) y **Nuevo lote** (mes + año, `POST /api/lotes` con `{codigo_lote:"AAAA-MM", mes, anio, activo:true}`). Si la respuesta es 401 aparece en la propia hoja "Estas acciones las hace el supervisor" con campo de contraseña, `POST /api/admin/login` y se reintenta la acción; sin clave configurada (503) las acciones son libres y no se pide nada. Sin `confirm()`/`prompt()`. Tras cambiar de lote se actualiza el sub-título y se emite el evento cancelable `tqt:lote-cambiado`; si la pantalla no lo atiende (Recibir/Emparejar) se recarga; Consultar y Programar lo atienden (sus datos son globales).
- `app/static/css/app.css`: bloque nuevo `.brandbox / button.brand-sub`, bloque "consultar: ficha de tarjeta" reescrito y bloque "hoja de lotes". `<span class="brand-sub">` de otras páginas (admin/monitor/dymo) no se toca.
- Versión de caché `?v=20260924d` (CSS/JS) y `common.js?v=20260924n` en index, emparejar, monitor, consultar, programar (no en admin.html: es del otro agente).
- **Ediciones mínimas en archivos ajenos (solo rótulos/lote):** `js/monitor.js` (`/monitor?lote=<id>` deja ese lote seleccionado en la primera carga, sin activarlo en el servidor; "FW" -> "Firmware" leído de `p.firmware`, nunca en R3; cabecera "Versión" -> "Hardware"), `js/emparejar.js` (línea de la ranura: "Hardware V30 · MAC · Firmware X", firmware solo R1/R2), `js/recibir.js` y `index.html` (etiquetas "Versión" -> "Hardware (V)" / "Versión de hardware", con aclaración "no es el firmware"), `tests/e2e/ficha_consultar.py` (R3 en Programar ahora es solo aviso).
- Tests: `tests/test_qa_consulta.py` +`test_frontend_hardware_firmware_y_selector_de_lote` (estático); `tests/e2e/diseno_consultar.py` nuevo.

## Verificado en Chrome real
Cámara falsa lee la etiqueta de 4 líneas -> ficha (0021, R1/R2/R3, MAC, Hardware, Firmware); esqueleto de carga; error 404; vacío; "Nueva consulta" restaura el visor; escritorio con 3 columnas y visor al costado; sin scroll horizontal a 320/390/1280; objetivos >= 44 px en la ficha; consola y red sin errores ni hosts externos; Programar (catálogo, "Otra versión…" vacía avisa sin guardar, una sola PUT `/programacion`, la versión nueva entra al catálogo, la siguiente R1 llega preseleccionada, R2 rotulada "Respaldo", R3 escaneada = aviso); hoja de lotes con clave (401 -> contraseña incorrecta -> correcta -> reintento crea y activa el lote; "Usar este lote" cambia el activo del servidor) y sin clave (crea directo); `/monitor?lote=<id>` selecciona ese lote; axe-core 0 violaciones en vacío, ficha, error, hoja de lotes (con y sin campo de clave), Programar (R1 y R3), claro y oscuro, 390 y 1280.

## No verificado / riesgos
- iOS Safari y móvil físico (solo Chrome de escritorio con viewport móvil); container queries y `color-mix` requieren navegador moderno (Safari 16+).
- Cámara real y lectura de la etiqueta impresa: solo cámara falsa (QR de 4 líneas dibujado en canvas).
- La zona táctil del sub-título del lote se amplía con un pseudo-elemento; no se midió con dedo real.
- Recibir/Emparejar se recargan completos al cambiar de lote (no tienen recarga suave propia; no son de mi propiedad).
- Suite completa: ver el resultado final al pie (`test_api ... certificado_publico` falla por el cambio de nombre `escaner-tqt-ca.crt`, ajeno a este trabajo).
- `docs/SPEC_v2.md` §8 aún menciona firmware de R3 (obsoleto): lo debe corregir el dueño del backend.
