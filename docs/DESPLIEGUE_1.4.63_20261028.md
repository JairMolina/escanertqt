# Despliegue TQT-Web 1.4.63 — 2026-10-28

## Alcance verificado

Petición expresa del usuario: revisar el sistema, localizar la última actualización y desplegar desde ella. GitHub main: `985d0d367de308dc1d20badd761793e530cb689b`; Orange Pi estaba limpia en `d63546b735d9b7bbd755655eb305ee8b74cdcea9`, ambos APP_VERSION 1.4.63. El único delta pendiente era el ajuste móvil de las cinco estrellas del portal (`inicio.js`, `inicio.css`). Se mantiene la versión definida por el autor del cambio; este cierre no modifica código funcional.

Copia aislada: `work/tqt-deploy-20261028`, rama `codex/despliegue-1-4-63-20261028`. El borrador de rediseño de Pruebas TQT se conserva SIN DESPLEGAR en `work/tqt-fw-beta-20261026`, rama `codex/validacion-paneles-20261027`, con cambios no confirmados en `app/static/js/sec_validacion.js`. Está incompleto y no debe copiarse directamente sobre main. Antes de retomarlo, integrar los cambios recientes de propiedad de agentes, exclusión de Raspberry, avisos de versión y Skytec de main.

## Pruebas ejecutadas

- Docker QA independiente, puerto 127.0.0.1:18090, volumen `tqt-deploy-20261028-qa`, sin base ni credenciales de producción. Compose validado; sintaxis Node de inicio.js correcta.
- 13 pruebas Python: `test_portal_modulos` y `test_version_estaticos`, PASS con `_aislamiento` y red deshabilitada.
- Playwright en contextos propios: portal a 1440 y 390 px, ocho módulos, cinco estrellas y posiciones/tamaños esperados, secuencia abre el crédito y Escape cierra, sin desborde horizontal ni errores JavaScript. Las capturas se tomaron después de permitir la animación inicial; el área de toque de algunas estrellas alcanza aproximadamente 4.5 px del borde vacío de las fichas móviles, sin cubrir su texto ni acciones principales. No se modificó ese diseño en este despliegue.
- Comprobación pública Playwright a 390 px: HTTP 200, v1.4.63, posiciones móviles nuevas, ocho módulos, sin errores JavaScript ni desborde.
- SHA256 con finales LF de Git, contenedor y archivos públicos coinciden:
  - inicio.js: `10ed9fcff0340c1515263687afc8cc560b4a70ce661e05aba922fcd987bbb094`.
  - inicio.css: `62473ab1c78de5abf36d738d2357ce7ac7b1f67860834b00e7715f7a602a56ba`.

## Producción

Destino existente: `/home/orangepi/escanertqt`, acceso por MiniPc a Orange Pi, Compose `servidor/compose.yml`. CM deploy se consultó sin aplicar: no encontró la etiqueta v1.4.63 en su clon central. Se usó el procedimiento Compose existente de Orange Pi; no se trasladó el despliegue a Mini PC ni se crearon etiquetas para eludir esa diferencia.

Respaldo nuevo en el propio servidor: `/backups/predeploy_1.4.63_20261028_153631.db`, SHA256 `0d3958bfeea6eec401fd61cfa37b0f0a1a4d3043c74529b26de764ca051afa6a`, integrity_check `ok`. Fecha del nombre en UTC. Comprobación repetida inmediatamente antes del cambio: cero trabajos STM32, pruebas, comandos, intentos R2, OTA recientes o campañas activas.

Fast-forward d63546b → 985d0d3 y recreación exclusiva de `tqt`, reutilizando imagen y bind mounts existentes. Cloudflared no se reinició. Contenedor running/healthy; salud interna y pública `ok:true`; SQLite quick_check `ok`.

Conteos antes/después idénticos: 446 PCB, 100 tarjetas, 1929 escaneos, 98 trabajos STM32, 109 ejecuciones de pruebas, 643 comandos, 28 trabajos OTA y 2 campañas. Consulta EXCEPT de IDs anteriores: cero faltantes en las ocho tablas. Inventario PCB y tarjetas: cero filas anteriores modificadas. No se programaron tarjetas ni se ejecutaron movimientos, resets o conexiones físicas.

## Continuidad

Para revisar, recargar con Ctrl+F5 y abrir /inicio o /monitor. El rediseño de los cinco bloques de Pruebas TQT permanece pendiente, separado de la actualización de Git que se pidió desplegar hoy. No se afirma que ese rediseño esté terminado. Respaldo SQLite, secretos y originales adjuntos quedan fuera de Git/memoria. CM se usa para checkpoint y sincronización documental; ECC verificación/E2E para las comprobaciones anteriores.
