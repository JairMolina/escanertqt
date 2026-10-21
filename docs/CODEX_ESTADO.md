# Estado de Codex: TQT-Web

Actualizado: 2026-10-21 (Claude Code)
Commit de referencia: ver `git log` de main (v1.4.20; producción en 1.4.13 hasta que se despliegue)

## v1.4.20 (2026-10-21, Claude Code)
- Estado «programada» con FW capturado a mano: `r2_programming.statuses` ya no exige evidencia BLE (compara FW guardado o `firmware_r2` de la tarjeta contra el más reciente; `verified` sigue aparte). `_SELECT_PCB` hereda `firmware_r1/r2` de la tarjeta, así las listas R1/R3 coinciden con Tarjetas.
- TQT R2 con la estructura de R1/R3 (tarjeta → acciones → avance → firmware → Bluetooth/monitor/USB).
- Pruebas TQT: historial bajo «Elige una tarjeta», oculto sin tarjeta elegida.
- Evidencia: 240 pruebas de suites pertinentes OK (2 de test_r2_programming adaptadas a la nueva regla), `node --check` OK. Sin revisión visual con sesión ni con la BD de producción.

## v1.4.19 (2026-10-20, Claude Code)
- Programación R1/R3: estatus por tarjeta en la lista, detalle en dos mitades, botones y avance arriba, estación J-Link automática (sin menú). Pruebas TQT: tarjeta + inventario arriba, intro/serial/historial apilados, prueba automática a todo el ancho.
- Evidencia: test_qa_version_hoy OK, `node --check` OK, Docker local 1.4.19. Sin revisión visual con sesión ni hardware.
- Pendiente: el usuario reporta que ON/OFF BLE sale por serial; el código revisado envía por BLE (puente Windows y Web Bluetooth). Falta evidencia del registro.

## v1.4.18 (2026-10-20, Claude Code)
- Impresora: etiqueta «ACT» arriba y número abajo junto al QR; exportar Excel (`/api/activos/exportar.xlsx`, filtros o selección); selección en lote y eliminación con contraseña del usuario (`/api/activos/eliminar-lote`, mismo limitador que el login, bitácora `ACTIVOS_ELIMINADOS`).
- Evidencia: 174 pruebas de las suites pertinentes OK; Docker local 1.4.18 con los 372 activos. Exportar/eliminar sin probar con datos reales.

## v1.4.14–v1.4.17 (2026-10-20, Claude Code)
- Módulo Impresora disponible: activos ACT 0000 (`app/services/activos.py`, `app/routers/activos.py`, tablas `activos`/`activos_eventos` creadas solas), etiqueta DYMO 30334 solo con «ACT 0000» + QR (`/impresora?activo=ACT-0000`), impresión individual y por lote a la DYMO compartida (misma cola que TQT, tipo `activo`), estado `/api/activos/impresora/estado`, vincular celular, importación de Excel (`activos_import.py`, solo filas verdes) con departamento y características. Interfaz propia y acceso propio `/impresora/acceso`.
- Permiso por módulo de cada ruta (`modulos.modulo_de_ruta`, rutas compartidas); invitaciones por correo a módulos desde el núcleo (`/api/plataforma/invitaciones`).
- Evidencia: suites pertinentes OK (test_activos, test_activos_import, test_invitaciones_modulo y las de plataforma/auth/dymo). Docker local 1.4.17 con 372 activos importados del Excel de inventario (BD local; el Excel no está en el repo). Sin impresión física ni prueba con celular real.
- Para producción: `TQT_PUBLIC_URL` debe estar definida (si no, el QR toma la URL con que la Raspberry pide la etiqueta); SMTP con `TQT_SMTP_*`; verificar que el agente de la Raspberry acepte trabajos de tipo `activo` (descarga el mismo SVG genérico). La carga inicial de activos se hace con el botón «Importar Excel».
- Pendiente: activos ACT-0281 y ACT-0377 traen una contraseña en notas (decisión del usuario).

## v1.4.11–v1.4.13 (2026-10-20, Claude Code)
- Plataforma «I+D»: portal `/inicio` con 7 módulos (catálogo `app/modulos.py`; Escáner TQT disponible, el resto «Próximamente»), órbitas con una sola elipse por anillo.
- Acceso por módulo: columna `usuarios.modulos` (default `escaner-tqt`, la crea sola al arrancar); administradores entran a todo; sin Escáner TQT asignado, páginas → `/inicio?denegado=escaner-tqt` y API 403 `X-Acceso: modulo`.
- Núcleo I+D: siempre botón; pide «Acceso de administrador» (`POST /api/plataforma/entrar`, solo abre sesión a administradores) y despliega «Cuentas y módulos» (`app/routers/plataforma.py`: GET/PATCH cuentas, POST `/modulos/{id}/todos`). También en Administración › Cuentas.
- Evidencia: 125 pruebas de las suites pertinentes OK (test_plataforma_cuentas y test_portal_modulos nuevas). Docker local 1.4.13 healthy. Móvil revisado con emulación CDP a 360/390/412 px (sin desborde, objetivos ≥40 px) y panel de cuentas con servidor aislado. Sin prueba en celular físico ni con cuentas reales.
- Pendiente: desplegar; los 6 módulos nuevos aún no tienen aplicación.

## v1.4.10 (2026-10-20, Claude Code)
- Portal de módulos en `/inicio` (constelación: núcleo TQT y módulos como estrellas en órbita). Módulos en `MODULOS` de `app/main.py`, servidos en `GET /api/modulos` (público). Sin sesión, `/` → `/inicio`; las demás páginas siguen → `/login?next=`. Enlace «← Módulos» en login, consola y móvil. Archivos nuevos: `inicio.html`, `css/inicio.css`, `js/inicio.js`.
- Evidencia: 84 pruebas OK (test_portal_modulos nuevo, test_qa_version_hoy, test_auth_seguridad, test_api, test_admin, test_cuentas_roles, test_consultor_escritorio). Revisión en Chrome con servidor local aislado: claro, oscuro, ficha al pasar el cursor, Entrar sin sesión → login, enlace de regreso. No revisado en navegador a 375 px ni con sesión real.
- Pendiente: probar en celular, definir los módulos reales («Próximamente» son de ejemplo), merge a main y despliegue cuando se pida.

## v1.4.9 (2026-10-20, sesión del servidor)
- DYMO compartida: la cola ya no se atora (commit `7564a21`, producción en 1.4.9).

## v1.4.7–v1.4.8 (2026-10-19, Claude Code)
- v1.4.7: consumo de materiales por evento (R1/R2 programadas, R3 asignada, gabinete colocado); migración `migr_consumo_146` + tabla `inv_tqtr_consumo_base` (solo desde hoy); `consumir_por_evento` serializado.
- v1.4.8: criterio único de «programada» (`db._R1R2_PROGRAMADAS`, `T.programada`/`T.conFw`); reporte por fecha corregido; STM32 y programación por lote notifican la tarjeta.
- Evidencia: suites de inventario, programación, emparejado, DYMO, admin y API OK (test_correo_excel solo falla en conjunto, preexistente; pasa aislado). Docker local 1.4.8 healthy con la BD de producción 1.4.6 del 2026-10-19 (migración: base placas 34, r3 26, gabinete 19). Sin prueba física.
- Pendiente de decisión: «Pendientes» de MAC y firmware solo miran MAC; OTA migration_required queda verified sin guardar firmware; vista de estado R2 por versión.

## v1.4.5–v1.4.6 (2026-10-19, Claude Code)
- v1.4.5: zona «Cable R3» en Etiquetas DYMO (TQT: 0000 / R3: 0000), parámetro `r3` en `/api/dymo/cable/*` y DYMO compartida.
- v1.4.6: impresión automática del cable R3 en la DYMO compartida al asignar una R3 (`app/services/cable_r3_auto.py`, gancho en `_notificar_tarjeta`), interruptor en Administración › Resumen (apagado por defecto). Crea la tabla `dymo_cable_r3_hechas` sola.
- Evidencia: 89 pruebas Python OK (test_cable_r3_auto, test_dymo_cable, test_dymo_remoto, test_dymo, test_admin, test_api, test_qa_version_hoy); Docker local 1.4.6 healthy. Sin prueba física con la Raspberry ni revisión visual en navegador.
- Pendiente: desplegar 1.4.4→1.4.6 en producción, activar el interruptor y probar una asignación real de R3.

## Avance reportado
Desplegada1.4.3 autorizada porusuario enOrangePi /home/orangepi/escanertqt commit11cc0585dc430208d1c1f2e83f3dd423e8badacf. Fastforward desde76d71a1 y recreate solo servicio tqt con servidor/compose.yml. Datos/volumenes/tunel conservados. Loginpublico confirma1.4.3 y apihealthOK.

## Siguiente paso
Revisar operacion de puente BLE Windows por usuario en produccion; pruebas fisicas previas locales14/14 no repetidas. UART28/99 lineas corruptas pendiente diagnostico. Previewlocal no reiniciado. Android/Skytec pendientes.

## Evidencia
Sin trabajos activos antes de despliegue; respaldo SQLite predeploy_1.4.3_20261016_134402.db en /backups servidor. ContenedorAPP_VERSION1.4.3 y arranqueOK; httpsinventariotqt.site/login muestra1.4.3, apihealthok. 502 transitorio durante arranque resuelto; recursosstatic protegidos requieren sesion. Pruebas previas24Python14JSUIpass.

## Nota operativa R2 (2026-10-16)

Documentado en R2_ALTA_GENERICA_42.md el inicio de programar_base.ps1 con ExecutionPolicy Bypass limitado al proceso. El usuario reporto bloqueo de PowerShell; no confirmo nueva grabacion. Se mantiene BIN generico4.0 fijo seguido de alta y OTA web con datos/credencial por unidad; evidencia previa0067 FW4.2. Sin cambios de codigo ni nueva prueba fisica.
