# Encargo de implementación: Validación TQT, conexiones web y OTA

Fecha: 2026-10-15. Estado: **especificación para el compañero; todavía no implementada**.

## Objetivo y alcance

Mejorar https://inventariotqt.site/monitor#/validacion para producción, trasladar la rutina automática de 14 pruebas al navegador, unificar la comunicación serial de la web con la experiencia directa de R2 y corregir la lentitud OTA al ocultar la pestaña. Mantener el inventario, evidencias, reportes y formatos de etiquetas existentes.

Este encargo es de la web TQT. La futura app Android **TQT** tiene su especificación independiente en `docs/APP_TQT_ANDROID.md`; no comenzar a desarrollarla como parte de este trabajo.

Antes de implementar: leer AGENTS.md, docs/CODEX_ESTADO.md y memoria; consultar Git, comparar con el código desplegado y conservar cambios locales. Referencia inspeccionada al redactar: rama `codex/r2-integracion-1387`, commit `5a5e89b16bb3` (web 1.3.92). Se incorporaron por fast-forward los cambios remotos de DYMO 1.3.90–1.3.92. Ese número es referencia Git, no una certificación del despliegue actual.

No modificar producción, grabar firmware ni mover hardware durante la elaboración del plan. Implementar y probar aislado; obtener autorización específica antes de desplegar y confirmar el banco antes de pruebas físicas. Escritura de eFuses desautorizada.

## A. Diagnóstico actual y archivos de partida

- Validación: `app/static/js/sec_validacion.js`, `app/static/css/sec_validacion.css`.
- Contrato de 14 etapas/estados: `app/static/js/test_station_contract.json`.
- API y persistencia: `app/routers/test_station.py`, `app/services/test_station.py`, y reglas relacionadas en `app/routers/validacion.py`.
- Motor actual Python: `station/test_station/tqtstation/engine.py`.
- Protocolos originales: `station/test_station/tqtstation/protocol.py`, `serial_port.py`, `ble.py`, `reporting.py`.
- Programación serial/monitor R2: `app/static/js/sec_programacion.js`.
- Programación STM32 R1/R3: `app/static/js/stm32_programacion.js`.
- OTA: `app/static/js/esp32_ota.js`, `app/services/esp32_ota.py`.
- DYMO: `app/static/js/dymo.js`, `dymo_connect.js`, `app/services/dymo_service.py`, `app/routers/excel_dymo.py`.
- Pruebas existentes: `tests/test_test_station.py`, `tests/test_validacion_comparar.py`, `tests/test_validacion_ble.py`, `station/test_station/tests/`, `tests/test_dymo*.py`, `tests/esp32_ota_transport.cjs`.

Hoy Validación depende de estación/agente Windows y ejecuta el motor Python fuera del navegador. Cambiar únicamente el selector de COM no elimina esa dependencia: se necesita transportar el motor, el parser, sus temporizaciones y las reglas de evidencia a un ejecutor web y adaptar el backend sin perder garantías ni historial.

Los botones `ON BLE` y `OFF BLE` ya aparecen en el código inspeccionado de Validación. Investigar por qué no se muestran/habilitan o no funcionan en la versión que usa el operador; no añadir controles duplicados.

El transporte Web Serial de R2 es una referencia de interacción, permisos y ciclo de vida. No copiar a R1 los baudios, comandos ni lógica de flasheo del ESP32: la rutina R1 actual indica 57600 baudios y ACK 180 ms; verificar los parámetros exactos en las fuentes. Web Serial debe conservar el protocolo real del banco.

## B. Requisitos de Validación, punto por punto

### 1. Banco de pruebas fijo, sin selector ni confirmación repetitiva

El usuario establece que **todas estas pruebas, sin excepción, se realizan en un banco de pruebas en modo seguro**. Eliminar el selector de banco/estación del flujo normal y dejar el contexto de banco seguro seleccionado internamente. No sustituirlo por otro selector equivalente.

La UI actual incluye selección de estación y una casilla «Confirmo la tarjeta conectada y el banco libre». Revisar ambos elementos para quitar el trámite repetitivo solicitado: el botón Iniciar debe incorporar la intención del operador y registrar el contexto fijo. No exigir marcar una casilla de banco en cada ejecución.

Mostrar, si aporta claridad, una leyenda discreta «Banco de pruebas · modo seguro» sin interacción adicional. No presentar esa leyenda como detección física o interbloqueo electrónico que el sistema no tiene. Mantener conexión válida, exclusión de operaciones, cancelación y comprobaciones físicas/identidad de la rutina. No saltarse esas comprobaciones asignando simplemente `physical_confirmed=true` y dejando todo igual.

### 2. Las 14 etapas siempre visibles con indicador a la izquierda

Renderizar las 14 filas desde el inicio, antes de ejecutar. Mantener orden, espacio del indicador y posición de las filas durante toda la prueba; no borrar/reconstruir la lista al llegar eventos ni reordenar por resultado. Cuando una etapa no se ejecute debe seguir visible con su motivo.

- Gris: pendiente.
- Verde: aprobada.
- Rojo: fallida.
- En ejecución: destacar la fila y un indicador propio, sin presentarla como aprobada (puede usarse azul/naranja).
- Cancelada/no verificada: estado y texto diferenciados; nunca verde.

Interpretación de «puntos fijos»: el indicador ocupa siempre la misma columna izquierda de cada fila y persiste al actualizar. No usar posicionamiento fijo en la ventana que desplace las filas o tape controles.

No depender solo del color: texto/iconos, aria-live apropiado y foco estable.

Etapas existentes, conservar nombres y semántica:

1. Restablecer e identificar R1.
2. Verificar estado inicial del motor.
3. R1 serial · Primer movimiento.
4. R1 serial · Repetición sin movimiento.
5. R1 serial · Movimiento inverso.
6. R1 serial · Repetición inversa.
7. Localizar y conectar R1 BLE.
8. R1 BLE · Primer movimiento.
9. R1 BLE · Repetición sin movimiento.
10. R1 BLE · Movimiento inverso.
11. R1 BLE · Repetición inversa.
12. Desconectar R1 y conectar R2 BLE automáticamente.
13. R2 BLE · Primer movimiento.
14. R2 BLE · Movimiento inverso.

### 3. Resultado destacado arriba

Colocar el resumen de la ejecución actual por encima de las etapas. Mostrar resultado textual, indicador de color y conteo aprobado/total. Verde «Aprobada · 14/14» únicamente con 14 etapas aprobadas y cotejo/evidencias válidos según las reglas actuales del servidor.

Incluir número/nombre exacto de tarjeta, R1/R2 y sus MAC pertinentes claramente identificadas, fecha/hora, duración, HW/FW y resumen de comandos/interfaz utilizados. No mezclar MAC declarada, MAC observada e identificador opaco del navegador. Si falta un dato, mostrar pendiente/no disponible, no rellenar con el inventario como si fuera lectura física.

Interpretar «nombre, MAC y comandos» como datos y trazabilidad visibles, con acceso al registro completo de comandos y respuestas. Mantener además controles manuales en su lugar correspondiente.

Distinguir ejecución fallida, cancelada, incompleta, no verificada y aprobada con advertencias. Conservar la distinción actual entre prueba aprobada y liberación/autorización: no cambiar `release_authorized` automáticamente por imprimir.

### 4. Tarjeta e inventario: selección e historial a la derecha

Mostrar listado de tarjetas seleccionables con búsqueda por número, nombre y QR; conservar ceros iniciales. Paginación/carga controlada, estado vacío y filtros sin descargar el inventario completo innecesariamente.

Al seleccionar una tarjeta actualizar su detalle y el historial del lado derecho, sin navegar a otra página. Historial con fecha/hora, resultado, ejecución, operador, duración y acceso a reporte/log. Orden más reciente primero; dos pruebas de una misma tarjeta son dos registros independientes.

En móvil apilar de forma coherente. Cancelar/ignorar respuestas de una selección anterior para no mezclar historial al cambiar rápido de tarjeta. Distinguir historial de la tarjeta seleccionada de la ejecución activa.

### 5. Serial directo desde navegador, sin agente de pruebas

Usar Web Serial con la experiencia de Programación > TQT R2: elegir puerto nativo del navegador, reutilizar puertos autorizados, conectar/desconectar, monitor y estado visible. HTTPS/localhost y navegador compatible. No listar todos los COM del sistema como si Web Serial los expusiera sin permiso.

Crear/reutilizar una capa compartida de transporte serial con un único propietario por puerto, lectura incremental de frames fragmentados, cola de escritura, liberación de locks, cancelación y limpieza al desmontar vistas. Separar monitor, flasheo y pruebas para evitar dobles lectores y conflictos de puerto.

Portar el motor de 14 etapas y parser de S29 a JS, apoyándose en los originales y fixtures. Preservar ACK, delimitadores, reintentos, timeouts, lecturas frescas, verificación de MOV y ventanas de repetición sin movimiento. No acelerar eliminando observaciones que demuestran que un comando repetido no provocó otro movimiento.

Persistir ejecución, eventos y reporte en el backend como hoy, mediante endpoints para el cliente web autenticado; no entregar al navegador el token privado de agente ni simular una estación privilegiada. Conservar compatibilidad con reportes anteriores y separar origen `browser`/`agent` cuando proceda. El backend debe validar la estructura/evidencia y autorizar por operador; no aceptar un booleano `passed` sin comprobaciones.

Retirar instalación y despliegue de agente del flujo de pruebas cuando la nueva ruta esté completa y verificada. No borrar abruptamente los adaptadores de compatibilidad necesarios para otras funciones.

### 6. HW/FW y semáforo de vigencia

Mostrar por cada PCB relevante HW, FW registrado, FW leído si existe y última versión compatible publicada/autorizada. Usar el catálogo correcto de R1, R2 y R3; no comparar todas contra FW4.2 de R2 ni contra una cadena fija.

- Verde: programada con la versión más reciente compatible.
- Naranja: programada con versión anterior; indicar versión objetivo.
- Rojo: no programada según el registro disponible.
- Desconocido/no verificable: estado neutro explícito si no hay evidencia suficiente o falla el catálogo.

Comparar versiones numéricamente (4.10 > 4.9). Conservar semántica de catálogo y compatibilidad HW. No confundir «FW vigente» con «pruebas aprobadas» ni con «conectada». Un registro borrado no impide comprobar la capacidad física real y no debe bloquear por sí solo una operación válida.

### 7 y 8. Un botón imprime aprobación y cable sin cambiar de sección

Tras aprobar la ejecución actual habilitar **Imprimir etiquetas**. Un clic debe solicitar:

1. Una etiqueta de la tarjeta actual con el formato y datos de la etiqueta vigente, agregando debajo de los datos la leyenda exacta **Aprobada**.
2. Una copia de la etiqueta **Etiquetas cable** con el número correspondiente a la tarjeta actual.

No navegar a `/dymo`, no abrir otra pestaña ni exigir volver a elegir tarjeta o capturar datos. Usar la identidad confirmada de la ejecución y la última información válida. Mantener QR, MAC, nombres, tamaños, orientación y contenido existentes; añadir la leyenda dentro del área imprimible sin recortes. Si no cabe, presentar una adaptación mínima medida, no reducir todo arbitrariamente ni rediseñar las etiquetas globales.

Reutilizar los generadores actuales y extraer el servicio de impresión necesario para que Validación pueda invocarlo. No copiar plantillas desactualizadas. La referencia 1.3.92 de cable incluye TQT arriba, número vertical, línea punteada y una opción separada R1/R2 `0000/0000`: conservar el comportamiento vigente. Para este botón el pedido es una copia con el número de la tarjeta actual; no activar el modo de pareja R1/R2 sin necesidad ni imprimir etiquetas adicionales.

Impresión directa: seleccionar/configurar impresora una vez desde la propia sección si hace falta; usar DYMO Connect y driver cuando estén disponibles. Mostrar indicador «Imprimiendo 1/2…», «Enviada 2/2…» y error/reintento por etiqueta. Evitar doble clic. Si falla la segunda no repetir automáticamente la primera. Un SDK que solo confirma envío a cola no demuestra salida física: distinguir enviados de impresos confirmados. Reimpresión intencional sí permitida y trazable.

Límite importante: la versión actual tiene fallback por diálogo de impresión del navegador. Ese fallback no puede garantizar impresión silenciosa. Para cumplir el único clic sin diálogo se necesita el mecanismo directo compatible de DYMO, que puede requerir su runtime local; no confundir ese requisito del fabricante con el agente TQT que se busca eliminar. Si falta DYMO, informar en la misma vista y ofrecer configuración; no abrir `window.print()` automáticamente ni fingir éxito. Documentar esta condición para el compañero y el operador.

Aprobación: habilitar por defecto solo con resultado final `aprobado`, 14/14 y cotejo válido. Mantener separada `aprobado_con_advertencias`: no imprimir Aprobada automáticamente hasta definir explícitamente su política; no debilitar el criterio existente. El botón aparece para la ejecución elegible, no para cualquier tarjeta que tenga un aprobado histórico anterior a un fallo posterior.

### 9. Últimos valores ON y OFF por etapa

Mostrar ON/OFF en vivo y guardar en cada una de las 14 etapas el último par observado con su timestamp/edad, evidencia fuente y valores previos/finales cuando proceda. No arrastrar valores de otra ejecución como si fueran nuevos; si no llegó una muestra válida, mostrar «sin dato nuevo».

Semántica real del contrato:

- `ON`: sensor de CIERRE; 1 = perno afuera/bloqueado activo.
- `OFF`: sensor de APERTURA; 1 = perno adentro/desbloqueado activo.
- No son los comandos PPON y POFF.

Conservar valores crudos 0/1 y su explicación. Si ambos indican conflicto, reflejarlo sin inferir una posición aprobada. No cambiar expectativas de movimiento basándose en nombres intuitivos de los campos.

### 10. ON/OFF manuales por BLE

Exponer claramente ON BLE y OFF BLE para el dispositivo conectado, indicando si es R1 o R2. Reutilizar comandos exactos PPON/POFF y terminadores del protocolo actual, no comandos del servicio OTA. Mostrar envío, respuesta/evidencia y error.

Revisar controles ya presentes antes de duplicar. Deshabilitar cuando desconectado, durante conexión o mientras una prueba automática posee el transporte. Los comandos manuales no deben contaminar las evidencias o el estado de una rutina en curso ni contabilizarse como etapas aprobadas.

### 11. Indicadores serial y Bluetooth

Círculo pequeño y texto junto a cada conexión:

- Rojo: desconectado.
- Naranja: conectando/reconectando.
- Verde: conectado realmente.

Indicar dispositivo y motivo del error cuando corresponda. Actualizar por eventos reales de Web Serial/Web Bluetooth, al desconectar cable, fallar GATT o cambiar vista; no dejar verde por tener un dispositivo guardado. Conservar etiqueta textual accesible. Separar conexión de identidad verificada y de salud/comunicación.

### 12. Tarjeta seleccionada distinta de la detectada: confirmar y continuar automáticamente

Ejemplo: seleccionada 0042, físicamente conectada 0044. No finalizar como error ni obligar a pulsar otra vez Iniciar. Pausar en una fase de identificación y mostrar:

> Seleccionaste la tarjeta 0042, pero está conectada la 0044. ¿Deseas continuar con la tarjeta 0044?

Acciones: **Continuar con 0044** y **Cancelar**.

Al confirmar, resolver la identidad contra el inventario, cargar el conjunto/pareja correcto y cambiar atómicamente selección, detalle, historial, evidencias esperadas, ejecución e impresión a 0044. Continuar la misma intención de prueba automáticamente. Conservar trazabilidad de la selección inicial 0042, detectada 0044, operador y consentimiento; nunca guardar el resultado de 0044 bajo 0042.

No asociar por coincidencia parcial de número. Si no existe, hay ambigüedad o los identificadores/MAC/pareja son contradictorios, explicar el problema y no inventar el registro ni saltarse el cotejo.

Identificar antes de Reset_44 o movimientos siempre que el protocolo permita obtener identidad sin efectos. Si la secuencia original necesita reset para revelar identidad, documentar el punto exacto y evitar movimientos posteriores hasta confirmar. No repetir Reset_44/movimientos por un error de flujo de UI. El backend actual liga el resultado al inventario solicitado: debe adaptarse también; un cambio solo visual no resuelve este requisito. Invalidar evidencias previas a la resolución que no correspondan al nuevo contexto.

### 13. Integración Skytec: pendiente, sin ejecutar

Destino futuro: https://skytec.skyguardian.mx/.

Cuando una revisión se confirme/apruebe, se desea enviar su resultado a ese sistema. **No implementar envío ni iniciar sesión todavía.** Faltan usuario, contraseña, permisos, endpoints y pasos del proceso.

Documentar backlog y datos candidatos (identidad, resultado, fecha, operador, FW/HW, evidencia) sin inventar contrato. Mantener el reporte local/web como fuente de esta ejecución y separar aprobación de TQT de exportación a Skytec. No crear falsos estados «enviado», no guardar credenciales en Git y no introducir llamadas al dominio. La integración se habilitará con instrucciones y autorización posteriores.

## C. Programación y unificación de toda comunicación serial

En https://inventariotqt.site/monitor#/programacion reutilizar en TQT R1 y TQT R3 la plantilla visual de estado/progreso que tiene R2: indicadores coherentes, fase, resultado, FW/HW, conexión y error/cancelación. Compartir componentes en lugar de duplicar plantillas. No mostrar un puerto serial ficticio como conexión de J-Link.

Inventariar todos los puntos de comunicación serial reales de la web, incluido monitor, lectura de identidad/MAC, pruebas, instalación ESP32 R2 y ESP32 asociado a R1. Crear una matriz ruta/archivo, hardware, protocolo, transporte actual, agente y reemplazo viable. Excluir librerías vendor de cambios masivos.

Donde exista USB–UART/COM, migrar a la capa Web Serial compartida y a la experiencia R2, sin instalar agentes TQT. Mantener baudios específicos y permisos nativos del navegador; no obligar a reautorizar un puerto ya concedido sin razón.

**Límite técnico que no debe ocultarse:** la grabación STM32 de R1/R3 usa J-Link por SWD y ejecutable nativo. Web Serial no sustituye automáticamente a J-Link. No eliminar el puente de programación STM32 ni prometer funcionamiento sin agente para SWD por reutilizar la UI de R2. Separar serial directo de grabación SWD; investigar una alternativa real si se exige eliminar también ese puente, proponerla con compatibilidad/driver/firmware, y no implementarla como cambio silencioso de este encargo.

Asimismo, Web Bluetooth no expone la MAC física arbitraria de Windows ni permite escanear/conectar cualquier dispositivo sin autorización. Los pasos 7/12 deben reutilizar dispositivos previamente autorizados cuando sea viable. Preparar permisos R1/R2 con gestos del usuario antes de la rutina o pausar para el selector nativo cuando haga falta, conservando la ejecución; no prometer una selección automática prohibida por el navegador. Obtener/cotejar identidad desde respuestas reales compatibles, nunca usar `device.id` como si fuera MAC. La falta de evidencia MAC debe permanecer no verificada, no aprobarse por asumir el valor del inventario.

## D. Ajuste OTA rápido ya confirmado por el usuario

Problema físico confirmado: al mantener la pestaña visible, OTA R2 terminó aproximadamente en2 min; al cambiar/minimizar Chrome se extendía mucho. Se comprobó que web principal 1.3.89 y local servían el mismo JS, con paquetes negociados500 B. No confundir con latencia del servidor: durante el envío el firmware ya está en el navegador y viaja a la R2 por BLE.

Archivo: `app/static/js/esp32_ota.js`. `waitState()` recibe notificaciones rápidas, pero consulta `chars.latest` con un bucle `await sleep(chars.fast ? 5 : 30)`. El navegador limita temporizadores en segundo plano.

Implementar en modo rápido espera por eventos/notificaciones BLE:

1. Aprovechar `chars.onStatus` y una suscripción de notificaciones por conexión.
2. Resolver esperas pendientes al recibir estado/offset aceptable; comprobar también `chars.latest` al empezar para cubrir una notificación ya recibida.
3. No depender de sleep(5 ms)/setInterval/lecturas GATT periódicas para avanzar en modo rápido. Mantener timeout solo como límite por ausencia de confirmación.
4. Conservar fallback para firmware antiguo sin notify, `writeValueWithoutResponse`, `info.chunk`, confirmación cada 8 paquetes y comprobación de offset/estado. No aumentar colas ni enviar sin control de flujo.
5. Limpiar suscriptores, cancelación y temporizadores al completar, fallar, desconectar o vencer timeout. Evitar que una espera anterior afecte a la siguiente OTA.
6. Preservar criptografía, identidad, manifiesto, hashes, verificación de reinicio y recuperación de OTA pendiente.
7. No prometer plena velocidad si Chrome/Windows suspenden totalmente la página. Dar indicaciones claras sin afirmar soporte de segundo plano ilimitado.

Actualizar `tests/esp32_ota_transport.cjs`: notificación antes/después de esperar; cancelación; desconexión; error; timeout; colas y limpieza; flujo rápido sin sondeo; compatibilidad antigua y transición de nombres. Actualizar versión y caché del JS al publicar.

## E. Diseño del ejecutor web y evidencia

Usar una máquina de estados explícita de sesión y otra por etapa. Separar transporte serial/BLE, parser, reglas de prueba, persistencia y presentación. No aprobar un comando solamente por haberlo enviado o recibido ACK: exigir evidencia S29 fresca como el motor actual.

Conservar validación de MOV, PB, ON/OFF, errores, salud serial, ventana de comandos repetidos y calidad de comunicación. Guardar trazas que permitan comparar ejecución browser con fixtures y motor original. Registrar desconexión, timeout y cancelación como resultados distintos de aprobado.

Mantener bloqueo de pruebas/flash/manual para los recursos físicos de la sesión. Dos pestañas pueden competir: coordinar dentro del mismo origen cuando sea posible y manejar el fallo de apertura; no afirmar que el backend puede bloquear procesos externos que usan el COM. Al cambiar de sección, no perder silenciosamente una prueba ni dejar lectores/locks abiertos.

El servidor valida datos y reglas pero no es un observador directo del hardware del navegador. Documentar ese límite de confianza; no presentar como atestación criptográfica independiente un reporte construido enteramente por JS. Reutilizar los mecanismos autenticados disponibles donde existan.

Durante la migración mantener reportes JSON/HTML/log e historial anterior consultables. Nuevo esquema con migraciones compatibles, idempotencia de eventos/resultado e identificador único de ejecución. No reutilizar la fila de un ensayo para el siguiente.

## F. Verificación y aceptación

No iniciar pruebas físicas por estar presentes estas instrucciones: pedir tarjeta, puertos y banco libre cuando el desarrollo esté listo. Primero pruebas con mocks/fixtures y entorno Docker aislado.

Mínimos:

- Las14 filas aparecen antes de empezar y conservan posición/estados al llegar eventos.
- Colores, textos, resultado superior e historial corresponden a la misma ejecución/tarjeta.
- Lectura serial fragmentada/retransmisiones/ACK y S29 viejo no generan falsos aprobados.
- Dos ejecuciones de la misma tarjeta quedan independientes y fechadas.
- Desconexión COM/BLE cambia el semáforo y termina/pausa coherentemente, sin dejar verde.
- ON/OFF manuales funcionan en R1/R2 y no interfieren con automático.
- Campos ON/OFF por etapa tienen muestra y edad correctas; distinguir sensor de comando.
- Cambio0042→0044 confirmado continúa sin otro clic Iniciar y guarda todo bajo0044; cancelar no ejecuta movimientos adicionales. Probar identidad desconocida/ambigua y respuesta tardía.
- FW verde/naranja/rojo y desconocido usan el catálogo correcto y compatibilidad HW.
- Un clic genera exactamente2 etiquetas: aprobación y cable de la tarjeta validada; navegación permanece en Validación. Probar doble clic, impresora ausente, fallo parcial, reimpresión y datos obsoletos.
- Comparar visualmente contra plantillas actuales 1.3.92 y verificar etiqueta real, dimensiones y recortes.
- Pruebas no requieren instalar agente TQT con navegador compatible; documentar selectores nativos inevitables y límite J-Link/DYMO.
- OTA con notificaciones avanza sin sondeo; medir visible/oculta en misma tarjeta/laptop.
- Regresión R1/R2/R3, DYMO existente, búsqueda/QR, reportes y permisos.
- Skytec permanece pendiente, sin comunicaciones salientes implementadas.

Usar pruebas del backend y del motor original, fixtures seriales/BLE, pruebas JS del nuevo motor/transporte y Playwright para escritorio/móvil y navegación/impresión simulada. Las pruebas con mocks no sustituyen la aceptación física de movimientos y salida de impresora. No inventar evidencia, tiempos o compatibilidad. No omitir ventanas de seguridad para aparentar velocidad.

## G. Secuencia y entrega al compañero

1. Recuperar Git/memoria, inspeccionar despliegue y elaborar mapa de serial/agentes, contratos y dependencias.
2. Proponer componente de conexión compartido y adaptación mínima de persistencia; dejar explícitos límites del navegador, J-Link, MAC y DYMO.
3. Implementar motor web equivalente y pruebas antes de retirar el agente de la ruta normal.
4. Incorporar UI14 etapas/resultado/sensores/historial/cambio de identidad y manuales.
5. Incorporar vigencia FW y plantilla de estado común de programación.
6. Extraer impresión reutilizable, agregar Aprobada solo al flujo de aprobación y doble impresión controlada.
7. Aplicar corrección OTA por eventos y verificar regresiones.
8. Presentar demo local y evidencias; realizar validación física autorizada.
9. Commit/push con cambios seleccionados, actualizar estado/historial/memoria y preparar despliegue Docker reproducible, con backup y rollback. Desplegar solo con autorización específica y sin reiniciar trabajos activos.

La integración Skytec queda como pendiente explícito. La eliminación total del puente SWD J-Link tampoco se dará por resuelta con Web Serial; debe quedar como decisión técnica separada si se requiere.

No incluir secretos, bases productivas, respaldos o firmware personalizado con credenciales en Git. Mantener el alcance de este encargo y la identidad visual existente. Informar qué requisitos se completaron y cuáles siguen limitados o pendientes, con evidencia verificable.

