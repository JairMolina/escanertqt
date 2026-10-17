# Estado de Codex: TQT-Web

Actualizado: 2026-10-17 15:47 UTC
Commit de referencia: `2b91f0b2c3b4` (puede no incluir cambios pendientes)

## Avance reportado
Android0.1.0 y FW4.3 preparados en rama codex/tqt-android-ota-20261017; API online/offline, identidad P256, permisos por unidad/teléfono, outbox cifrado y página privada. Reutiliza inventario/catálogo/alta/OTA existentes. Producción conocida web1.4.3/11cc0585 intacta; base genérica4.0 y FW4.2 sin cambios.

## Siguiente paso
Pruebas físicas teléfono/R2 al final según usuario: BLE, OTA4.2 a4.3, sesión4.3 sin Internet, cortes y rollback. Definir custodia/firma APK estable y publicación privada con fecha/historial real. Despliegue productivo requiere autorización y respaldo/restauración verificables; no se realizó. Original interno excluido por cm files add conservado en adjunto.

## Evidencia
105/105 backend;32/32 JVM;7/7 instrumentadas reales API36(loginHTTPS/catálogo/navegación/Keystore/almacenamiento);Playwright1440/390;SDK apksigner/aapt verifica debug y rechaza unsigned;FW4.3 compila core3.3.11 app1159888B RAM43164B;nativecryptoPASS+4contrato. CM9MCP/0Gemini/5auxiliares;52.45%menos bytes en comparación delimitada, sin ahorro global demostrado.
