# Historial de versiones — Escáner TQT

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
