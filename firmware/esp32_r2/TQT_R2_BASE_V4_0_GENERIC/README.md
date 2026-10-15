# Base R2 4.0 genérica con OTA rápida

ESP32-WROOM-32E-N4, HW 3.0. La misma imagen se instala por USB en todas las tarjetas y anuncia `TQT_R2_V30_XXXX`. No contiene número de unidad ni secreto compartido. No escribe eFuses; los diagnósticos de VDD_SDIO se conservan.

Ejecutar `compilar.ps1` con Arduino ESP32 3.3.12 y placa `esp32doit-devkit-v1` para exportar BIN completo y HEX. El catálogo usa el archivo normalizado `../TQT_R2_BASE_V4_0_GENERIC.merged.bin`.

En la web, seleccionar la tarjeta del inventario y FW 4.2, pulsar Actualizar por Bluetooth y elegir el dispositivo XXXX. El alta utiliza ECDH, un ticket firmado y AES-GCM para guardar la identidad en NVS. Luego se instala el firmware personalizado y se confirma el inventario solamente tras verificar el nuevo arranque.

Después del alta el nombre coincide exactamente con el inventario: `TQT-R2-V30-0067`, por ejemplo. `XXXX` solo identifica la base sin asignar.

`enrollment_trust.h` contiene únicamente la clave pública del emisor. Su clave privada persistente debe conservarse fuera de Git y respaldarse de forma segura: `/data/r2_enrollment_signing.pem` o `TQT_R2_ENROLL_SIGNING_KEY`. El servidor debe usar la clave correspondiente a esta base; regenerarla impediría el alta de las bases existentes. No cambiar esta relación al desplegar.

Las pruebas físicas de una tarjeta y su conexión se documentan en el estado del proyecto; una compilación correcta no equivale a una grabación verificada.
