# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 15:40 UTC
Commit de referencia: `0396117f315b` (puede no incluir cambios pendientes)

## Avance reportado
Prueba OTA BLE rapida aislada EXITOSA en R20069. Trasserialtemporal41.1/hashFlash yreinicio confirmados, transferencia completa1135600bytes en71.758s a15.45KiBs,MTU517/bloques500/notificaciones951. Nuevoarranque HMAC/hash/FW/nonce/particion verificados. Sin cambiosweb/catalogo, sinreles. R2quedaFWtemporal4.1.1.

## Siguiente paso
Prueba solicitada completa. Esperar decisionusuario para integrar transporte rapido enweb/firmwaredefinitivo o restaurar4.1 original. NO integrarweb automaticamente: usuario pidio solo prueba. R20069real41.1 temporal; inventarioprodconservaregistro4.1 previo. Sin conexionesBLE/COM abiertas. Helper --restore disponible peroNOejecutado. Fuentes temporales outputs/r2_ble_probe; privados AppData TQT/programming/R2_0069_FW41.

## Evidencia
UsuarioLISTO_COM3;MACsilicio8C:8C:29:C3:D6:A4 coincide,esptool1201136bytes17.3s/hashFlashOK. Usuario confirmoBOOTlibre yreinicio. OTAself41.1 app1135600bytes,71.758s15.45KiBs,bloque500MTU517,951notificaciones,slot65536->1376256,appSHA2e21a2723f1ee914c0e876978a13a125ee52d1adbb70df2b9855504d0660b465,verifiedtrue enoutputs/r2_ble_probe/ota_fast_result.json. NativeArduino86%flash12%RAM;HMAC138/AESCTRofflineexactos;baseline24muestrasWRITE81ms/READ90msMTU247chunk180.14minantiguo eraETAno medicioncompleta;72sexcluyeconexion/preparacion/verificarboot;Chrome aun sin medirnuevo protocolo. ECC HWFW/CPP/verificacion;CMcheckpoint/memoria/Git.
