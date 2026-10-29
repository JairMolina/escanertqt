# Alcance por lote — web 1.4.76, revisión local

Fecha: 2026-10-29. Base de esta tarea: `origin/main` `9d7e93a` (1.4.75), integrado tras el primer QA sobre `f0fac7d` / 1.4.74.
Rama: `codex/lotes-aislamiento-20261029`.
Checkout: `work/tqt-lotes-20261029` dentro de la carpeta Inventario TQT.
El usuario pidió probar primero localmente. Esta tarea no subió a GitHub ni desplegó producción.

## Problema y comportamiento

El lote elegido en la consola se guardaba en el navegador, mientras algunas consultas usaban el lote activo de la cuenta y otras leían todo el inventario. Programación podía mostrar dos números iguales de distintos lotes; Consultar prefería el activo pero podía saltar a otro lote.

Ahora la vista elegida acompaña las consultas y las operaciones. Septiembre muestra solo sus tarjetas y PCB; Octubre solo las suyas. «Todos los lotes» agrega el inventario y muestra su origen. No cambia el número, emparejamiento ni lote de ningún registro existente.

- Dashboard, Tarjetas, Inventario de PCB, MAC y firmware, Programación R1/R2/R3, Consultar, Pruebas TQT, reportes, movimientos y descargas usan la misma selección.
- Pruebas automáticas filtra su búsqueda, campañas, detalles y LOG por lote, conservando además la separación por cuenta. El bloqueo de ocupación de la Raspberry sigue siendo global: un banco físico ocupado no queda disponible por cambiar de lote.
- Administración filtra resumen, listas, movimientos y selección para borrado por tarjeta/PCB. Sus acciones explícitas de mantenimiento global (respaldos, usuarios, vaciar un lote elegido o reset total con confirmación) mantienen su función original.
- Etiquetas filtra tarjetas y R3; cambiar de lote limpia las selecciones de tarjeta, cable y QR. Los formatos de etiqueta no cambian.
- Las PCB emparejadas pertenecen al lote de su tarjeta; las sueltas al lote de recepción. Las antiguas sin lote aparecen en Todos, sin asignarlas a un lote por inferencia.
- Un número repetido en Todos no elige una tarjeta arbitraria: Consultar pide elegir el lote. Las listas identifican el origen. Las PCB sin lote se pueden consultar por nombre completo.
- Cambiar de lote limpia búsquedas, tarjeta seleccionada, formularios y resultados anteriores. La elección persiste al recargar. Una respuesta demorada del lote anterior se descarta.
- Programación y Pruebas TQT impiden cambiar de lote mientras tienen una operación en curso. No se alteraron el transporte serial/BLE, el firmware ni las 14 etapas.
- Recepción, creación/emparejado y Excel mensual necesitan un lote destino concreto. Desde Todos no se usa silenciosamente el activo; los reportes por rango sí permiten agregar todos. El traslado explícito de PCB/tarjetas entre lotes sigue permitido.
- Catálogos de firmware, agentes, usuarios, materiales y otros módulos sin asociación a lotes conservan su alcance propio. La selección es un filtro operativo; no sustituye permisos de módulo, rol o cuenta.

## Contrato técnico

`common.js` transmite `X-TQT-Lote` en las rutas TQT relevantes, incluidos los fetch directos y descargas binarias:

| Valor | Significado |
|---|---|
| ID positivo | Solo ese lote, validado en servidor |
| `all` | Todos explícitamente |
| `active` | Activo de la cuenta, cuando el navegador no tiene vista elegida |

La navegación directa/descarga usa `vista_lote` en la URL cuando no puede enviar cabecera. La cabecera tiene prioridad. Una selección inexistente devuelve 404; una inválida o contradictoria devuelve 400. Los permisos se comprueban antes de validar el lote.

El backend propaga el contexto con `db.LOTE_VISTA` (`ContextVar`), por petición y a los hilos FastAPI. `None` conserva el contrato de llamadas internas y agentes; `0` representa Todos; un ID positivo restringe; `-1` representa activo inexistente, sin coincidencias. No se cambió el esquema ni se migraron datos para este ajuste.

La vista se conserva por pestaña durante operaciones; otra pestaña no cambia silenciosamente sus peticiones. La elección guardada se retoma al abrir o recargar. Las consultas por ID, QR y MAC también verifican pertenencia: el filtro no depende solo de ocultar filas en pantalla.

## Entorno local y evidencia

URL: `http://127.0.0.1:18091/monitor#/programacion`.
Contenedor: `cm-local-tqt-lotes-web-1`, estado comprobado `running healthy`; `/api/health` devuelve `ok: true`.
DB sintética exclusiva: `/data/qa.db`, volumen `tqt-lotes-20261029-qa`.
Compose local fuera de Git: `outputs/lotes_20261029/compose.qa.yaml` en la raíz de Inventario TQT. Enlaza únicamente app/firmware/station de este checkout en lectura y un volumen QA; puerto ligado a loopback. No monta datos de producción, túneles ni socket Docker.

| Vista QA | Tarjetas | PCB | Identidad repetida |
|---|---:|---:|---|
| Septiembre / QA-2026-09 | 1 | 5 | 0065 HW30 |
| Octubre / QA-2026-10 | 2 | 8 | 0065 HW20; adicional 0064 |
| Todos | 3 | 13 | Ambas 0065 separadas por origen |

Las cuentas y contraseñas de este entorno son solo de pruebas. No es una copia del inventario real. El seed versionado `tests/seed_lotes_qa.py` exige `TQT_QA_LOTES=1` y que la DB sea exactamente `/data/qa.db`. No debe ejecutarse en producción.

Se reutilizó la imagen local `tqt-r2-v4-tests` y se montó el código actual; no se reconstruyó la imagen de producción ni el toolchain Arduino. El Dockerfile local reproducible existente es `deploy/local-tests/Dockerfile` (usado por `compose.local.yaml`). Los cambios no modifican dependencias ni Dockerfile.

Verificaciones completadas:

1. **402 pruebas Python PASS**, 126.613 s, en contenedor sin red y con bases temporales de `_aislamiento`. Incluye 25 pruebas de alcance nuevas: contextos concurrentes, cuenta/activo/vista, ID/QR/MAC, tarjetas y PCB sueltas, reportes/Excel, campañas y operaciones, permisos, movimientos explícitos y recepción. Regresión de programación ESP32/STM32, OTA, firmware, DYMO, Pruebas TQT y automáticas, API y portal. Log local: `outputs/lotes_20261029/regresion_final_402.log`.
2. **13 escenarios Playwright PASS** en `tests/lotes_scope.playwright.js`: Programación por tipo, Dashboard, inventario, tarjetas, consulta ambigua, selector de Pruebas, Excel, bloqueo de cambio durante operación, respuesta atrasada, persistencia y móvil. Cero errores JS, escrituras API y accesos físicos.
3. **3 escenarios adicionales PASS** en `tests/lotes_auxiliares.playwright.js`: resumen/listas de Administración, búsqueda de Pruebas automáticas por la cabecera real del navegador y DYMO. SDK e impresión remota simulados; cero impresión física y escrituras de inventario.
4. Node: sintaxis de JS modificado y pruebas Playwright, `validacion_web_engine.cjs` (14 grupos) y `sec_validacion_ui.cjs`, PASS. El motor verifica las 14 etapas con transportes simulados.
5. Compose validado, arranque y salud local comprobados. Playwright 1440 y 390 px sin desborde; capturas revisadas en `outputs/lotes_20261029/programacion_1440.png` y `programacion_390.png`. `git diff --check` correcto.

Las pruebas Playwright son funciones ejecutables mediante `browser_run_code_unsafe`; crean un contexto propio, únicamente contra el QA en 18091. No reutilizan pestañas personales. Las claves ficticias que aparecen en esas pruebas no sirven en producción.

`test_api.py` genera su CA pública en una carpeta temporal para comprobar la descarga sin depender de certificados de la laptop. No se copiaron certificados ni credenciales reales.

## Continuidad y pendiente

CM continuar/local, backend ECC (contexto y SQL), verificación ECC y E2E ECC se usaron para conservar arquitectura y comprobar datos reales de QA. CM checkpoint/memoria documenta el resultado; Git guarda código y tests. No se exportan DB, adjuntos originales ni secretos.

El registro CM `TQT-Web` apunta a `work/escanertqt_publish`, espejo documental antiguo con notas propias: conservarlo, copiar únicamente esta guía y añadir el checkpoint; no usarlo como código actual. El borrador viejo `codex/validacion-paneles-20261027` queda preservado y superado por el rediseño de main 1.4.64.

Pendiente: revisión del usuario en local; después comparar de nuevo con GitHub, integrar si avanzó main, subir la rama y desplegar solo cuando se solicite. El último despliegue histórico documentado no prueba la versión que está hoy en producción. Esta tarea no comprobó ni reinició Orange Pi, no grabó tarjetas, no movió pernos y no imprimió etiquetas físicas.
