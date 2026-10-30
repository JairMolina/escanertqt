# Despliegue 1.4.76 — 2026-10-29

## Resultado

El usuario revisó el QA local y autorizó subir, guardar y desplegar la versión. GitHub main y la rama `codex/lotes-aislamiento-20261029` recibieron el cierre probado `b0d8c64` (implementación `deac73e`). Orange Pi pasó mediante fast-forward de `f0fac7d` / 1.4.74 a `b0d8c64` / 1.4.76.

Incluye el aislamiento de lotes y «Todos los lotes», además de la portada 1.4.75 de main que se conservó íntegra al integrar. Evidencia local: docs/LOTES_ALCANCE_LOCAL.md; 402 Python, 13+3 escenarios Playwright, motor Node y prueba UI PASS.

## Acceso y campaña existente

La conexión directa desde Mini PC no tenía la identidad SSH de administración. Tras autorización específica para consultar la ficha de TQT-OrangePi, se usó el salto habitual desde Windows: `ssh -J MiniPc orangepi@192.168.4.70`, con la clave y verificación de host existentes. Host confirmado `orangepizero3`. La clave restringida de respaldos no se usó para administración.

La consulta previa encontró «Prueba7», campaña `60afa69e006dc4a5a5e50b75`, activa con 1 de 16 ciclos guardado y aprobado, sin ciclo en curso. El usuario autorizó expresamente **pausar, desplegar y reanudar esa misma campaña**. Se pausó con el servicio existente; después del despliegue y de comprobar salud/datos se reanudó, quedando `activa`, con el primer ciclo conservado. No se creó una campaña ni se ejecutó una rutina de prueba adicional desde Codex.

## Respaldo y aplicación

- Checkout `/home/orangepi/escanertqt`, rama main limpia antes del cambio.
- Compose existente `/home/orangepi/escanertqt/servidor/compose.yml`, servicio `tqt`, imagen `escaner-tqt:web`, código montado en lectura. Dependencias, Dockerfile y Compose no cambiaron entre la versión instalada y la aprobada.
- El plan CM no se pudo obtener porque `cm` no está en el PATH de Mini PC. Se usó el procedimiento Compose ya documentado de Orange Pi, revisando primero configuración, puertos, montajes y servicios.
- Respaldo en el propio servidor: `/backups/predeploy_1.4.76_20261030_001647.db` (nombre con fecha UTC; en México aún 29 de octubre).
- SHA256: `bfc98b7295fa330392a7d5095bc48734e35b884ae5eddf0b2aa63585e5be289e`; `integrity_check=ok`.
- Preflight repetido inmediatamente antes de aplicar: cero trabajos STM32, pruebas, comandos, intentos R2, OTA recientes y campañas activas; Prueba7 seguía pausada.
- Solo `tqt` se recreó con `up -d --no-deps --no-build --force-recreate tqt`. Se reutilizó la imagen existente con el código verificado. Cloudflared conservó su ID y no se reinició; puertos y origen del túnel se conservaron.

## Verificación posterior, antes de reanudar

Contenedor `escanertqt-tqt-1` en estado `healthy`. Salud interna `ok:true`, APP_VERSION 1.4.76 y SQLite `quick_check=ok`. Login público HTTP 200 muestra 1.4.76; `https://inventariotqt.site/api/health` devuelve `ok:true`.

33 archivos modificados de app/station montados dentro del contenedor coinciden por SHA256 con Git. `common.js`: `177ef0d345f76acd1ee2d65d10e92736e397a73d81e5e16c455e6e22032940cd`.

| Tabla | Antes | Después |
|---|---:|---:|
| pcb_inventario | 446 | 446 |
| tarjetas_produccion | 100 | 100 |
| escaneos | 2531 | 2531 |
| stm32_jobs | 223 | 223 |
| tqt_test_runs | 151 | 151 |
| tqt_test_commands | 655 | 655 |
| esp32_ota_jobs | 93 | 93 |
| tqt_resistencia | 8 | 8 |

Comparación por `EXCEPT`: cero IDs anteriores faltantes en las ocho tablas; cero filas previas de tarjetas/PCB modificadas. La campaña conservó su primer ciclo. Los conteos son una foto previa a reanudar: la operación normal puede generar nuevos registros después.

Consulta adicional con conexión SQLite **solo lectura** y el contexto real de lotes:

- 2026-09: 100 tarjetas, 229 PCB, todas pertenecientes al lote elegido.
- 2025-04-04: 0 tarjetas, 144 PCB, todas pertenecientes al lote elegido.
- Todos: 100 tarjetas, 446 PCB. Las 73 PCB antiguas sin lote se ven en Todos; no se reasignaron datos por inferencia.

## Continuidad

Recargar con Ctrl+F5 y revisar `https://inventariotqt.site/monitor#/programacion`. El selector conserva su elección; usar «Todos los lotes» para inventario sin lote o revisión global. Recepción y Excel mensual requieren elegir un lote concreto.

Guardar este cierre junto a CODEX_ESTADO, HISTORIAL y MEMORIA en Git; replicar únicamente documentación curada al espejo CM y sincronizar el índice central. Backups, claves y datos reales permanecen fuera de Git y del índice. Prueba7 continúa con su configuración original; no se afirma haber completado sus 16 ciclos.
