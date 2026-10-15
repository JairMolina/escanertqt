# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 15:57 UTC
Commit de referencia: `2af724627e1c` (puede no incluir cambios pendientes)

## Avance reportado
Desplegada y verificada web 1.3.80 en Orange Pi desde commit 2af724627e1ccfbc7d2821c32f5fdec8cec8b10c, rama codex/r2-ota-rapida GitHub. Base 1.3.79 recuperada del servidor y preservada. R2 OTA rapida 500 bytes NR+notificaciones, ventana8, compatibilidad FW4.1, plantilla 4.1.1 predeterminada sin secretos. Pruebas: suite ESP32 35 OK mas OTA final15 OK (36 casos unicos), JS7 OK, Playwright R2 desktop/movil y R1 sin catalogo/OTA OK. API publica/local y contenedor healthy; SQLite integrity OK y hashes de todas las filas anteriores intactos; unica adicion base-R2-v411. Respaldo pre-r2-ota-1380-20261015T155624Z.db SHA256 2ae2b22d4d18b4210c130dfdb6dd48e413eb9db11ad5a5abde1217826909ef4c. CM y ECC-verification utilizados.

## Siguiente paso
Medir OTA desde Chrome/Edge real con R2 0069; conserva firmware temporal4.1.1 ya probado por cliente nativo, inventario4.1 hasta una verificacion real de la web. No se afirmo prueba fisica del navegador ni se tocaron COM3/reles. Actualizar desde rama codex/r2-ota-rapida con tracking reparado; main no se modifico.

## Evidencia
tests/test_esp32_ota.py; tests/esp32_ota_transport.cjs; docs/ESP32_R2_OTA_PRUEBA_AISLADA.md; despliegue publico 1.3.80 healthy
