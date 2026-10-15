# R2 FW 4.2, HW 3.0

Plantilla para ESP32-WROOM-32E-N4 con OTA rápida. La web coloca el nombre de la R2 seleccionada y su credencial; HW y FW se obtienen del perfil del archivo. El nombre `0000` y la clave vacía identifican la plantilla, que no debe instalarse directamente en una unidad de producción.

El nombre final coincide exactamente con el inventario, por ejemplo `TQT-R2-V30-0067`. La web conserva la compatibilidad con receptores antiguos mediante una transición OTA con la misma MAC y credencial; solo confirma el resultado final tras verificar el nombre exacto.

Ejecutar `compilar.ps1` con Arduino ESP32 3.3.12 y placa `esp32doit-devkit-v1` para generar BIN completo y HEX. El catálogo utiliza `../TQT_R2_V4_2.merged.bin`. La primera instalación puede realizarse con la base genérica 4.0 XXXX por USB; después la web asigna la tarjeta e instala 4.2 por Bluetooth.

La escritura automática de eFuses está desactivada por decisión del usuario. Los comandos y salidas originales se conservan. El resultado de programación se registra solamente después de verificar identidad, firmware, HW y nuevo arranque.
