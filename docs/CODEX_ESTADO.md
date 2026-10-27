# Estado de Codex: TQT-Web

Actualizado: 2026-10-27
Commit de código de referencia: 23a7d8da8ae35030497b296a0488310dceec9b31.

## Avance reportado

Web1.4.47 publicada en main y desplegada sobre main/producción1.4.46/04676c5. Nuestro cambio de agentes0ca9d86 ya estaba integrado, sin repetir ni sobrescribir funciones de main. Cuenta web como propietario de agente; operator identifica a quien inicia cada trabajo. Servidor con20registros físicos previamente revocados,0vigentes,1banco lógico. Limpieza local completada:4procesos detenidos,6arranques retirados,7carpetas en respaldo privado local;LocalWeb/R2 preservados. No se creó un agente nuevo ni se programó hardware. Ver docs/DESPLIEGUE_1.4.47.md.

## Siguiente paso

Recargar web y, cuando se vaya a programar, instalar solo un agente nuevo usando la cuenta web. Banco físico y aprobación humana de FW4.4 beta siguen pendientes. No repetir la limpieza de los20registros ya revocados. Para trabajos futuros partir de origin/main y comprobar servidor antes de modificarlo. Checkout activo: work/tqt-fw-beta-20261026,rama codex/cierre-agentes-20261027;checkout CM registrado conserva cambios documentales sin reset ni stash.

## Evidencia

122Python aisladas+9Node+15gruposPlaywrightPASS,0JSerrors,móvil390sin desborde,ComposeQA/diffcorrectos. Backup /backups/predeploy_1.4.47_20261027_092049.db,integrity_checkok,SHA256d51ad4340fb1e321341685fb46e7b4ce067e2167ec6ef37b0551403b7fa44b11. Producción tqt runninghealthy,APP_VERSION1.4.47,quick_checkok,health interno/público ok:true,loginHTTP200/1.4.47. Antes/después coinciden94trabajosSTM32,50pruebas,239comandos,446PCB,100tarjetas,1883escaneos,20agentesrevocados,0vigentes,1bancoweb. Cloudflared sin reiniciar. CMcheckpoint/memoria y ECCbackend/seguridad/verificación;sin secretos o bases en Git/CM.
