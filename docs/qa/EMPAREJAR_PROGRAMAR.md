# QA Emparejar / Programar

Tests: `tests/test_qa_emparejar.py` (20 tests, API con TestClient, incluye concurrencia con hilos). UI: Playwright + Chrome real (cámara falsa), servidor aislado en el puerto 8452 con BD temporal.

## Bugs

| Bug | Sev. | Causa | Arreglo | Regresión |
|---|---|---|---|---|
| `PUT /pcb/{id}/mac` aceptaba MAC multicast (`01:00:5E:…`) | media | solo se rechazaban 00…/FF… | `app/database/inventario.py` `set_mac` (~l.476-482) | `TestMAC.test_invalidos` |
| MAC con octetos separados por espacios (`70 4b ca 5b 9f 6e`) daba 400 | media | `extract_mac` solo admite `: - .` | `inventario.py` `set_mac` (reintento sin espacios); `common.js` `parseMac` igual | `TestMAC.test_formatos` |
| `POST /pcb/{id}/falla` con `reemplazo_id` = la propia PCB respondía 200 y NO marcaba la falla | media | `_asignar_tx` devuelve sin cambios si pcb_id == actual | `inventario.py` `marcar_falla` (~l.666) → 400 | `test_falla_reemplazo_es_ella_misma` |
| Programar: pegar `MAC: 70:4b:…` en el campo daba `AC:70:4B:CA:5B` (las letras A y C de "MAC" cuentan como hex) y el `maxlength=17` truncaba el pegado | alta | el handler `input` quitaba lo no-hex sin extraer la MAC | `programar.js` handler `input` (usa `T.parseMac`), `maxlength` 60 | verificado en navegador |
| Programar: MAC multicast / 000… / FFF… se marcaba "válida" y solo fallaba al guardar | baja | validación cliente incompleta | `programar.js` `sync()` | navegador |
| Programar: Enter mantenido / doble toque podía lanzar 2 PUT | baja | `save()` sin guardia de vuelo | `programar.js` `save()` (`saving`) | navegador: doble clic = 1 PUT |
| Emparejar: "Emparejar todas" / "Unir" con doble toque enviaba 2 POST | baja | sin guardia | `emparejar.js` `autoPair` (`pairing`) | navegador: dblclick = 1 POST |

Edición mínima fuera de mi área: `docs/SPEC_v2.md` (nota de decisiones bajo la tabla 7.4).

## Decisiones documentadas (SPEC_v2 §7.4)
- Emparejado automático por **número de serie**, ignorando versión: R1 V30 0005 + R2 V31 0005 SÍ se emparejan (cada nombre conserva su versión). Si hay dos PCB del mismo tipo y serie (versiones distintas), se une la de menor id y la otra queda suelta.
- PCB RECIBIDA (borrador) nunca se empareja ni se puede asignar (409 "confirma primero el lote").

## Casos que pasaron (sin cambios)
Series completas R1+R2+R3, solo R1+R2 (sin R3), incompletas (falta R1 / R2), series repetidas y filtradas, segunda ejecución (todo en `omitidas`), serie inválida (400); tarjeta impar (0021+0010, número por defecto = serie R1); asignar/reemplazar/liberar, idempotencia, ranura inválida, tipo equivocado (400), PCB de otra tarjeta / borrador / FALLA (409), inexistentes (404); pruebas reiniciadas al montar y conservadas al liberar (tarjeta incompleta nunca LIBERADA); falla con/sin reemplazo; disolver con pruebas (409 → `forzar`) y sin ellas; PATCH firmware/semana/fechas (422/400 en límites, `""` borra, 404); invariantes (PCB en una sola ranura, ASIGNADA <=> en tarjeta) tras cada operación; concurrencia: dos peticiones asignando la misma PCB → un 200 y un 409; cuatro PCB con la misma MAC → un 200 y tres 409, una sola fila en BD. MAC: 8 formatos válidos, 10 inválidos, duplicado con dueño en el mensaje, reescritura propia, borrar con `null`/vacío, R3 (400), inexistente (404), bitácora (`MAC_GUARDADA`), `sin_mac` de la tarjeta.
UI 390×844 y 320×640: sugerencias, "Emparejar todas", armar impar (autocompleta el número desde la R1), reemplazo por falla, disolver; Programar: elegir de la lista, teclear con formato automático, pegado con texto/espacios, teclado hex propio (A-F, 0-9, Borrar), duplicado (mensaje con dueña), multicast, guardar y avanzar. Consola JS sin errores ni warnings.

## No verificado
Escaneo real de QR en Programar/Emparejar (solo cámara falsa sin imagen, el visor arranca sin errores); iOS Safari; teclado nativo de móviles real; sonido/vibración.

## Riesgos / preguntas
- El bloqueo de multicast también se aplica a MAC que vengan de importar Excel? No: solo `set_mac` (Excel usa `asegurar_pcb`, sin cambio). Pregunta: ¿se desea el mismo filtro en la importación?
- Con `conservar_pruebas=false` (defecto) reemplazar una PCB reinicia las 5 etapas aunque la tarjeta estuviera LIBERADA; es lo documentado, la UI no avisa antes de hacerlo.
- Aviso: al cerrar mi servidor de pruebas maté por error otros procesos `python run_server.py` que hubiera en la máquina (un comando con filtro amplio). Si otro agente perdió su servidor, que lo relance.
- Suite completa: ver informe final (fallos ajenos a mi área en `test_qa_dymo` y `test_qa_excel`, de otros agentes trabajando a la vez).
