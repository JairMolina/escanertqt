# R2 · Base 4.0 con OTA rápida

Instalación inicial por USB para ESP32-WROOM-32E-N4, Flash 4 MB. Conserva las funciones de R2 y el transporte rápido de 4.1.1. Después se instala el firmware vigente por BLE, sin volver a conectar pines.

Esta base es distinta del antiguo FW 4.0 sin OTA. Ambos se conservan: `base-R2-v40-ota` (schema 2, credencial por unidad y OTA) y `base-R2-v4` (schema 1). El número 4.0 por sí solo NO demuestra capacidad OTA.

Compilar con `compilar.ps1`, Arduino ESP32 3.3.12 / DOIT ESP32 DevKit V1, particiones OTA predeterminadas: app0 0x10000 y app1 0x150000, 0x140000 bytes cada una. Compilación validada con GCC 14.2.0 (2511): programa 1.135.459 bytes, RAM 42.220 bytes. El SDK incluye CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=1; la aplicación confirma el arranque tras sus comprobaciones y difiere la confirmación temprana de Arduino.

Subir el archivo completo `.merged.bin` o el HEX exportado. La web personaliza nombre y credencial; la plantilla contiene 0000 y clave vacía. No subir binarios personalizados al catálogo ni al repositorio.

AES-CTR, HMAC por unidad, SHA-256, comprobación de perfil, tamaño de partición, ventana de ocho paquetes, hasta 500 bytes por paquete y confirmación del nuevo arranque. Una transferencia incompleta conserva la partición activa; una imagen que no confirma su arranque usa el rollback del bootloader. Los ensayos de corte de alimentación y rollback físico se documentan por separado, nunca se presuponen por compilar.
