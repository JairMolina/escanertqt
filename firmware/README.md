# Firmware ESP32 (R1 y R2)

La programación de ESP32 se realiza por USB con Web Serial en `/monitor`,
mediante `esptool-js` incluido en la aplicación. Chrome/Edge de escritorio,
HTTPS o localhost, y adaptador USB–TTL autorizado en el navegador.

## R2: FW 4.0 y catálogo BIN / HEX

Fuente nueva: `esp32_r2/TQT_R2_V4_0`. Base compilada de runtime:
`esp32_r2/TQT_R2_V4_0.merged.bin`, HW 3.0 / FW 4.0, core ESP32 3.3.12.
Las fuentes anteriores V3.1.2 y V2.1 permanecen sin cambios.

En Programación > R2, **Subir BIN / HEX** analiza el perfil interno y permite
 guardar la imagen en la BD. El selector usa por defecto la versión numérica
más alta compatible y permite escoger una anterior. La web coloca el nombre
de la R2 elegida del inventario dentro del campo reservado; no recompila ni
modifica código, HW o FW por unidad. Verifica nombre/HW/FW/MAC al arrancar.

Para preparar otra versión, cambia HW/FW una sola vez en `tqt_profile.h`,
compila y ejecuta `compilar.ps1`. Sube el archivo completo `*.ino.merged.bin`
o el HEX ESP32 exportado por el script. `*.ino.bin` es solo la aplicación,
por lo que se rechaza. Un HEX STM32 no se usa para ESP32.

Detalles del formato, persistencia y API: [ESP32_R2_V4](../docs/ESP32_R2_V4.md).
El perfil plantilla 0000 se personaliza en la web antes de grabar. La imagen
base fue compilada/verificada; la prueba de hardware de V4.0 sigue pendiente.

## R1 y compatibilidad anterior

El ESP32 de R1 conserva la compilación por Arduino CLI desde
`esp32_r1/ESP32_BLE_SERIAL`, placa `esp32:esp32:esp32doit-devkit-v1`.
El endpoint `POST /api/firmware/compilar` mantiene también la compilación R2
V3.1.2 anterior y su personalización del nombre para clientes existentes.
El nuevo panel R2 utiliza el catálogo y no requiere Arduino CLI en el servidor.

El STM32 de R1/R3 usa su catálogo HEX y la estación Windows J-Link; es un
flujo independiente del ESP32.
