# Historial de versiones — Escáner TQT

## v1.4.3 — 2026-10-16
- Integra la versión real de producción 1.4.1 (76d71a1) con los ajustes locales 1.4.1/1.4.2 (8983d99), sin descartar ninguna corrección.
- Conserva liberación de COM tras salir de una prueba y desbloqueo de tarjetas con pestañas abandonadas de otro operador, además de Web Serial + puente BLE Windows por MAC y la distribución de Validación.
- Caché de validacion_web.js y sec_validacion.js a 1430. Producción permanece en 1.4.1; esta integración se publica en la rama de trabajo.

## v1.4.2 — 2026-10-16
- Validación mantiene Web Serial y recupera exclusivamente Bluetooth Windows/Bleak por MAC, con un puente BLE sin abrir el COM. Sustituye el cambio completo de modo de 1.4.1.
- Conexión automática R1/R2 por MAC de inventario y S29; admite nombres antiguos sin alterar firmware. Autorización por operador/estación, comandos de un solo uso y evidencia nativa autenticada.
- Prueba física TQT 0039 / COM7: 14/14 etapas aprobadas en 108,2 s, final abierto. Resultado aprobado con advertencias por 28/99 líneas seriales ilegibles excluidas de evidencia. Solo base local aislada; producción sin cambios.
- Ver docs/VALIDACION_142.md para operación, verificaciones y límites.

## v1.4.1 — 2026-10-16
- Pruebas TQT: encabezado en tres bloques, ON/OFF junto a cada conexión y selector de tarjetas con historial antes de R1/R2; selección numérica por Enter.
- Bluetooth del navegador admite alias de la misma identidad (guiones, guiones bajos y V3_0/V30), conserva permisos y rechaza ambigüedad u otra unidad.
- Opción local de Validación «Usar Windows por MAC» recupera el motor anterior pyserial/Bleak completo; requiere su agente. Conexión manual elige por MAC, no la primera tarjeta encontrada.
- ON/OFF serial directo exige S29 fresco y ambas MAC; no genera aprobaciones. Ver docs/VALIDACION_141.md para verificaciones y límites.

## v1.4.1 (producción) — 2026-10-16
- **Pruebas TQT (web):** salir de la sección con una prueba en curso ahora libera el puerto COM cuando la prueba termina (antes quedaba abierto y Programación no podía usarlo hasta recargar).
- **Pruebas TQT (web):** una prueba web abandonada (sin latido por más de 2 min) de otro operador ya no bloquea la tarjeta: al iniciar se marca interrumpida / no verificada. Caché `sec_validacion.js` a `?v=1410`.

## v1.4.0 — 2026-10-16
Pruebas TQT (`#/validacion`) pasan a correr en el navegador; el agente de Windows queda como respaldo. Pendiente de aceptación en el banco físico.
- **1. Banco fijo:** sin selector de banco ni confirmación repetida; pulsar «Iniciar» es la intención del operador. Contexto fijo «banco de pruebas · modo seguro» (en la ruta web lo fija el servidor; en la del agente el campo `banco` se envía pero el backend lo ignora).
- **2. 14 etapas fijas:** las 14 filas se ven desde el inicio con indicador a la izquierda, no se reordenan ni se borran; la que no se ejecuta queda con su motivo (cancelada / no verificada).
- **3. Resultado arriba:** Aprobada / Aprobada con advertencias / Fallida / No verificada / Cancelada, con contador x/14, MAC registradas, del firmware y observadas, duración, HW/FW e interfaz usada.
- **4. Tarjeta e historial a la derecha:** búsqueda/escaneo y el historial de la tarjeta junto a la prueba.
- **5. Serial directo:** nueva capa `serial_web.js` (`TQTSerial`: un propietario por puerto, lector incremental, cola de escritura, liberación de locks) y motor `validacion_web.js` (`TQTValWeb`) con las 14 etapas: 57600 8N1, ACK 180 ms, guardia 300 ms, barrera S29, PPON/POFF por Web Bluetooth. Reutiliza puertos/dispositivos autorizados; si falta permiso BLE pide un clic («Autorizar R1/R2 BLE»). Backend `/api/validacion/tqt/web/runs` (crear, eventos por lotes, identidad, resultado) con las mismas reglas de aprobación y cotejo que el agente; el historial existente sigue igual. En la ruta web, fuera de la prueba, el registro muestra el monitor RX del puerto.
- **6. HW/FW:** semáforo de vigencia del firmware leído contra `/api/firmware` (sin compatibilidad por HW todavía).
- **7 y 8. Imprimir etiquetas:** con la prueba Aprobada, un botón imprime la etiqueta vigente con la leyenda «Aprobada» y la etiqueta de cable con el número, sin salir de la sección (`dymo_imprimir.js`, endpoint `/api/dymo/cable/svg`). Sin DYMO Connect abre el cuadro de impresión del navegador. «Aprobada» solo aparece en este flujo.
- **9. Últimos ON/OFF por etapa**, **10. ON/OFF manuales por BLE** (R1 o R2 conectada) y **11. indicadores serial/Bluetooth** visibles en la vista.
- **12. Tarjeta distinta:** si la conectada no es la seleccionada se pide confirmar; al aceptar, la prueba continúa sin reiniciar y el resultado se guarda bajo la detectada (se registran selección, detectada y consentimiento).
- **Salir con prueba en curso:** cambiar de sección con una prueba web en curso pide confirmación (si se acepta, se cancela y queda no verificada); cerrar o recargar la pestaña también avisa.
- **C. Programación:** R1 y R3 usan la misma plantilla de estado que R2 (`prog_estado.js`). Matriz de comunicación en `docs/V140_MATRIZ_SERIAL.md`.
- **D. OTA R2:** el envío avanza por notificaciones BLE, sin bucle de espera con temporizador; aviso discreto de mantener la pestaña visible (si Chrome/Windows suspenden la página puede tardar más).
- **Limitaciones / pendiente:** en la ruta web no hay comandos seriales manuales (solo monitor RX y ON/OFF BLE). Web Bluetooth no expone la MAC BLE: el vínculo se acepta solo con evidencia S29, si no queda «no verificado». Solo Chrome/Edge de escritorio en HTTPS. Programación R2 aún no migra a `TQTSerial`; STM32 R1/R3 sigue por J-Link con el puente. La detección de cancelación de R1/R3 en la plantilla común no se probó con un trabajo real. Punto 13 (Skytec) sin ejecutar. Caché a `?v=1400`.
- **Correcciones de revisión:** «Aprobada» (`?aprobada=1` en SVG/XML/archivo) solo si la última prueba TQT de la tarjeta quedó «aprobado» (si no, 403). El puerto serial solo se reabre con Pruebas TQT montada y se libera al salir (no choca con Programación). La ruta web ya no recibe las MAC del inventario al crear la prueba (solo huellas SHA-256) y err=13/14 de R2 cuentan solo en S29 posteriores a la etapa 11; carrera de prueba activa y `serial_health` no numérico devuelven 400; interfaz «Navegador» por `origin`; aviso de mantener la pestaña visible (registra si se oculta); BLE sin listeners RX duplicados. Caché `validacion_web.js`, `sec_validacion.js`, `dymo_imprimir.js` a `?v=1401`.
- **Límite de confianza (ruta web):** el informe lo arma el navegador del operador autenticado; el servidor valida estructura, S29 crudas e inventario pero no observa el hardware, así que un cliente manipulado podría fabricar evidencia (queda `trust_note` en cada informe). Las MAC siguen visibles al operador por otras vistas del inventario.

## v1.3.94 — 2026-10-16
- **Etiquetas DYMO:** la hoja ya no muestra todo desplegado. Debajo de la conexión hay cuatro botones (Tarjetas · Escanear · R3 · Cable) y solo se ve la zona elegida; se recuerda la última en ese navegador. «Escanear» muestra cuántas etiquetas hay en la lista y, si llega un escaneo del celular, la página cambia sola a esa zona. Los avisos de impresión y la ampliación de la vista quedan fuera de las zonas (sirven para todas). Caché `dymo.js` a `?v=1394`.

## v1.3.93 — 2026-10-15
- **Etiquetas cable:** «TQT 0000» ya no va centrado en su mitad: queda en una franja de 13 mm pegada al borde izquierdo (lejos de la línea punteada), así al doblar no se recorre hacia el doblez. Vista previa igual.

## v1.3.92 — 2026-10-15
- **Etiquetas cable:** el texto queda «TQT» arriba y el número abajo (en vertical). Botón «/» para R1/R2 con número diferente: pide «Número R1» y «Número R2» y la etiqueta sale «TQT 0021/0034». La API acepta `numero=0021/0034`. Caché `dymo.js` a `?v=1392`.

## v1.3.91 — 2026-10-15
- **Etiquetas DYMO:** se quita el texto largo de ayuda; queda una línea de estado y el botón «Instalar DYMO en esta PC», que descarga `Instalar_DYMO_TQT.cmd` (instala DYMO Connect con winget, driver incluido, y abre la prueba del servicio; si no hay winget abre la página oficial). Sin DYMO Connect, «Imprimir» sigue usando el cuadro de impresión de Chrome.
- **Etiquetas cable:** la línea punteada central es un elemento propio de 0.5 mm (vista previa e impresión con Chrome) y en el XML de DYMO una imagen más ancha con trazo de 0.5 mm. Caché `dymo.js` a `?v=1391`.

## v1.3.90 — 2026-10-15
- **Etiquetas DYMO en cualquier laptop:** si la PC no tiene DYMO Connect (o Chrome no deja hablar con él), los botones de imprimir (tarjeta, lote, escaneo, R3 y cable) abren el cuadro de impresión de Chrome con las etiquetas a 57 × 32 mm, una por página y en una sola tanda; solo necesita el driver de la LabelWriter. Las tarjetas se marcan impresas al cerrar el cuadro. Con DYMO Connect se sigue imprimiendo directo.
- **Etiquetas cable:** línea punteada vertical al centro, impresa (referencia para pegar la etiqueta); también en la vista previa. Caché `dymo.js` a `?v=1390`.

## v1.3.89 — 2026-10-15
- **Etiquetas DYMO en laptops:** se quita el consejo de abrir `https://localhost:8443/dymo` (solo existe en el servidor). La ayuda detecta cuando Chrome bloquea el «Acceso a la red local» (sitio público → DYMO Connect en 127.0.0.1) y explica cómo permitirlo; los pasos de DYMO Connect y del certificado local quedan más claros y se ofrece «Descargar .label» como alternativa. Caché `dymo_connect.js`/`dymo.js` a `?v=1389`.

## v1.3.88 — 2026-10-15
- Base R2 4.0: reconoce varias compilaciones registradas para permitir cargas desde Arduino IDE sin invalidar la base fija anterior.
- Incluye grabador local repetitivo del BIN fijo, comprobación previa sin abrir puerto e instrucciones Arduino. Corrige cabeceras de versión y eFuses en las fuentes, sin cambiar la lógica ni los BIN ya probados.

## v1.3.87 — 2026-10-15
- Integra la versión desplegada 1.3.84: conserva etiquetas de cable DYMO, terminal única y optimizaciones J-Link.
- R2: base genérica 4.0 XXXX, alta firmada y cifrada, FW 4.2 con nombre exacto del inventario y OTA rápida con recuperación GATT.
- R2 0067: flujo físico verificado por web y lectura BLE independiente; eFuses desactivados.

## v1.3.84 — 2026-10-15
- **Etiquetas cable:** el número va en vertical (girado 90°, se lee de abajo hacia arriba) en la mitad izquierda; vista previa igual.

## v1.3.83 — 2026-10-15
- **Etiquetas DYMO › Etiquetas cable:** nueva sección desplegable al final (debajo de Etiquetas R3). La etiqueta rectangular se divide a la mitad en vertical y solo la mitad izquierda lleva el número (grande y centrado); la derecha se enrolla en el cable. Rango «desde/hasta» (máx. 500), copias, vista previa, impresión en DYMO y descarga `.label`. API `GET /api/dymo/cable/xml` y `/api/dymo/cable/archivo`. Caché `dymo.js` a `?v=1383`.

## v1.3.82 — 2026-10-15
- **Programación ESP32 (R2 y R1):** se quita la terminal clara duplicada; el registro de grabación, esptool y la verificación salen en la terminal negra del monitor serial, que queda abierta y como principal. Caché `sec_programacion.js/.css` a `?v=1382`.

## v1.3.81 — 2026-10-15
- **Programación:** se quita la pestaña duplicada «R1 · ESP32 · BLE serial»; el flujo ESP32 de la R1 se abre con «Programar ESP32 R1» del panel STM32. Caché de `sec_programacion.js` a `?v=1381`.
- **Agente J-Link más rápido (R1/R3):** SWD a 4 MHz con reintento automático a 1 MHz (`TQT_SWD_KHZ`), grabación y lectura en una sola conexión, y lectura de verificación solo de las páginas del HEX y la de identidad (R1 48 KB, R3 14 KB; antes 512 KB). Sondeo de trabajos cada 1 s. Requiere reinstalar el agente en cada laptop.
- **ESP32:** esptool se precarga al abrir Programación y se descarga en paralelo con el firmware.

## v1.3.80 — 2026-10-15
- R2: OTA rápida con Write Without Response, bloques de hasta 500 bytes y notificaciones de avance; ventanas de ocho paquetes respetan la cola del receptor. FW 4.1 conserva el transporte anterior.
- Catálogo: plantilla R2 4.1.1 sin datos de unidad, seleccionada como versión más reciente. Conserva firmware anteriores, cifrado, identidad, cancelación y verificación del nuevo arranque.
- Integra la base 1.3.79 de la Orange Pi sin modificar el monitor serial, el flujo R1 ni los reportes. Prueba física aislada previa: 1.135.600 bytes enviados y validados en 71,758 s; el tiempo de Chrome queda por medir.

## v1.3.79 — 2026-10-14
- **Programación R2 ESP32 · Monitor serial:** panel estilo Arduino IDE (velocidad, abrir/cerrar, limpiar, enviar texto con fin de línea, «Reiniciar placa» por RTS/DTR) para leer el arranque (`waiting for download`, `rst:`…). Se cierra solo antes de grabar o leer la MAC, muestra la salida de esptool y de la verificación, y se reabre al terminar (opcional).
- **Grabación por serial más rápida:** sincroniza a 115200 y envía los datos a la «Velocidad de grabación» elegida (921600 por defecto, como Arduino IDE; se recuerda en el navegador). Si falla a alta velocidad, pide volver a BOOT y reintenta una vez a 115200.
- **Programación R1 ESP32:** firmware fijo `ESP32_BLE_SERIAL` 1.0 precompilado en el repo (core 3.3.12), igual para todas las R1 y sin catálogo ni subida; se descarga por `/api/esp32/bin` sin arduino-cli (antes fallaba en el servidor). Se graba como Arduino IDE sin borrar NVS (0x9000–0xE000), donde vive el nombre BLE que pone el STM32. Verificación por MAC al arrancar; no cambia el FW (STM32) de la R1; registra ESP32_PROGRAMADA.
- **Pestaña «R1 · ESP32 · BLE serial»:** misma interfaz que R2 (lista de R1, búsqueda, pasos, puerto, monitor, velocidad) con el firmware fijo; «Programar ESP32 R1» del panel STM32 abre esta pestaña. Corrige que al refrescar la lista la R1 elegida se perdía y la vista volvía a R2. Caché de `sec_programacion.js/.css` a `?v=1379`.
- **Tarjetas / Resumen / ficha:** el avance de programación se ve sin esperar la R3: estado «Falta R3 · R1 y R2 programadas», filtro y KPI «R1 y R2 programadas» y paso «Programada» con nota en la ficha. «Programadas (R1+R2+R3)» conserva la regla anterior. Caché `common/sec_tarjetas/sec_resumen.js` a `?v=1379`.
- **Tarjetas › Reporte por fecha:** incluye las tarjetas con programación en el rango (MAC o firmware guardado en R1/R2/R3, por día local; `escaneos.creado_en` está en UTC) con el contador «con programación», así «Hoy» + «R1 y R2 programadas» muestra lo programado hoy.
- **Orden de producción:** el ESP32 de la R1 solo se graba si su R2 tiene MAC y el último trabajo J-Link del STM32 de esa R1 está verificado (`GET /api/esp32/r1-gate/{id}`; el botón muestra qué falta).
- **OTA Bluetooth:** al verificar la actualización se notifica `PCB_ACTUALIZADA`/`TARJETA_ACTUALIZADA`, así Tarjetas e Inventario muestran la MAC y el FW nuevos sin recargar. Prueba de regresión: R2 programada en tarjeta sin R3 y con `firmware_r2` desactualizado devuelve MAC/FW en tarjetas, detalle, búsqueda por MAC y placa.

## v1.3.76 — 2026-10-14
- **Programación R2 ESP32:** catálogo persistente BIN/HEX, perfil HW/FW interno, nombre tomado del inventario y selector de la versión numérica más reciente compatible. Verificación INFO tras el arranque; se conserva el flujo anterior de R1.
- Integra los cambios existentes de v1.3.73–1.3.75: orden R2/R1/R3, semáforo STM32, rediseño de Pruebas y estación local J-Link. R2 FW4.0 conserva relés, BLE y eFuse del original.

## v1.3.75 — 2026-10-14
- **Programación STM32 R1/R3:** «Estación Windows conectada al J-Link» muestra solo la estación local (la que reporta desde la misma red que el navegador), no todas. El servidor recuerda en memoria la IP de cada agente; «Cambiar dispositivo» solo aparece si hay más de una estación local.

## v1.3.74 — 2026-10-14
- **Pruebas TQT:** rediseño de la sección en tarjetas (Tarjeta e inventario · Conexión y dispositivo · Controles manuales · Prueba automática · Sensores S29 · Historial), dos columnas que se apilan en <900px, botones espaciados de 40px y sin desbordes de 375px a escritorio.
- **Dispositivo de esta PC:** Programación STM32 (R1/R3) y Pruebas TQT recuerdan en cada navegador su propia estación (al descargar el instalador, al elegirla o si es la única conectada) y muestran solo «Dispositivo de esta PC» con opción «Cambiar dispositivo».

## v1.3.73 — 2026-10-14
- **Programación:** botones en orden R2 · ESP32 → R1 → R3.
- **Programación STM32 R1/R3:** el detalle de la tarjeta se divide en datos + semáforo de estado (rojo «Sin programar»/«Error al programar», amarillo «Programando…», verde «Programada») que se actualiza en vivo y relee el estado real de la placa.
- **Pruebas TQT:** los recuadros de sensores S29 ya no desbordan su contenido (MACs y etiquetas largas se ajustan).

## v1.3.72 — 2026-10-13
- **Programación STM32 R1/R3:** subir, validar y guardar HEX en un catálogo persistente. Selector de firmware compatible con la placa; por defecto elige la versión numérica más alta, con la subida más reciente en caso de empate.
- R1 obtiene HW/FW de su perfil y conserva la personalización por inventario; R3 solicita confirmar HW/FW al registrar una imagen sin perfil. Se conservan las versiones anteriores.
- Cada trabajo guarda el firmware elegido y su hash; una subida posterior no cambia una programación pendiente. Los HEX se incluyen en los respaldos de la base de datos.

## v1.3.71 — 2026-10-13
- **Programación STM32 R1/R3:** botón «Detener y cancelar programación» cancela los trabajos pendientes de la estación y solicita detener J-Link en los activos. Se mantiene el bloqueo hasta la confirmación del agente; una cancelación no registra firmware verificado.
- Recuperación del progreso al volver a la sección, vencimiento de trabajos en espera antes de crear otro y corrección del agente al recibir una R3 sin datos de R2.
- El agente de pruebas COM/BLE ya no anuncia por sí solo que la estación J-Link está conectada. Requiere actualizar el agente STM32 para detener procesos activos desde la web.

## v1.3.70 — 2026-10-13
- **Pruebas TQT:** integración de las 14 etapas originales de Test Station 0.6.3 mediante agente Windows para COM y Bluetooth, con progreso y sensores S29 en la web.
- Cotejo de R1/R2 con el inventario, historial independiente por ejecución y reportes con JSON, LOG original completo e impresión PDF. La aprobación funcional no cambia automáticamente el estado de fabricación de la tarjeta.
- Validación local con dos ejecuciones físicas de R1 0036 / COM10, ambas 14/14 aprobadas; Docker local aislado y documentación reproducible.

## v1.3.69 — 2026-10-12
- **Administración › Resumen:** botón «Descargar copia de la base (.db)» (solo con clave de administración): copia completa y verificada hecha en caliente (`GET /api/admin/respaldo/descargar`, `sqlite3.backup` + `integrity_check`), queda registrada en Movimientos (BD_DESCARGADA). Sirve para restaurar la base en otro equipo, p. ej. el Docker local.

## v1.3.68 — 2026-10-12
- **Inventario TQTR › Stock mínimo:** «Comprar» ahora es botón: se indica cantidad y llegada estimada (por defecto hoy + tiempo de entrega, editable) y el material pasa a «Comprado · faltan N días». Al cumplirse la fecha aparece «¿Llegó el material?»: Sí registra la Entrada en el inventario (suma al disponible); No vuelve a preguntar en 7 días. El pedido se puede editar o cancelar (`inv_tqtr_pedidos`, `POST /stock-minimo/{id}/pedido`, `PATCH /pedidos/{id}`, `POST /pedidos/{id}/llegada`).
- El contador de Stock mínimo cuenta solo lo pendiente (por comprar + llegadas por confirmar); el KPI muestra cuántos van en camino.
- La hoja de Stock mínimo explica la diferencia entre stock mínimo y punto de reorden.

## v1.3.67 — 2026-10-12
- **Tarjetas:** los botones Cambiar/Quitar de cada placa ahora aparecen junto a su R1/R2/R3, arriba en el panel (antes al final).
- **Pruebas y validación (varios usuarios):** si la conexión BLE de una laptop la abrió otro usuario se muestra «En uso por <usuario>» y no se pueden mandar comandos; sin confirmar «esta laptop» tampoco se puede buscar/conectar (evita mover la placa de otro compañero).

## v1.3.66 — 2026-10-12
- **Pruebas y validación:** «esta laptop» ya no depende solo de la IP: se recuerda en el navegador al descargar el instalador o con el botón «Sí, es esta laptop»; en IPv6 basta el mismo prefijo /64. El aviso muestra la IP del navegador y la del agente para diagnosticar.
- Si la búsqueda no encuentra placas, se indica qué laptop buscó y qué revisar (placa encendida, no conectada al celular u otra app, cerca de esa laptop).

## v1.3.65 — 2026-10-12
- **Pruebas y validación › Placas validadas:** nueva sección con solo las placas escaneadas, probadas y validadas (automática o manual), su tarjeta, quién probó (usuario · ID) y el estado de la tarjeta. Se seleccionan las tarjetas y «Marcar como validadas» las cambia a «Validada» en Tarjetas (`GET /api/validacion/placas-validadas`, `POST /api/validacion/tarjetas/validar`, registro TARJETA_VALIDADA).
- «Validada» de la tarjeta ahora se confirma explícitamente; la validación automática/manual es por placa. Las pruebas ON/OFF anteriores al 12-oct-2026 siguen contando como validadas.
- El «Registro de la sesión» muestra en cada línea el usuario y su ID.

## v1.3.64 — 2026-10-12
- **Pruebas y validación:** ficha «Tarjeta escaneada»: con el Botón de escaneo el celular escanea la tarjeta y se comparan los datos de la base (nombre BLE, MAC, firmware, tarjeta y pruebas ON/OFF) contra la placa conectada por Bluetooth (`GET /api/validacion/comparar`).
- Botones «Validar automático» (solo valida si todo coincide; si no, indica qué está mal) y «Validar manual» (valida aunque haya diferencias, con motivo opcional) → `POST /api/validacion/validar` (VALIDACION_AUTO / VALIDACION_MANUAL); ambas cuentan para el estado «Validada».
- Se quitaron el «Historial de pruebas» y el campo «Tarjeta o placa» (lo sustituye el escaneo).
- El selector de laptop solo muestra la laptop en uso con el agente conectado (`GET /api/validacion/estaciones`, por IP del agente).

## v1.3.63 — 2026-10-09
- **Pruebas y validación:** se quitó el aviso «No hay ninguna laptop con el agente conectada»; si no hay laptops conectadas, el selector lo indica y aparece «Instalar agente en esta laptop» en la misma sección. El Bluetooth lo usa el agente de la laptop (el navegador no ve la radio de la PC), por eso la lista sale vacía hasta instalarlo.
- **Agente 1.3.63:** J-Link pasa a ser opcional (antes el agente y el instalador se detenían sin J-Link, así que una laptop solo para Bluetooth nunca aparecía conectada); sin J-Link solo rechaza trabajos STM32.

## v1.3.62 — 2026-10-09
- **Etiquetas DYMO: impresas que no se marcaban.** La firma de «impresa» la calculaba el navegador con datos viejos (p. ej. MAC registrada después de abrir la página o tarjeta de otro lote) y no coincidía con la etiqueta real; ahora `POST /api/dymo/impresas` la calcula con el estado actual en la base y la devuelve. El registro se espera, reintenta y avisa si falla; cada etiqueta se marca en cuanto sale y la vista se actualiza al momento; el escaneo usa la ficha fresca. Las R3 y R1/R2 sueltas se imprimen pero no quedan registradas (se avisa).
- **Programación ESP32 de R2 con firmware V3.1 (FW 3.1.2)** según la especificación «Programador Web TQT R2 Arduino CLI»: solo se sustituye la directiva `#define Nombre_Del_Ble` en una copia temporal, con nombre calculado del inventario (`TQT_R2_V30_` + 4 dígitos, sin editar el prefijo); se rechazan números inválidos y fuentes sin la directiva, duplicada o dinámica, y se aborta si cambia otra línea. Hashes SHA-256 de fuente y copia. Asistente de BOOT/RESET manual antes y después de grabar; tras el arranque se envía `MAC` y se valida que el nombre BLE reportado sea exactamente el esperado («Identidad incorrecta» si no); si la placa ya tenía otra MAC pide autorización explícita. Se registra FW 3.1.2. La versión V2.1 anterior se conserva.

## v1.3.61 — 2026-10-09
- **Pruebas y validación sin ventana emergente.** La búsqueda y conexión Bluetooth la hace el agente Windows de la laptop (bleak, como el tester v1.1) y todo se muestra dentro de la página: selector de laptop, «Buscar placas», lista con dirección Bluetooth y RSSI, Conectar/Desconectar y ON/OFF. Se quitó Web Bluetooth. Servidor: cola de trabajos `/api/validacion/ble/trabajos|estado` y rutas del agente `/api/stm32/agent/ble/claim|evento|{id}/resultado`; cada conexión, comando, notificación y desconexión se registra solo en el historial (evento BLE_ESTADO).
- **Agente 1.3.61.** Reinstalar desde Programación › «Instalar agente en esta laptop»: instala bleak y atiende Bluetooth en un hilo aparte sin afectar la programación STM32.

## v1.3.60 — 2026-10-09
- **Pruebas y validación.** Botones renombrados a «ON · Meter perno» y «OFF · Sacar perno» (por BLE se siguen enviando PPON/POFF; el historial también muestra los nombres nuevos). Se quitaron los avisos de seguridad y de la MAC BLE. Las placas ya permitidas se listan y conectan dentro de la página (`navigator.bluetooth.getDevices`); el selector del navegador solo aparece con «Buscar placa nueva».

## v1.3.59 — 2026-10-09
- **Nuevo estado «Validada» en Tarjetas.** Una tarjeta es validada cuando en «Pruebas y validación» se enviaron con éxito PPON y POFF a ella o a cualquiera de sus placas. Badge «Completa · validada», filtro «Validadas» (orden: Falta placa → Sin MAC → Programadas → Validadas → Completas) y refresco automático de la consola al registrar una prueba BLE (evento VALIDACION_BLE). La tabla `validaciones_ble` ahora se crea con el esquema principal.

## v1.3.58 — 2026-10-09
- **Nueva sección «Pruebas y validación»** (Operación, debajo de Consultar). Prueba por Bluetooth LE desde Chrome/Edge (Web Bluetooth): conecta al dispositivo «TQT…», envía PPON/POFF exactos, muestra notificaciones y un registro; se vincula a una placa/tarjeta por código, QR o escáner remoto. Cada conexión, comando y respuesta queda en la tabla `validaciones_ble` (`/api/validacion/registros`, `/resumen`) con historial, KPIs del día y aviso por WebSocket. Botón para descargar el tester Windows v1.1 (`/api/validacion/tester.zip`, en `station/ble_tester/`) cuando el navegador no tiene Bluetooth; el navegador no expone la MAC BLE.

## v1.3.57 — 2026-10-09
- **Tarjetas: «Reporte por fecha» desplegable.** Se muestra cerrado; recuerda si lo dejaste abierto y se abre solo si ya hay fechas elegidas.
- **Programación: se quitó «Descargar HEX»** en R1 y R3 (sigue «Subir HEX» para leer la versión de un firmware).

## v1.3.56 — 2026-10-09
- **Desemparejar una sola placa.** Al desemparejar UNA tarjeta, la hoja pregunta qué desemparejar: toda la tarjeta o solo su R1, R2 o R3 (la placa elegida queda suelta y las demás siguen emparejadas, conservando las pruebas). Con varias tarjetas se desemparejan completas como antes.
- **Tarjetas: diseño y revisión.** Mejoras de diseño y estilo en la lista y el detalle, y revisión de las funciones compartidas con otras secciones.

## v1.3.55 — 2026-10-09
- **Programación con tres modos:** «R1 · STM32 / J-Link», «R2 · ESP32 · USB serial» (la lista muestra solo R2; la R1 llega con «Programar ESP32 R1») y nuevo **«R3 · STM32 / J-Link»**.
- **R3 desde la app.** Firmware PCB_TQT_R3_TIMER_WH-V3.0_FW-V1.0 (STM32F103RET6) convertido del .elf a `firmware/stm32_r3/r3_fw10.hex` (+ .json con hashes). Imagen fija sin identidad; el agente graba, lee toda la imagen de vuelta, compara su huella y el UID, y al verificarse registra FW 1.0 en la R3 (queda Programada). «Subir HEX» en R3 reconoce el firmware si es idéntico al de la app.
- **Agente 1.3.55.** Las estaciones deben reinstalar el agente (botón «Instalar agente en esta laptop») para programar R3; un agente anterior rechaza el trabajo sin grabar.

## v1.3.54 — 2026-10-09
- **Programar ESP32 R1 desde el panel STM32.** Botón junto a «Programar STM32 con J-Link» que abre el flujo ESP32 (USB serial) con la misma R1 elegida: compila el firmware ESP32_BLE_SERIAL de R1, flashea y guarda la MAC de la R1. Si el STM32 aún no está programado y verificado, avisa del orden (ESP32 R2 → STM32 R1 → ESP32 R1) antes de seguir.
- **Subir HEX.** Junto a «Descargar HEX», lee un .hex de STM32 (`POST /api/stm32/hex/analizar`, sin guardarlo) y muestra MCU, HW, versión FW, tamaño e identidad, comparado con el firmware base de la app.

## v1.3.53 — 2026-10-09
- **Etiquetas DYMO: escanear R1 y R2 para imprimir.** En "Escanear para imprimir", una R1/R2 sin tarjeta con R1 + R2 ya no se rechaza: se imprime individual en la misma tira doble (QR + nombre) que las R3, de dos en dos. Las R1/R2 de una tarjeta completa siguen sacando la etiqueta de su tarjeta. `/api/dymo/r3/xml|archivo` acepta nombres R1, R2 y R3.

## v1.3.52 — 2026-10-09
- **Menú de la consola por flujo de la tarjeta.** Operación: Dashboard → Tarjetas → Programación → MAC y firmware → Consultar. Inventario de PCB e Inventario TQTR pasan a Gestión.
- **Estado Programada en Tarjetas.** Una tarjeta completa con R1/R2 (MAC + firmware) y R3 (firmware) se marca "Completa · programada"; filtro "Programadas" en Tarjetas y Administración, KPI en el Dashboard y paso Programada en la ficha de estatus.
- **R1 STM32 / J-Link con el diseño de ESP32.** Paneles, lista de selección, pasos y barra de avance con el mismo estilo (claro/oscuro y móvil).
- **Instalador del agente STM32.** Se borra la carpeta temporal con la credencial al terminar, avisa borrar el archivo descargado y se quitó una ruta de Python local del desarrollador.

## v1.3.51 — 2026-10-09
- **J-Link sin ventana de consola.** El agente inicia Commander con CREATE_NO_WINDOW en Windows y conserva la salida en su diagnóstico.
- **Avance de programación en la web.** Indicador animado y etapas reales de preparación, conexión/grabación, lectura/verificación, reinicio y reporte. El avance requiere la credencial de la estación asignada y no registra firmware ni sustituye la verificación final. Al terminar correctamente, la web indica que ya se puede desconectar la R1.

## v1.3.50 — 2026-10-09
- **Programación con un botón desde la web.** El botón identifica la R1 y confirma la unidad conectada. El trabajo registra operador y confirmación vinculada a la PCB. El agente graba y verifica sin pedir PROGRAMAR en consola; rechaza trabajos antiguos sin confirmación web.
- **Instalador único para Windows.** La web genera un archivo Instalar_TQT que contiene el agente y su configuración privada, evita extraer ZIP manualmente y crea el inicio automático en segundo plano para el usuario actual. Usa Python y J-Link/STM32CubeIDE instalados y avisa si faltan. No requiere permisos de administrador. El agente evita procesos duplicados por estación y guarda diagnóstico en agente.log.

## v1.3.49 — 2026-10-09
- **Lectura del UID con J-Link corregida.** Commander interpreta las longitudes en hexadecimal: `12` leía 18 bytes y el agente rechazaba una lectura correcta después de grabar. Ahora solicita explícitamente `0xC` (12 bytes). Reproducido y comprobado por lectura real en la R1 0031. La prueba de regresión simula el formato numérico de Commander.

## v1.3.48 — 2026-10-09
- **STM32 desde la laptop.** El agente detecta también J-Link incluido con STM32CubeIDE. La web actualiza automáticamente las estaciones y los datos de la R2 vinculada cuando cambia el inventario, y admite buscar la serie de una R1 cuyo número de tarjeta es diferente.
- **Firmware probado.** Se actualiza el HEX base desde el proyecto FW 4.3 probado por el operador el 9 de octubre. La aplicación conserva todos sus bytes; la web añade únicamente la identidad individual. La grabación desde la web sigue requiriendo la confirmación física y la lectura de verificación del agente.
- **Diagnóstico del agente.** `python agent.py --check` verifica acceso HTTPS al servidor y localiza J-Link sin abrir la sonda ni tomar trabajos.
- **Conexión al dominio público.** Las peticiones del agente se identifican como TQT-Station para evitar el rechazo HTTP 403 del cliente Python genérico.

## v1.3.47 — 2026-10-08
- **R1 STM32 / J-Link en Programación.** Selección manual o por QR remoto, carga automática de la R2 vinculada y su MAC, identidad con HW/FW/CRC y HEX individual sin recompilar por unidad. R1 y R2 pueden tener números distintos.
- **Agente Windows descargable.** Conexión saliente autenticada, confirmación de la PCB física, lectura de verificación de Flash y UID, trabajos persistentes y protección contra operaciones simultáneas. Se registra firmware solo después de la verificación; queda pendiente la primera prueba de hardware.
- **Proyecto STM32CubeIDE FW 4.3.** Fuente completa, dependencias locales, Datos_editar.h y generador offline. Corrige el contador del timeout Debug y la consulta de sobrecorriente; conserva EEPROM y tramas.
- **Despliegue devsky.** Ejemplos sin secretos con montajes de código en solo lectura para evitar reconstrucciones grandes en la partición de desarrollo.

## v1.3.46 — 2026-10-08
- **QR de otras versiones.** Se reconocen etiquetas como `PCB_TQT_R3_V2_0_TIMER_0073` (versión con decimal "2_0" = V20 y texto entre la versión y el número) en Recibir, Consultar, MAC y firmware, DYMO y el servidor.
- **Recibir: ¿lote nuevo?** Si se escanea una placa de otra versión que la de la recepción actual, pregunta si es un lote nuevo: "Sí" confirma lo ya escaneado como su propio lote, cambia la versión por defecto e inicia el registro nuevo; "No" solo registra esa versión.
- **Escáner remoto más confiable.** El celular ve siempre la sección abierta en la PC (se actualiza en cada envío, al volver a la app y cada 10 s) y recibe la respuesta aunque se haya caído su conexión en tiempo real; la consola y DYMO recuperan los códigos que no les llegaron. Ya no hace falta desvincular al cambiar de sección.

## v1.3.45 — 2026-10-08
- **R3 en MAC y firmware.** Las R3 aparecen junto a las R1/R2 en "Pendientes" (las que no tienen firmware) y en "Con MAC" (las programadas), con filtro "R3". La columna MAC dice "No lleva MAC" y al elegir el firmware se guarda y queda "Programada". Al escanear una R3 (celular o lector USB) se abre la hoja **"Lote R3"**: cada R3 escaneada se agrega a la lista y con "Aplicar firmware a todas" se programa todo el lote con un solo firmware (también con el botón "Lote R3 (escanear)"). Botón **"Quitar firmware"** para regresar una R3 a "Sin firmware".
- **Escanear para imprimir en Etiquetas DYMO.** Nuevo panel con "Botón de escaneo" (vincula el celular con un QR) y campo para lector USB: se escanean solo las placas a imprimir. Una R1 o R2 agrega la etiqueta de su tarjeta (R1 + R2); las R3 se acomodan de dos en dos en la etiqueta R3 doble (si queda una sola, la otra mitad va vacía). "Imprimir escaneadas en DYMO" manda todo.

## v1.3.44 — 2026-10-07
- **Vincular el celular desde cualquier cámara.** El QR del "Botón de escaneo" de la consola se reconoce en Recibir, Emparejar, Programar y Consultar (y con la cámara del teléfono): el celular pasa directo a modo escáner vinculado, sin entrar antes a "Escáner para la consola".
- **R3 programada (sin MAC).** La R3 ya guarda su versión de firmware y queda "Programada" al tenerla. Al escanearla (Consultar, ficha de la consola, Inventario) se ve si está programada y con qué firmware. Se programa en el celular (Programar: selector de firmware para R3) y en la consola (MAC y firmware › pestaña "R3 firmware"; el escáner remoto la ubica ahí). Catálogo de firmware propio para R3. La R3 sigue sin aceptar MAC.
- **Lotes por mes, semana o día.** Al crear un lote se elige el tipo: Mes ("Septiembre 2026"), Semana ("Semana 40 · 28 sep–4 oct 2026") o Día ("15 sep 2026"); puede haber varios lotes en el mismo mes. Cada lote tiene su propio Excel (los de semana y día llevan sufijo). Los lotes existentes quedan como mensuales.
- **Rol Consultor en escritorio.** El consultor entra a la vista móvil (Consultar) y a la consola de escritorio, donde solo ve Dashboard, Tarjetas, Inventario de PCB, Consultar y Excel; las demás secciones no aparecen y los botones que modifican datos se ocultan. Sigue siendo de solo lectura.
- **Excel sin contraseña de administración.** Descargar el Excel ya no pide la clave de administración (solo la sesión). Importar, crear y sincronizar siguen protegidos. Enviar por correo el Excel del lote tampoco la pide (cuentas General y Administrador).
- **Etiquetas DYMO R3: dos por etiqueta.** La etiqueta de 57 × 32 mm se divide en dos tiras horizontales de 57 × 16 mm (se corta a lo largo) con una R3 en cada una: QR a la izquierda y nombre a la derecha. Si queda una sola R3, va en la tira de arriba. Selector "Imprimir: R3 de un lote" o "Rango de series"; con lote, "Imprimir lote R3 en DYMO…" abre una hoja con todas las R3 del lote para marcar cuáles imprimir (Marcar todas, Quitar todas, Solo programadas), igual que el lote de R1/R2. La hoja incluye también las R3 sueltas (registradas pero sin emparejar), con filtros "Solo de tarjetas" y "Solo sueltas".
- **Firmware a mano en Inventario de PCB.** El editor de una placa permite "Otra versión…" cuando la versión no está en el catálogo (p. ej. R3 sin catálogo), en lugar de solo las del catálogo.

## v1.3.43 — 2026-10-07
- **Consultar muestra el estatus de la tarjeta** (celular y escritorio): pasos Emparejada → Programada → Completa → Entregada con sus fechas, y datos de Llegada, Finalizada, Proyectada, Entrega y Gabinete. Cuando la tarjeta está **Completa**, ahí mismo se elige la **fecha real de entrega y el gabinete** (como la hoja "¿cuándo se entrega?" de la consola) y se puede corregir después. Las cuentas Consultor solo lo ven.
- **Tablets en vista de escritorio:** al abrir la app en una tablet (lado corto de 700 px o más: iPad, Galaxy Tab) se abre la consola de escritorio; los celulares siguen en la vista con cámara (también en horizontal).
- **Botón de escaneo (escáner remoto).** En la cabecera de la consola, en todas las secciones, el botón muestra un QR. El celular lo escanea (con su cámara o desde la app en *Más opciones › Escáner para la consola*), queda vinculado y lo que escanea aparece en la PC:
  - **MAC y firmware:** ubica la placa escaneada en Pendientes (o en "Con MAC" si ya tiene) y deja el cursor en su MAC; si después se escanea una MAC, se pone en esa placa.
  - **Inventario de PCB:** filtra la placa. **Tarjetas:** abre la tarjeta. **Consultar:** muestra la ficha.
  - **Dashboard, Inventario TQTR, Lotes, Excel y demás:** abre una ficha rápida con el estatus y las placas (con atajos a Tarjetas, Inventario o Consultar). Un código que no es de una placa va al buscador de la sección.
  - El celular ve en qué sección está la PC y qué hizo la consola con cada lectura. Solo quien escaneó el QR puede enviar códigos (el token no viaja por WebSocket); la vinculación caduca tras 12 h sin uso o con "Desvincular".

## v1.3.42 — 2026-10-07
- **Avisos de "Acceso restringido" por rol.** Cuando una cuenta General o Consultor intenta entrar a una zona sin permiso, ya no se le regresa sin explicación: aparece una hoja que dice a qué no tiene acceso, qué sí puede hacer su rol y que lo pida a un administrador. Aplica a:
  - **General:** Administración (página, menú "Más opciones", barra lateral de la consola, atajo de teclado), Movimientos, Excel protegido, y cambiar o crear lotes (la hoja de Lotes ya no muestra los botones; lo explica).
  - **Consultor:** Recibir, Emparejar, Programar, la consola de escritorio, Etiquetas DYMO, Administración y cualquier acción que cree, edite, envíe o borre (respuesta 403 de la API con `X-Acceso: rol`). Su logo lleva a Consultar.
  - Las pestañas y opciones bloqueadas se ven atenuadas con un candado. El servidor redirige con `?denegado=<zona>` y la página destino muestra el aviso. También se bloquean las copias `/static/*.html` de las páginas restringidas.
- **Seguridad:** una cuenta General o Consultor ya no puede aprobar el restablecimiento de contraseña de un Administrador (con eso podía quedarse con esa cuenta), y un Consultor no aprueba ninguno. Solo ve las solicitudes que puede aprobar.
- **Auditoría móvil (390 px):** menú "Más opciones" sin subrayado; Etiquetas DYMO ya no se sale de la pantalla; las 7 pestañas de Administración caben en el celular (Cuentas y Cuenta quedaban ocultas); la consola de escritorio en el celular acomoda su encabezado en dos filas (antes empujaba los botones fuera y la página se desplazaba de lado), el Dashboard pone R1/R2/R3 en una columna y las pestañas de Inventario TQTR y los botones de MAC bajan de línea. Se revisaron sin desbordes Recibir, Emparejar, Programar, Consultar, Administración (todas las pestañas), las 15 vistas de la consola, Login e Invitación.

## v1.3.41 — 2026-10-07
- **Tarjetas › Reporte por fecha con rango.** Campos "Desde" y "Hasta" (sin "Hasta" = un solo día) y atajos: Hoy, Ayer, Esta semana, Últimos 7 días, Este mes y Mes pasado. La tabla, el Excel y el envío por correo usan el rango (máximo un año). El Excel de un rango se llama `Tarjetas_AAAA-MM-DD_a_AAAA-MM-DD.xlsx`, agrega las columnas "Fecha finalizado" y "Fecha entrega" y una hoja "Por día" con completadas y entregadas de cada día.
- **Correos con diseño profesional y menos spam.** Todos los correos (Excel por correo, invitaciones, aviso de contraseña, stock mínimo y prueba) salen en texto + HTML con la plantilla de la marca: encabezado azul, indicadores, ficha del adjunto, mensaje del remitente y pie. Se agregan los encabezados `Content-Language`, `Auto-Submitted` y `X-Auto-Response-Suppress`. Los correos de solo texto con un adjunto eran los que los filtros mandaban a spam. El dominio ya tiene SPF, DKIM (Hostinger) y DMARC.

## v1.3.40 — 2026-10-06
- **Placas programadas.** Una R1/R2 con MAC y versión de firmware guardadas se muestra como "Programada" (o "Asignada · programada" si ya está en una tarjeta) en Inventario de PCB, Consultar, el detalle de la tarjeta y Administración; nuevo filtro "Programadas".
- **Inventario TQTR: Translock disponible = 16, como el Excel.** "Devolución" y "Desinstalado o Garantía" ya no suman a disponible: quedan aparte como "Devueltas / en revisión" (Translock: 2), con acciones "Pasar a disponible" o "Dar de baja" que registran el movimiento. Los armados que alcanzan con el stock bajan de 18 a 16 (los limita la caja Translock).

## v1.3.39 — 2026-10-06
- **Sensores magnéticos:** entrada de 73 en el Registro; con las 33 ya consumidas por los armados registrados, quedan 40 (migración única, también en bases existentes).
- **Silicón en gramos y catalizador en ml.** Por armado: 400 g de silicón y 6 ml de catalizador (Translock/Quintalock) y 100 g y 1.5 ml para la R3. Registros previos convertidos con factores editables en Configuración (envase de silicón = 1000 g, de catalizador = 15 ml). Costo por armado: **4,451.14 MXN** (Translock) / 4,625.14 (Quintalock).
- **Nueva pestaña "Stock Mínimo".** Mínimo, punto de reorden, armados objetivo, proveedor y tiempo de entrega por material; lista "Materiales a comprar" ordenada por urgencia (días de cobertura vs. tiempo de entrega) con cantidad sugerida. Aviso en el Dashboard de la sección y en la barra lateral, y correo a los administradores una vez cada vez que un material cruza su mínimo.
- **Auditoría de precios contra `Costos_Produccion_TQTR.xlsx`:** coinciden tipo de cambio, monedas, R2 y gabinete/actuador; cambian solo silicón y catalizador por las nuevas cantidades.

## v1.3.38 — 2026-10-06
- **Inventario TQTR descuenta materiales solo.** Al quedar completa una tarjeta (R1+R2+R3 y MAC de R1 y R2) se descuentan los materiales de sus tres placas; al asignarle gabinete se descuentan la caja (Quintalock/Translock) y el actuador, y si cambia de gabinete se ajusta. Solo cuentan las tarjetas completadas desde la activación (fecha editable en Configuración).
- **Ficha de materiales por tarjeta (merma).** Cantidad estándar vs. real de cada material, editable desde el detalle de la tarjeta (Tarjetas) y desde la nueva pestaña "Consumo" de Inventario TQTR; el costo real de la tarjeta y la merma se recalculan.
- **Desemparejar o borrar una tarjeta completa** devuelve al inventario solo el actuador y el gabinete; el resto queda como consumo de tarjeta disuelta. Funciona aunque nadie tenga abierta la consola (se concilia al arrancar y con un disparador en la base).
- Auditoría contra los dos Excel: diferencias (cables 0.55 vs 0.5 m, catalizador en ml vs piezas, relevador R3 fuera del total de costos) listadas en la pestaña Costos.

## v1.3.37 — 2026-10-06
- **"Enviar por correo" junto a cada exportación a Excel.** En Excel (copia del lote), Administración (Exportar Excel), Tarjetas (reporte por fecha) e Inventario TQTR. Se abre una ventana con las cuentas activas de la app como casillas, un campo para correos sin cuenta (separados por coma) y un mensaje opcional. El servidor genera el archivo (igual que la descarga) y lo manda adjunto por SMTP, un correo por destinatario (máx. 10). El Excel del lote sigue pidiendo la sesión de administración. Queda registrado en Movimientos (`EXCEL_CORREO`). Endpoints `GET /api/correo/destinatarios` y `POST /api/correo/excel`.

## v1.3.36 — 2026-10-06
- **"Resumen" ahora se llama "Dashboard"** en la consola de escritorio (el atajo `g r` sigue funcionando).
- **Etiquetas DYMO › Etiquetas R3.** Apartado propio para imprimir etiquetas de R3 que solo llevan el nombre de la placa (texto y QR): `TQT-R3-V30-0000`. La versión (V30) se puede cambiar; se imprime una serie o un rango (máx. 500 por tanda) con sus copias, con vista previa a escala real. Endpoints `GET /api/dymo/r3/xml` y `/api/dymo/r3/archivo`.
- **Inventario TQTR › Costos** (desde `Costos_Produccion_TQTR.xlsx`). Costo por armado (R1 + R2 + R3 + gabinete y actuador) = **4,426.28 MXN** con Translock y tipo de cambio 18.5, desglosado por placa; tipo de cambio y gabinete de costeo editables; valor del inventario en existencia, armados que alcanzan con el stock y costo de lo producido. KPIs de costo en el Dashboard de la sección y hoja "Costos" en la exportación.

## v1.3.35 — 2026-10-06
- **Administración › Cuentas: alta por invitación de correo.** El administrador escribe correo y rol; la persona recibe por SMTP un enlace (48 h, un solo uso) a `/invitacion`, elige su contraseña y entra directo. Nadie conoce la clave de otro. Si el correo falla, se muestra el enlace para compartirlo a mano. Lista de cuentas con cambio de rol, activar/desactivar, reenviar invitación y eliminar (doble clic para confirmar). Botón "Probar envío de correo". Todo queda en Movimientos.
- **Roles.** *Administrador*: todo, incluida Administración. *General*: opera la app sin acceso a Administración. *Consultor*: solo la página Consultar (escaneo) y lecturas; cualquier intento de crear, editar o mover datos responde 403 y las demás páginas lo mandan a Consultar. Las cuentas que ya existían quedan como administrador. Nunca se puede dejar la app sin un administrador activo.
- **Tarjetas › Reporte por fecha.** Se elige un día y se ve cuántas tarjetas se completaron (fecha de finalizado) y cuántas se entregaron (fecha real) en todos los lotes; la tabla se filtra a esas tarjetas y "Exportar Excel" descarga un reporte con encabezado, indicadores, tabla con filtros y nota de criterios (`GET /api/reporte-dia`, `/api/reporte-dia/excel`).
- **Nueva sección Inventario TQTR** en la consola de escritorio con el contenido del libro `INVENTARIO_TQTR_26_v.xlsx`.

## v1.3.34 — 2026-10-05
- **Correo saliente desde el backend (SMTP).** Nuevo `app/services/correo.py`: TLS implícito por el puerto 465 con validación de certificado, remitente fijo (`TQT_SMTP_FROM`) y Reply-To opcional. Las credenciales solo viven en variables de entorno (`TQT_SMTP_*`, plantilla sin contraseña en `.env.example`). Nuevo `POST /api/admin/correo/prueba` (solo supervisor) y aviso por correo a la cuenta cuando se restablece su contraseña (si el envío falla, el restablecimiento sigue). SPF, DKIM y DMARC verificados en PASS desde la app.
- **Sin contraseña inicial por defecto en el código.** `TQT_USER_SEED_PASSWORD` ya no trae valor: si no se define, no se crean las cuentas iniciales (las existentes no se tocan). Las pruebas leen la clave del entorno. Importante al instalar desde cero: define esa variable en `.env`.

## v1.3.33 — 2026-10-05
- **"¿Olvidaste tu contraseña?" aprobado por otra cuenta.** En el inicio de sesión se pide el correo; otra persona con sesión abierta ve la solicitud en la consola (icono de escudo con contador), la aprueba y recibe un código de 6 dígitos que le dicta en persona. Quien olvidó escribe el código y su contraseña nueva (mínimo 10 caracteres). Nadie teclea la clave de otra persona. El código vale 10 minutos y se bloquea tras 5 intentos; no se puede aprobar la propia solicitud; el cambio cierra las sesiones de esa cuenta y queda en la bitácora. Respuestas iguales exista o no el correo y límite de solicitudes por equipo.

## v1.3.32 — 2026-10-05
- **Resumen (escritorio): cada indicador se abre para ver su detalle.** Al hacer clic (o Enter) en Tarjetas, Completas, Con/Sin MAC, Falta placa, Finalizadas, Entregadas, Por entregar, Etiquetas por imprimir y los de Inventario de PCB, se abre una hoja con la lista de tarjetas o placas que lo componen, con acceso directo a la sección correspondiente.

## v1.3.31 — 2026-10-05
- **Administración: la hora de "Últimos movimientos" y de la bitácora ya es la local.** Se guardaba en UTC (6 h de adelanto); ahora se muestra y filtra por fecha en hora local del servidor.
- **Emparejar (móvil): los contadores se actualizan al instante.** "Completas" e "Incompl." cuentan las tarjetas del lote (misma regla que el Resumen) y la pantalla se refresca también cuando se empareja una tarjeta (faltaba escuchar ese aviso).

## v1.3.30 — 2026-10-05
- **Descargar copia .xlsx ya no se pierde al pedir la contraseña de administración.** Si la sesión de administración no estaba activa, tras escribir la contraseña correcta se regresa a la sección Excel y la copia se descarga sola, sin tener que volver a pulsar el botón.

## v1.3.29 — 2026-10-05
- **Emparejar (móvil): las tarjetas completas van al final.** Arriba quedan las pendientes (sin R3 o sin MAC) y, al completarse, la tarjeta baja sola al final de la lista.

## v1.3.28 — 2026-10-05
- **Entrega de tarjetas concluidas: selección múltiple.** En la hoja "¿cuándo se entrega?" ahora hay casilla por tarjeta y "Todas"; con una barra para elegir fecha y/o gabinete y "Aplicar" a las seleccionadas (el gabinete en blanco no cambia nada). Sigue pudiéndose editar cada fila.

## v1.3.27 — 2026-10-02
- **Inicio de sesión, segunda pasada de diseño (móvil, escritorio, claro y oscuro).** Campos con etiqueta flotante y una barra ámbar que se dibuja al enfocar; el botón "Entrar" tiene un brillo que sigue al cursor y muestra "Entrando…". En escritorio, la etiqueta DYMO se inclina con el cursor con un reflejo satinado, hay un foco de luz sobre la mesa de trabajo y una cuadrícula de puntos; cada 9 s se lee una tarjeta distinta (cambian QR, trama y confirmación) y el fondo del formulario respira. Aviso de Bloq Mayús, línea "¿Sin cuenta? Pide acceso a un supervisor", objetivos táctiles de 44 px o más. Todo respeta "reducir movimiento".

## v1.3.26 — 2026-10-02
- **Inicio de sesión animado y con versión.** Secuencia de entrada en orden: el circuito se traza, el logo gira al lugar, la etiqueta DYMO llega y se lee, el titular sube línea por línea y el formulario aparece campo por campo. Después, un ciclo discreto: la etiqueta se vuelve a leer cada 9 s y una señal recorre el circuito. El botón brilla al pasar el cursor y muestra un indicador mientras entra, el error sacude el mensaje y el campo enfocado resalta su etiqueta. Abajo se muestra la versión en uso (la inyecta el servidor) y un punto "Servidor en línea" que consulta `/api/health`. Con "reducir movimiento" activo no hay animaciones.

## v1.3.25 — 2026-10-02
- **Nuevo diseño de la pantalla de inicio de sesión (móvil y escritorio).** En escritorio, una mesa de trabajo con la etiqueta DYMO real (QR y trama de 4 líneas) que se lee una vez al abrir la página, y el formulario plano a la derecha. En móvil, banda compacta con logo y mini etiqueta, y el formulario a la vista sin desplazarse. Campos más grandes, botón "Ver" dentro del campo de contraseña, errores solo cuando hay texto, tema claro/oscuro y sin movimiento si el sistema lo pide. No cambia el flujo de acceso ni el cambio de contraseña.

## v1.3.24 — 2026-10-02
- **Resumen de la consola actualizado.** Nuevo bloque "Producción y entrega" (finalizadas, entregadas, por entregar y etiquetas por imprimir) y dos tarjetas: "Avance de pruebas" (liberadas, en proceso, retrabajo, detenidas, pendientes) y "Etiquetas DYMO" (impresas vs. por imprimir, con la misma regla de firma que el lote de impresión).

## v1.3.23 — 2026-10-02
- **DYMO: lo impreso ahora se guarda en la base de datos.** En v1.3.22 el registro de etiquetas impresas vivía en el navegador, así que no se veía en otros equipos ni incluía lo impreso antes. Ahora es la columna `etiqueta_firma` de la tarjeta (se crea sola al arrancar) y el lote las pinta en azul con "Impresa" desde cualquier equipo.

## v1.3.22 — 2026-10-02
- **DYMO: el lote marca las etiquetas ya impresas.** En la ventana "Imprimir lote en DYMO" las tarjetas ya impresas se pintan en azul con la insignia "Impresa", y el contador indica cuántas van. Se registra al enviar con éxito a la impresora (individual o lote), por navegador. Si después cambia la pareja o se completa la MAC, la tarjeta vuelve a figurar como pendiente para reimprimirla.

## v1.3.21 — 2026-10-02
- **Sonido más confiable al escanear (Consultar, Emparejar, Programar, Recibir).** Si el navegador tenía el audio suspendido, el primer pitido se perdía y, tras suspenderse otra vez (iOS, segundo plano), el desbloqueo ya no se rearmaba. Ahora todos los sonidos esperan al `resume()` y el desbloqueo se rearma solo. En Consultar, las recargas automáticas por cambios de otro equipo ya no hacen sonar el pitido de lectura.

## v1.3.20 — 2026-10-02
- **Consultar (móvil): se puede seguir escaneando tras un resultado.** Antes, con una ficha en pantalla la cámara quedaba en una franja de 60 px sin marco y había que bajar hasta "Nueva consulta". Ahora cámara y buscador quedan fijos arriba (franja de ~130 px con marco) y la ficha se desplaza debajo, de modo que se consulta la siguiente tarjeta sin bajar.

## v1.3.19 — 2026-10-02
- **Al concluir una tarjeta, la consola pide la fecha real de entrega.** Cuando una tarjeta queda con R1, R2, R3 y las MAC de R1 y R2, la base ya sella sola su "Fecha Finalizado" (columna T del Excel); ahora, además, la consola de escritorio abre una hoja con las tarjetas concluidas que no tienen entrega: cada una con su fecha (se propone la proyectada o la de hoy) y su gabinete. "Guardar fechas de entrega" las manda al Excel (Fecha Real Entrega, K); "Más tarde" las pospone en esa pestaña. Se revisa al abrir la consola y con cada cambio de placas, tarjetas o Excel.
- **Excel (auditoría de fechas)**: al importar, una celda de fecha solo se acepta si es fecha de Excel, texto `AAAA-MM-DD` o `dd/mm/aaaa`; antes un texto raro o un número se guardaba truncado como basura. Pendientes conocidos de la auditoría: los cuatro formatos de fecha del libro son distintos, S/T no tienen validación y borrar una fecha en un lado no la borra en el otro.

## v1.3.18 — 2026-10-01
- **Un solo "Cerrar sesión"**: en la consola de escritorio había dos botones; el de texto solo cerraba la sesión de supervisor y mandaba a /admin. Se quitó; el icono de salida ahora cierra también la sesión de supervisor y lleva a /login.

## v1.3.17 — 2026-10-01
- **Pantalla de inicio de sesión rediseñada**: mobile-first (una columna, campos de 48 px y 16 px para que iOS no haga zoom) y vista de escritorio de dos paneles (marca + formulario). Tema **claro y oscuro** con botón sol/luna; recuerda tu elección (`tqt.tema`, el mismo de la app) y, si nunca elegiste, usa el del sistema.

## v1.3.16 — 2026-10-01
- **Inicio de sesión con correo y contraseña en TODA la app.** Sin sesión no abre nada: ni las páginas (redirigen a `/login`), ni la API (401), ni el WebSocket (se rechaza), ni los archivos JS/HTML. Solo son públicos `/login`, `/api/auth/login`, `/api/health` (Docker) y los certificados `/cert` y `/ca` (los celulares los instalan antes de entrar), más CSS, fuentes e iconos.
- Cuentas iniciales: `developer@`, `developer4@`, `developer5@` y `developer6@skyguardian.mx` con la contraseña inicial acordada; la pantalla ofrece cambiarla al entrar y desde el candado de la consola (`/login?cambiar=1`). Mínimo 10 caracteres. Las contraseñas se guardan con PBKDF2-SHA256 (600,000 iteraciones y sal); nunca en claro.
- Sesión: cookie firmada `tqt_sesion` (HttpOnly, Secure, SameSite=Lax, 12 h). Cambiar la contraseña o desactivar la cuenta invalida todas sus sesiones. Límite de intentos por equipo y por correo (5 fallos = 5 min) con retardo uniforme y un solo mensaje para "correo desconocido" y "clave incorrecta". Botón de cerrar sesión en móvil y consola.
- La contraseña de supervisor de `/admin` sigue como segunda capa. `/api/config` ahora exige sesión; el healthcheck de Docker usa `/api/health`.
- Pruebas: 17 nuevas (`test_auth_seguridad.py`: recorren TODAS las rutas del esquema sin sesión, cookies manipuladas o vencidas, WebSocket, bloqueo, cambio de clave, cuenta desactivada) y un e2e en Chrome (`tests/e2e/login_flujo.py`). Los demás scripts de `tests/e2e/` que hablan con la API necesitan iniciar sesión primero.

## v1.2.16 — 2026-10-01
- **Fechas de llegada, finalizado y entrega + gabinete (Quintalock / Translock)** por tarjeta. Llegada y finalizado se llenan solas (disparadores de la base: llegada = recepción confirmada de sus placas; finalizado = el día en que la tarjeta queda con R1+R2+R3 y la MAC de R1 y R2) y todas se pueden corregir a mano. En Tarjetas, el panel de cada tarjeta tiene "Fechas y entrega" con "Marcar entregada hoy"; la tabla muestra Entrega y Gabinete. `PATCH /api/tarjetas/{id}` acepta `fecha_llegada`, `fecha_finalizado`, `fecha_real` (entrega) y `gabinete`.
- **Excel**: exporta Gabinete a Producción!L (la lista Translock/Quintalock de la plantilla), la entrega a K y agrega las columnas "Fecha Llegada" y "Fecha Finalizado" (S y T, con el estilo de las demás) si el libro no las tiene; la importación las lee de vuelta (también de Excel anteriores). Cierra el pendiente "Gabinete no se guardaba".
- Bases anteriores se migran solas (columnas + fechas retroactivas).

## v1.2.15 — 2026-09-30
- **Etiquetas DYMO**: QR de vuelta a 20.8 mm (módulo de 6 puntos) y texto más grande (9.5 pt, antes 8); zona segura 1.5 mm. "Imprimir lote en DYMO…" abre una ventana con una casilla por tarjeta (con buscador, "Marcar todas", "Quitar todas" y "Solo con MAC") para imprimir solo las elegidas.
- **Resumen y estados de tarjetas**: una tarjeta sin R3 ya no esconde el avance de las MAC. Nuevas tarjetas "Con MAC", "Sin MAC" y "Falta placa" (conteos independientes); estado "Sin MAC: R1, R2 · falta R3". "Incompletas" pasa a llamarse "Falta placa". El conteo "Sin MAC (R1/R2)" del Resumen usa la misma regla que Inventario y que MAC y firmware.
- **Datos siempre al día**: todas las pantallas (consola y móviles) se resincronizan al reconectarse el WebSocket, al volver a la pestaña y cada 45 s; Excel muestra el conteo real de tarjetas; importar Excel avisa a las demás pantallas (`EXCEL_IMPORTADO`); Programar y Consultar también reaccionan a placas recibidas y recepciones confirmadas.

## v1.2.14 — 2026-09-30
- **La etiqueta impresa ahora sí crece**: el servicio DLS dibuja el `BarcodeObject` con un tamaño fijo (máx. 16 mm) e ignora la caja del diseño, por eso la zona segura de 1.5 mm no cambiaba nada. El QR se envía como imagen 1 bit a 300 dpi con módulos de 7 puntos exactos (24.3 mm, antes 16); verificado que decodifica igual.
- **Vista previa fiel**: zona segura 1.5 mm, texto Consolas 8.5 pt negrita, 4 líneas seguidas y QR de 7 puntos (antes mostraba 3 mm / 7.5 pt / 20.8 mm).
- **Etiquetas DYMO**: tarjetas ordenadas de menor a mayor y nuevo campo "Buscar pareja" para teclear el número (p. ej. `21` → 0021, 0121…) y encontrar la etiqueta más rápido.
- Dockerfile: el `chown` del toolchain ESP32 se hace antes de copiar la app (capa cacheada); los rebuilds ya no duplican varios GB.

## v1.2.13 — 2026-09-30
- **Corregida la impresión DYMO (error "PrintLabel … Error: 400")**. Causa: la PC tiene **DYMO Label Software v8** (servicio DLS, LabelWriter 450), que solo entiende etiquetas `<DieCutLabel>`; la app mandaba el XML de DYMO Connect (`<DesktopLabel>`) y además el XML v8 propio era inválido (`<Font>` en vez de `<TextFont>` en el código QR, `Id` y orientación distintos a los de las etiquetas reales de DYMO). Ahora el XML v8 replica el de una etiqueta 30334 real (`Small30334`, 3240×1800 twips) y se valida contra `RenderLabel`.
- Imprimir prueba primero el formato v8 y, si el servicio lo rechaza, el de DYMO Connect; sirve con cualquiera de los dos programas. "Abrir en DYMO" y el ZIP descargan `.label` (lo abren DYMO Label y DYMO Connect).
- **Etiqueta más grande**: zona segura de 3 → 1.5 mm (54×29 mm útiles), QR con módulo de 7 puntos (24.3 mm, antes 20.8) y texto a 8.5 pt (antes 8).

## v1.2.12 — 2026-09-29
- **Programar R1/R2 por USB desde la consola de escritorio**: en "MAC y firmware" (`/monitor`), con una placa pendiente, un botón nuevo compila el firmware correcto (backend, `arduino-cli` horneado en la imagen Docker, placa `esp32:esp32:esp32doit-devkit-v1`) y lo flashea directo por USB desde el navegador (Web Serial, sin Arduino IDE ni instalar nada; requiere Chrome/Edge de escritorio). Muestra el registro en vivo para ver cuándo la tarjeta ya está en modo programador y lista para flashear. Al terminar, lee la MAC por el mismo puerto serial y la guarda sola. Reemplaza: editar el `.ino` a mano → compilar/subir con Arduino IDE → abrir el monitor serial → leer la MAC → teclearla.
- El firmware STM32 "R1 Principal" sigue siendo manual con STM32CubeIDE (no está cubierto por esta versión).
- `.ino` de R1 y R2 versionados en `firmware/` dentro del repo (ver `firmware/README.md` para cómo actualizarlos).

## v1.1.12 — 2026-09-25
- **Excel = plantilla de referencia con Botón R3**: la plantilla mensual ahora es `Control_Produccion_TQT_Septiembre.xlsx` tal cual (Producción!H `Botón R3` con lista de disponibles `O3#`, Catálogo PCB K:M con las R3 sin MAC y `O3 = FILTER` de disponibles, Etiquetas!G apunta a Producción!I). Se conservan fórmulas (2,211), tablas, validaciones (incluidas x14 y ANCHORARRAY), formato condicional, `FILTER` dinámico (`cm="1"` + `metadata.xml`) y `fullCalcOnLoad`.
- **Exportar**: escribe la R3 de cada tarjeta en Producción!H y las R3 en Catálogo K/L (sin MAC); los firmwares nuevos van a las listas O/Q. Excel de la versión anterior (sin R3) se sigue exportando en su layout.
- **Importar**: detecta el layout por el encabezado `Botón R3`, valida encabezados exactos (error claro), carga R3 y **reporta conflictos** (R3 repetida, inexistente en el catálogo o con MAC) en vez de ignorarlos. Compatible con Excel anteriores sin R3.
- Pendiente conocido: Gabinete (Producción!L) no se guarda en la BD, por lo que no se importa/exporta.

## v1.1.11 — 2026-09-24
- **Consultar, terminada (celular y PC)**: ahora sí se puede buscar por **número de tarjeta** (`0011`, `11` o `#11`), como prometía la pantalla; antes respondía «No reconozco el código». Si aún no hay tarjeta con ese número, muestra las **placas con esa serie** (R1/R2/R3) con el aviso «Sin tarjeta» y un acceso directo a emparejar. API: `GET /api/consulta?codigo=0011` (`origen: "tarjeta"` o `"serie"`).
- **Celular**: consultas recientes como botones en la pantalla vacía; textos más claros (errores «No encontramos ese código» / «No se reconoce ese código», ayuda con ejemplos).

## v1.1.10 — 2026-09-24
- **Consola de PC > Tarjetas, completa**: con el lote sin tarjetas ya no queda en blanco. Nueva sección **«Por emparejar»** con las placas sueltas y una vista previa de lo que se creará (parejas, impares y R3 según el modo elegido), con «Unir» por pareja y **«Armar a mano (impar)»**. En el detalle de cada tarjeta: **Asignar / Cambiar / Quitar** R1, R2 y R3 desde una lista de placas sueltas con búsqueda.
- **Celular > Emparejar, en orden de avance**: primero las **tarjetas ya emparejadas** (por número), luego las listas para emparejar, las impares y al final las incompletas.

## v1.1.9 — 2026-09-24
- **Cómo emparejar las R3 (elegible)**: **Manual** (por defecto): «Emparejar todas» solo une R1 + R2 y la R3 se asigna a mano en cada tarjeta. **Automático (par e impar)**: la R3 del mismo número, o la siguiente que sobre en las impares, y monta las R3 que llegaron después. Selector en el celular (Emparejar) y en la consola de PC (Tarjetas); se recuerda por equipo. API: `r3: "manual"|"auto"` en `POST /api/emparejar/auto` y `GET /api/emparejar/sugerencias`.

## v1.1.8 — 2026-09-24
- **Emparejar en dos tiempos y en orden numérico**: primero las parejas (R1 + R2 del mismo número, con su R3 si está) y después las **impares** con lo que sobra: la R1 más baja con la R2 más baja (p. ej. R1 0018 + R2 0021; la R3 del mismo número o, si no hay, la siguiente que sobre). Lo que queda sin par se deja suelto. La pantalla Emparejar muestra la sección «Impares» y el botón cuenta todo lo que se va a hacer.
- **R3 que llegan después**: «Emparejar todas» (celular y consola de PC) monta la R3 disponible en la tarjeta del mismo número que aún no la tenía, sin borrar sus pruebas. Antes las tarjetas ya creadas nunca recibían las R3 recibidas más tarde y había que asignarlas una a una.
- **Resumen de la consola**: ya no dice «Todo en orden, todas las tarjetas están completas y con MAC» cuando el lote no tiene tarjetas (con 0 tarjetas todo se cumplía en vacío). Ahora avisa «Todavía no hay tarjetas» y cuántas placas sueltas faltan por emparejar, con un acceso directo.

## v1.1.7 — 2026-09-24
- **Editar una placa ya emparejada**: los botones R2/R3 del tipo estaban bloqueados cuando la placa estaba en una tarjeta. Ahora se puede cambiar el tipo: al guardar la placa sale de su tarjeta y queda suelta con el tipo nuevo (todo o nada; si el nombre nuevo ya existe no se cambia nada).
- **Desemparejar** en masa: `POST /api/tarjetas/disolver` (tarjetas elegidas o `todas` del lote; omite las que tienen pruebas salvo `forzar`). En la consola de PC (Tarjetas): selección múltiple, «Desemparejar», «Desemparejar todas» y «Desemparejar» en el detalle de cada tarjeta. En el celular (Emparejar): «Desemparejar todas» (una a una ya existía en cada tarjeta).
- **Consola de PC**: botón «Emparejar completas» en Tarjetas (antes solo se podía emparejar desde el celular).

## v1.1.6 — 2026-09-24
- **Excel exportado aún más idéntico a la plantilla**: la hoja Pruebas conserva sus 500 fórmulas de matriz dinámica (`cm="1"` + `metadata.xml`); antes Excel las mostraba como fórmulas de matriz heredadas `{=...}`. Se comparó contra `Control_Produccion_TQT_Septiembre.xlsx` (idéntico a la plantilla): mismas 4 hojas, tablas, validaciones, formatos condicionales, anchos, vistas y fórmulas. Lo único que no se copia es el panel de un complemento de Excel (`webextensions`) y los valores en caché (Excel recalcula al abrir).

## v1.1.5 — 2026-09-24
- **Cada persona ve solo su lote de recepción**: antes, con varios celulares escaneando a la vez, todos veían el total combinado y cualquiera podía confirmar el lote de los demás. Ahora cada equipo lleva una marca anónima (sin cuentas ni contraseñas) y su contador, su lista, sus avisos de series faltantes y el botón "Confirmar lote" solo incluyen lo que escaneó ese equipo. Las placas confirmadas siguen siendo comunes (inventario, emparejar, consola). Las que estaban sin confirmar antes de actualizar las ven todos.

## v1.1.4 — 2026-09-24
- **Varias personas a la vez**: verificado con carga real (16 celulares escaneando y programando en paralelo, 5 sesiones de administración simultáneas e independientes) sin errores ni duplicados (`tests/e2e/multisesion.py`).
- **Bloqueo por intentos fallidos por equipo**: dentro de Docker todos los equipos llegan con la misma IP y 5 fallos de una persona bloqueaban el acceso de administración a todos. Ahora cada equipo lleva una marca anónima (cookie `tqt_cid`) y se bloquea solo el que se equivoca; hay un tope global (30 fallos) contra quien intente saltarse el límite.

## v1.1.3 — 2026-09-24
- **Exportar a Excel con la estructura idéntica a `Control_Produccion_TQT_[Mes].xlsx`** en cualquier situación: las tarjetas salen emparejadas o no, con o sin MAC, con o sin R3 (la plantilla no tiene R3, así que no se agregan columnas ni texto), incompletas (solo R1 o solo R2) y todas las **placas R1/R2 del inventario** aparecen en el Catálogo PCB aunque no estén en una tarjeta, no tengan MAC o no estén confirmadas (la fórmula del Excel las marca SUELTA). Mismas 4 hojas, las 2,110 fórmulas, validaciones y formatos; si una tarjeta no tiene R1, la columna B conserva su fórmula. La plantilla admite 100 tarjetas y 100 placas por tipo: si hay más, avisa cuáles no caben (siguen en la base de datos).

## v1.1.2 — 2026-09-24
- **La contraseña ya solo se pide en la zona de administración** (`/admin`, donde se borran tarjetas/PCB, se vacían lotes y se exporta). La consola de PC (`/monitor`), las pantallas del celular y las acciones de lote (usar/crear lote, sincronizar Excel) abren sin contraseña.
- **Cámara**: si la cámara elegida no abre (cámara virtual o infrarroja de una laptop, o una trasera/frontal que el equipo no tiene), el escáner la olvida y vuelve a una que funcione; ya no queda atascado en "La cámara está ocupada".

## v1.1.1 — 2026-09-24
Primera versión versionada en el repositorio. Reúne todo lo construido desde la v1.0.0 (asistente de 4 pasos con MAC escaneada).

### Flujo real de planta
- **Recibir** (celular, cámara): registro automático de cada PCB al pasar por la cámara (QR grabado blanco sobre negro, invertido; contiene `TQT-R3-V30-0084`). Lote de recepción que se confirma, edita o elimina; alta manual de las que no traen QR.
- **Emparejar**: R1+R2+R3 por número, tarjetas "impares", reemplazo de placas falladas.
- **Programar**: MAC de R1 y R2 tecleada (la R3 no lleva MAC ni firmware) y **versión de firmware** con catálogo del Excel (Principal `2, 3.2, 3.3, 4.0, 4.1, 4.2`; Respaldo `2, 2.1`).
- **Consultar**: al escanear la etiqueta DYMO (4 líneas), el QR de una PCB o una MAC, ficha completa: pareja, MAC, *Hardware V30*, *Firmware*.
- El `V30` es la **versión de hardware**; el firmware es aparte.

### Consola de escritorio (PC, sin cámara)
- La PC entra sola a `/monitor`: Resumen, Inventario de PCB, Tarjetas, **MAC y firmware** (captura con teclado, pegado masivo con vista previa, corrección), Consultar, Lotes y Excel. Atajos de teclado, modo claro/oscuro.
- "MAC guardadas hoy" cuenta a **todos los operarios** (sale del servidor).
- Selector de lote en el encabezado móvil y en la consola; cambiar de lote afecta a todos.
- La versión se muestra en el pie (móvil) y en la barra lateral (consola).

### Administración y seguridad
- `/admin` con contraseña (`TQT_ADMIN_PASSWORD`): borrar tarjetas/PCB, vaciar lote, borrado total (con respaldo previo), exportar Excel, cambiar clave.
- **Movimientos**: historial de lo que se hizo (altas, ediciones, eliminaciones, sesiones, Excel); "Borrar TODO" no lo borra.
- La consola y las acciones de supervisor exigen sesión; cookie `tqt_admin` (HttpOnly, Secure, SameSite=Strict).
- Cierre de sesión claro (sin bucle de contraseñas).
- Cabeceras de seguridad, protección contra peticiones de otros orígenes, rutas de archivos restringidas.

### HTTPS sin aviso de "sitio no seguro"
- Autoridad certificadora local (`certs/ca.pem`) que firma el certificado del servidor; se instala una vez por dispositivo (`instalar_certificado.ps1`, ruta `/cert`). Sigue valiendo si cambia la IP.

### Excel y etiquetas
- Sincronización con la plantilla mensual sin romper fórmulas ni validaciones; el firmware llega a `Producción!D/G` y las versiones nuevas a las listas.
- Etiqueta **DYMO 30334** (57×32 mm) con la trama de 4 líneas (nombre R1, MAC, nombre R2, MAC) e impresión con DYMO Connect.

### Despliegue
- Docker (`desplegar.ps1`, `docker-compose.yml`), respaldos (`respaldar.ps1`), guía en `docs/DESPLIEGUE.md`.

### Quitado
- La sección **Pruebas** (páginas, API y enlaces). Se conserva solo la tabla interna y la hoja `Pruebas` de la plantilla Excel.

## v1.0.0
Versión inicial: asistente de escaneo de 4 pasos (R1 → MAC → R2 → MAC), monitor y sincronización básica con Excel.
