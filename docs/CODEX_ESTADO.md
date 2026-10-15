# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 22:54 UTC
Commit de referencia: `abaee0b80ed0` (puede no incluir cambios pendientes)

## Avance reportado
Web 1.3.88 desplegada en Orange Pi desde abaee0b80ed0 sobre produccion ee604de. Conserva integracion R2 generica4.0/FW4.2/nombre exacto/OTA rapida, DYMO y JLink. Admite multiples bases recompiladas registradas. Agregado programar_base.ps1 para BIN fijo sin recompilar; cabeceras y copia publica ESP32_BLE_SERIAL actualizadas y verificadas sin secretos. Firmante correcto instalado y credencial0067 reservada selectivamente; no cambia estado programado ni MAC/FW productivos.

## Siguiente paso
Revisar con usuario fuentes FW4.2 y flujo de futuras versiones. No se grabo hardware en este avance. Arduino IDE genera build distinto: registrar su BIN completo una vez; produccion en masa puede usar BIN fijo con script. Nuevas identidades offline deben conservar credencial y registrarse antes de OTA web; no hay importador automatico.

## Evidencia
Despliegue abaee0b80ed048101bae048e028a642576f87cee healthy; API interna y publica inventariotqt.site version1.3.88, catalogo default base-R2-v42, generica4.0/R1 presentes. SQLite integrity OK y todas filas originales preservadas:100 tarjetas,300 PCB,7 usuarios,4 firmwares,7 claves,4 trabajos; solo nuevos firmwares y clave0067. Backup pre-r2-ota-1388-20261015T225310Z.db SHA d76464cb3d2f5027d605995f961ca4893433cb15ded8b6596ce7e1e8b912688f. 6 tests enrollment PASS; programar_base -Comprobar PASS sin abrir COM. Integracion previa140tests+12JS y Playwright escritorio/movil. Paquete26archivos con hashes comprobados.
