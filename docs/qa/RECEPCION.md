# QA Recepción (pantalla Recibir y su API)

Puerto usado: 8451 (BD/Excel/exports/respaldos en carpeta temporal del scratchpad). Tests: `tests/test_qa_recepcion.py` (26 pruebas).

## Bugs encontrados y corregidos
| Bug | Sev. | Causa | Arreglo | Regresión |
|---|---|---|---|---|
| Dígitos Unicode (`０００２`, `٠٠١١`, `٣٠`) aceptados como serie/versión y guardados en el nombre | media | `\d` de Python/JS acepta Unicode | `app/database/models.py:153-154` (`re.A`), `app/database/inventario.py` `normalizar_version/serie`, `parsear_qr` (`[0-9]`) | `test_formatos_invalidos`, `test_ajustes_valores_raros` |
| Serie `0000` y versión `0`/`000` aceptadas (QR, manual, PATCH, ajustes) | media | sin validación de rango | `inventario.py:44-59` (`int(s)==0` -> inválido) | `test_formatos_invalidos`, `test_topes` |
| `V030` y `V30` eran PCB distintas (duplicado silencioso) | media | la versión se guardaba con ceros a la izquierda | `normalizar_version` devuelve `str(int(s))`; `parsear_qr` normaliza el QR | `test_version_normalizada_no_duplica`, `test_version_masiva_todo_o_nada` |
| Regex del cliente distinta a la del servidor (`TQT-R1-V30-00001` leía 0000; sin normalizar V030) | baja | `NOMBRE_RE` de `common.js` | `app/static/js/common.js:80-90` (misma regex, rechaza 0, normaliza versión) | UI (manual) |
| Al leer una placa repetida la página se desplazaba hasta su fila y el visor quedaba fuera de pantalla | media | `scrollIntoView` en `duplicated()` | `app/static/js/recibir.js` (solo resalta la fila) | UI (manual) |
| `navigator.vibrate` antes del primer toque genera error de consola en cada lectura | baja | Chrome bloquea vibrate sin activación de usuario | `app/static/js/haptics.js` (`userActivation.hasBeenActive`) | UI (consola limpia) |
| Avisos repetidos: huecos se mostraban dos veces (lista propia + aviso del servidor) | baja | cliente mostraba `huecos` y `avisos` | `recibir.js` `avisosSinHuecos()` | UI |
| Aviso decía "faltan 200 series" cuando eran 300 (lista recortada) | baja | recorte a 200 sin indicarlo | `inventario.py` `listar_recepcion` ("200+") | `test_huecos_recortados_avisan_que_son_mas` |
| Deshacer eliminar convertía una placa QR en "sin QR" (origen MANUAL) | baja | usaba `/api/pcb/manual` | `recibir.js` (usa `/api/pcb/escanear` si origen QR) | UI |
| Con lecturas sin enviar (red caída) se podía confirmar el lote dejándolas fuera | media | botón solo bloqueaba pendientes sin error | `recibir.js` `renderCounters` (bloquea con cualquier pendiente) | UI |
| `pcb/por-codigo` con serie 0000 daría 400 en vez de 404 | baja | efecto colateral de la nueva validación | `inventario.py` `pcb_por_codigo` captura ValueError | cubierto por suite |

## Probado y correcto
- Escaneo: mayúsculas/minúsculas, espacios, `TQT R1 V30 0021`, guiones bajos, versión 1-3 dígitos, serie 1-5 (5 dígitos = INVALIDA), texto largo (301 = 422), vacío (422), solo espacios (INVALIDA), inyección SQL/HTML (INVALIDA o extraída sin efecto), NUL; `tipo_forzado` solo con número (mayúsc./minúsc., versión propia, versión por defecto, QR completo manda); duplicados en RECIBIDA/DISPONIBLE/ASIGNADA/BAJA; eliminada vuelve a poder escanearse.
- Concurrencia: 20 hilos con el mismo QR (1 AGREGADA + 19 DUPLICADA); 45 QR distintos x2 con 16 hilos; 12 hilos por HTTP: sin `database is locked`.
- `/api/recepcion`: conteos, huecos (series existentes fuera del borrador no cuentan), avisos de desbalance; confirmar con/sin ids, parcial, doble confirmación, ids inexistentes/no RECIBIDA (`omitidas`); manual (siguiente serie, cantidad 1-200, tope 9999, todo o nada, versión por defecto/explícita); PATCH (tipo/versión/serie, 409, 400, 404, asignada actualiza tarjeta, no cambia tipo si está montada); versión masiva todo o nada; DELETE por estado; ajustes con valores raros.
- UI (Chrome real, 390x844 y 320x640, cámara falsa): QR invertido real leído y agregado UNA sola vez aunque siga en cuadro 8 s (1 POST); secuencia de cámara con QR que sale y vuelve a entrar (1 POST por QR); lista viva, contadores, editar (incluye choque 409 en pantalla), eliminar + deshacer, chip de versión (guarda; rechaza 0), "Agregar sin QR" x3, resumen de confirmación con huecos/desbalance, confirmar y lista vacía, segundo cliente por WebSocket ve altas y bajas, recarga a mitad de lote conserva todo, red caída (offline y servidor detenido de verdad) -> filas "Sin enviar" que se reenvían solas al volver (verificado con servidor reiniciado), permisos denegados / sin HTTPS / sin cámara muestran mensaje claro. Sin scroll horizontal a 320 px. Consola: solo los errores esperados de las pruebas negativas (409/400, red caída).

## No verificable
- Cámara real de celular, iOS/Safari, sonido audible y vibración física (solo se comprobó que no hay excepciones), BarcodeDetector nativo en Android.
- "Sin HTTPS" se simuló forzando `isSecureContext=false`; no se probó una página http:// real.

## Riesgos abiertos / decisiones de diseño
- El parser del servidor acepta el código como subcadena (`hola TQT-R2-V30-0005 chao`, o una URL con el nombre dentro). Es tolerante a propósito; si se quiere estricto, cambiar `_TARJETA_REGEX.search` por `fullmatch` en `parse_tarjeta_code` (afecta también a la migración).
- Confirmar con `ids: []` confirma TODO el borrador (contrato de "sin ids"); un cliente que envíe lista vacía por error confirmaría todo.
- Cosmético: el selector de cantidad de "Agregar sin QR" deja un hueco vacío a la derecha.
- Tras quitar el escaneo de una placa DISPONIBLE (ya confirmada) no hay UI en Recibir para editarla (solo desde el monitor), como indica el texto de la hoja.

## Preguntas
- ¿Series con `0000` deben rechazarse? (se rechazan ahora; en la planta la primera serie parece ser 0001).
