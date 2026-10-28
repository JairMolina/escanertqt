# Estado de Codex: TQT-Web

Actualizado: 2026-10-28. Código desplegado: `985d0d367de308dc1d20badd761793e530cb689b`, web 1.4.63.

## Estado vigente

Último main comparado con Orange Pi; se aplicó el único commit pendiente d63546b → 985d0d3, ajuste móvil de estrellas del portal. Servicio tqt saludable, salud pública/interna correcta y archivos públicos iguales al código probado. Inventario e historiales conservados. No se cambió APP_VERSION ni firmware. Evidencia y respaldo: docs/DESPLIEGUE_1.4.63_20261028.md.

Main incluye los avances de otros colaboradores: Pruebas automáticas por cuenta y Raspberry, exclusión de Raspberry de bancos normales, agentes/puentes BLE por cuenta y avisos de actualización, sincronización Skytec y rediseño de Diagrama. No volver a desplegar 1.4.49 ni el checkout documental antiguo. Las notas anteriores de despliegue 1.4.51 pendiente están superadas por esta comprobación de producción; las pruebas físicas y la configuración de Skytec no se revalidaron hoy.

## Pendiente de Pruebas TQT

El usuario autorizó adaptar únicamente cinco bloques de /monitor#/validacion: conexiones compactas Serial/Bluetooth, controles manuales plegables ON/OFF, las 14 etapas originales agrupadas 1–2 / 3–6 / 7–11 / 12–14, barra de tarjeta con datos/historial y selector modal real por número/nombre/QR. Conservar motor, temporización, comandos, Bluetooth Windows por MAC, resultado/S29/impresión y confirmación de identidad real.

Borrador incompleto y no probado en `work/tqt-fw-beta-20261026`, rama `codex/validacion-paneles-20261027`, archivo modificado `app/static/js/sec_validacion.js`. No se desplegó ni se subió como implementación final. Retomar sobre el main más reciente conservando los cambios de agentes por cuenta, Raspberry, avisos de versión y Skytec. Faltan finalizar lógica/estilos de nuevos paneles, regresiones del motor y Playwright. No ejecutar banco físico sin coordinar tarjeta y autorización vigente para esa prueba.

## Evidencia actual

13 Python PASS (portal/permisos/versionado), Node syntax y Compose QA correctos; Playwright escritorio1440/móvil390 con secuencia de crédito, Escape, ocho módulos, sin errores JS/desborde. Comprobación pública móvil y hashes JS/CSS coincidentes. Backup íntegro, cero actividad antes de recrear, cero IDs anteriores perdidos y cero cambios en inventario. Solo tqt recreado, Cloudflared intacto.

Checkout de este despliegue: `work/tqt-deploy-20261028`, rama `codex/despliegue-1-4-63-20261028`. El checkout CM registrado `work/escanertqt_publish` tiene cambios documentales propios y se conserva; no usarlo como código más reciente. Capacidades: CM estado/versión/checkpoint/memoria y ECC verificación/E2E.
