# Estado de Codex: TQT-Web

Actualizado: 2026-10-27 15:09 UTC
Commit de referencia: `1bb98bd4385d` (puede no incluir cambios pendientes)

## Avance reportado
Preparada web1.4.46 sobre origin/main1.4.45/1bb98bd. Comandos ya estaba integrado y produccion ejecuta1.4.45. Se actualizan version del servidor, README, CHANGELOG y prueba de version; se conservan catalogo beta/aprobado, lote persistente, agentes fijos y estado historico STM32. Usuario autoriza guardar en Git/memoria y desplegar. Ruta efectiva OrangePi192.168.4.70 por salto MiniPc, repo /home/orangepi/escanertqt, servicio tqt de servidor/compose.yml; acceso directo Tailscale no responde.

## Siguiente paso
Publicar1.4.46 en main y etiquetar; respaldo SQLite y nueva comprobacion sin trabajos activos; recrear solo servicio tqt y verificar salud/version publica. Banco fisico de FW4.4 beta sigue pendiente; no aprobar firmware ni programar hardware ni borrar agentes por esta actualizacion.

## Evidencia
115PythonPASS en Docker aislado;9NodePASS;16escenarios PlaywrightPASS en localhost18086 con clipboard real y capturas1440/1024/390 claro/oscuro sin JS/HTTPerrors. Compose/buildOK. Produccion1.4.45 cleanmain1bb98bd,0trabajosSTM32/test/BLE/R2 activos y PRAGMA quick_check=ok. Revisados imagen, puertos y montajes; cmdeployMiniPc no aplica al hostOrangePi, se usa procedimiento SSH/Docker vigente. ui-ux-pro-max/ECC verificacion reutilizadas; sin cambios funcionales de UI.
