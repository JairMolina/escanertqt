# Estado de Codex: TQT-Web

Actualizado: 2026-10-28. Código desplegado: `985d0d367de308dc1d20badd761793e530cb689b`, web 1.4.63.

## Estado vigente

Último main comparado con Orange Pi; se aplicó el único commit pendiente d63546b → 985d0d3, ajuste móvil de estrellas del portal. Servicio tqt saludable, salud pública/interna correcta y archivos públicos iguales al código probado. Inventario e historiales conservados. No se cambió APP_VERSION ni firmware. Evidencia y respaldo: docs/DESPLIEGUE_1.4.63_20261028.md.

Main incluye los avances de otros colaboradores: Pruebas automáticas por cuenta y Raspberry, exclusión de Raspberry de bancos normales, agentes/puentes BLE por cuenta y avisos de actualización, sincronización Skytec y rediseño de Diagrama. No volver a desplegar 1.4.49 ni el checkout documental antiguo. Las notas anteriores de despliegue 1.4.51 pendiente están superadas por esta comprobación de producción; las pruebas físicas y la configuración de Skytec no se revalidaron hoy.

## Claude v1.4.73 (main, sin desplegar)

Agente: `$OK` antes de registrar la línea, outbox en WAL/synchronous=NORMAL y eventos en lotes (hasta 50 por POST); espera de R2 de 32 a 60 s. Causa: en el ciclo 2 la Raspberry tardaba 1–2 s por ACK → reintentos de la R1 y cola de mensajes → «cerrado» llegó 33 s tarde. Log del agente con estilo de terminal.

## Claude v1.4.72 (main 8227cf6)

Etapa 12: hasta 3 escaneos BLE y búsqueda de la R2 por MACR aunque anuncie sin nombre (engine.connect_r2). Causa típica: un celular conectado a la R2 hace que deje de anunciarse.

## Claude v1.4.71 (main 08ca716; incluye 1.4.68–1.4.70)

Cuenta atrás de la pausa entre ciclos en el panel y la barra fija (solo pruebas_auto.js/.html/.css).

## Claude v1.4.70

Solo campañas: ciclo con 14 etapas aprobadas cuyo único problema son reintentos de ACK = aprobado_con_advertencias (`resultado_ciclo`); la certificación de Pruebas TQT no cambia.

## Claude v1.4.69

Controles manuales de Pruebas TQT: Bluetooth sin depender del serial (validacion_web.bleManual) y mensajes separados (serialOut / manualOut).

## Claude v1.4.68

Historial de Pruebas automáticas con el motivo de cada fallo (etapa y detalle, desde `source_report`) y `DELETE /api/pruebas-auto/campanas/{id}`. El ciclo de prod del 2026-10-28 14:32 falló en la etapa 5: el sensor de apertura (OFF) nunca llegó a 1 tras PPON (TQT=2 con ON0/OFF0) → hardware (alineación del imán y sensor CS1-U o carrera del actuador).

## Claude v1.4.67

- **Campañas:** un ciclo no verificado ya no corta la campaña, salvo con «detener en falla» o 3 ciclos seguidos.
- **Motor:** espera hasta 150 s a que R1 limpie el err viejo antes de R2.
- **Página:**
  - «Liberar» sin salir de la página;
  - historial agrupado por tarjeta y plegable, con buscador;
  - «Limpiar» en el log del agente.

AGENT 1.4.67. Evidencia: test_pruebas_auto 22 OK y test_engine_fake 5 OK; el caso del err viejo y el de 3 no verificados tienen pruebas.

## Claude v1.4.66 (main, sin desplegar)

Rediseño de /pruebas-automaticas con el lenguaje visual de Pruebas TQT: preparar el banco, campaña en curso con 14 etapas en 4 bloques, sensores y botones de detener, registro en vivo e historial con «Repetir». Solo pruebas_auto.html, .css y .js. Chip de canal por etapa (terminal serial / Bluetooth → R1/R2) y barra fija con Detener. Evidencia: unittest 41 OK y node --check; capturas con API simulada; sin probar con la Raspberry real.

## Claude v1.4.65 (main 233d0f3, sin desplegar)

R2 BLE: la posición debe sostenerse 1.5 s seguidos con un Status nuevo antes de aprobar; si rebota, queda «AVISO SENSOR» en el log. Antes se tomaba la trama en caché, que podía ser la del rebote, y fallaba con «no se mantuvo estable». Pruebas automáticas: panel «En curso», `GET /campanas/{id}/vivo` y `detener_ahora`. AGENT_VERSION 1.4.65.

## Claude v1.4.64 (main 0575adb, desplegada)

Rediseño de /monitor#/validacion integrado en main por Claude, que supera el borrador `codex/validacion-paneles-20261027`: no hay que retomarlo. Incluye:
- **Pantalla:** franja «Tarjeta en prueba», conexiones compactas, 14 etapas en 4 bloques plegables y estado de la ejecución. El resumen y los 29 sensores S29 conservan su marcado de 1.4.63; los sensores van a todo lo ancho.
- **Selección de tarjeta:** modal «Elige la tarjeta en prueba» con el lote de la consola y selección de una o varias; el escaneo del celular responde a la consola.
- **Puente Bluetooth:**
  - instalador único `.cmd`, oculto y con avance en la página (`install-progress`, `installer/{id}/estado`);
  - misma estación al reinstalar, con tokens previos válidos (`stm32_stations.tokens_previos`);
  - autoactualización con `claim.agent_version` y `/api/stm32/agent/tests/package`;
  - «Elegir dispositivo» (`/web/ble/commands` operation `scan`; connect sigue exigiendo la MAC del inventario);
  - aviso al entrar para instalar o actualizar (`sin_agente`).
- **Pruebas automáticas:** paso 1 con comando de un solo uso (`curl …/api/stm32/agent/tests/instalar/<codigo>.sh | sh`, 15 min, en memoria: un solo worker), `instalador_linux.py`, `GET /api/pruebas-auto/agente/instalacion` y autoactualización también en Linux.
- **Inventario TQTR:** relevador único R1+R2+R3 y sensores magnéticos incluidos en el actuador (`_migrar_1464`).
- **Versiones:** AGENT_VERSION 1.4.64.

Evidencia: unittest 117 OK (pruebas_auto, native_ble, test_station_web, qa_version, inventario_tqtr, stm32) y `sec_validacion_ui.cjs` OK. En `station/test_station/tests` solo falla `test_reporting`, que ya fallaba. El instalador .cmd pasa el parser de PowerShell y el .sh pasa `sh -n`, con simulación de extracción. Probado en Docker local con la BD de producción 1.4.63; el puente Bluetooth se instaló y conectó en la laptop del usuario.

Pendiente:
- desplegar;
- reinstalar una vez los puentes 1.4.56 y la Raspberry con el comando nuevo;
- probar «Elegir dispositivo» y una campaña con hardware real.

## Pendiente de Pruebas TQT

El usuario autorizó adaptar únicamente cinco bloques de /monitor#/validacion: conexiones compactas Serial/Bluetooth, controles manuales plegables ON/OFF, las 14 etapas originales agrupadas 1–2 / 3–6 / 7–11 / 12–14, barra de tarjeta con datos/historial y selector modal real por número/nombre/QR. Conservar motor, temporización, comandos, Bluetooth Windows por MAC, resultado/S29/impresión y confirmación de identidad real.

Borrador incompleto y no probado en `work/tqt-fw-beta-20261026`, rama `codex/validacion-paneles-20261027`, archivo modificado `app/static/js/sec_validacion.js`. No se desplegó ni se subió como implementación final. Retomar sobre el main más reciente conservando los cambios de agentes por cuenta, Raspberry, avisos de versión y Skytec. Faltan finalizar lógica/estilos de nuevos paneles, regresiones del motor y Playwright. No ejecutar banco físico sin coordinar tarjeta y autorización vigente para esa prueba.

## Evidencia actual

13 Python PASS (portal/permisos/versionado), Node syntax y Compose QA correctos; Playwright escritorio1440/móvil390 con secuencia de crédito, Escape, ocho módulos, sin errores JS/desborde. Comprobación pública móvil y hashes JS/CSS coincidentes. Backup íntegro, cero actividad antes de recrear, cero IDs anteriores perdidos y cero cambios en inventario. Solo tqt recreado, Cloudflared intacto.

Checkout de este despliegue: `work/tqt-deploy-20261028`, rama `codex/despliegue-1-4-63-20261028`. El checkout CM registrado `work/escanertqt_publish` tiene cambios documentales propios y se conserva; no usarlo como código más reciente. Capacidades: CM estado/versión/checkpoint/memoria y ECC verificación/E2E.
