# Estado de Codex: TQT-Web

Actualizado: 2026-10-28. Código desplegado: `985d0d367de308dc1d20badd761793e530cb689b`, web 1.4.63.

## Estado vigente

Último main comparado con Orange Pi; se aplicó el único commit pendiente d63546b → 985d0d3, ajuste móvil de estrellas del portal. Servicio tqt saludable, salud pública/interna correcta y archivos públicos iguales al código probado. Inventario e historiales conservados. No se cambió APP_VERSION ni firmware. Evidencia y respaldo: docs/DESPLIEGUE_1.4.63_20261028.md.

Main incluye los avances de otros colaboradores: Pruebas automáticas por cuenta y Raspberry, exclusión de Raspberry de bancos normales, agentes/puentes BLE por cuenta y avisos de actualización, sincronización Skytec y rediseño de Diagrama. No volver a desplegar 1.4.49 ni el checkout documental antiguo. Las notas anteriores de despliegue 1.4.51 pendiente están superadas por esta comprobación de producción; las pruebas físicas y la configuración de Skytec no se revalidaron hoy.

## Claude v1.4.64 (main, sin desplegar)

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
