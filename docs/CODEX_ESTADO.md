# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 21:27 UTC
Commit de referencia: `927b96555a9f` (puede no incluir cambios pendientes)

## Avance reportado
Web1.3.77 desplegada con autorizacion en Orange Pi desde GitHub codex/esp32-r2-ble-ota/927b965. API publica/local verificadas, catalogo R2 4.1OTA por defecto y4.0serial. R2 0069/PCB66: imagen privada preparada desde API y validada nativamente; credencial persistida y respaldada. No se programo hardware ni se abrio COM3.

## Siguiente paso
Usuario debe confirmar LISTO: R2 0069 banco libre en modo programacion COM3. La imagen esta en AppData Local TQT programming R2_0069_FW41 fuera de Git/Drive. Avisar al terminar para soltar BOOT y reiniciar; leer INFO real y registrar MAC/FW/capacidad; despues validar OTA Bluetooth con R1 desconectada y alimentacion normal. Produccion usa rama OTA, main sigue separado.

## Evidencia
Servicio tqt recreado exclusivamente, compose/cloudflared intactos; healthy y HTTPS2001.3.77. Inventario/usuarios hash identico100tarjetas/300PCB/7usuarios,SQLiteok. Respaldo pre-r2-ota-1377-20261014T212145Z.db SHA731beb94072b7c1424d279cff4c3eb708de98c3275f3d736d8ead906ae5fcf21; posterior con clave post-r2-ota-1377-20261014T212659Z.db SHA108f9db2a66f9d393a7087713cc776dd4b54e4bc02764006225dc671e55390da. Imagen0069FW4.1HW3.0,nombre correcto,checksum/SHA esptool validos; COM3 registrado sin abrir. Compilacion y78tests previos correctos; Playwright envio/cancelacion/recuperacion en DB sintetica. CM checkpoint/Git/memoria yECC HWFW/CPP/security/verification.
