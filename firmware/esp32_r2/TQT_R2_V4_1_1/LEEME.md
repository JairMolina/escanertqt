# R2 FW 4.1.1 · OTA rápida

Plantilla sin credenciales de unidad. La web asigna nombre y clave privada al instalar por serial; OTA conserva la identidad y valida el firmware cifrado antes de activarlo.

Compilar con `compilar.ps1`, Arduino ESP32 3.3.12 y ESP32 DOIT DevKit V1 (4 MB, particiones OTA predeterminadas). Subir el `merged.bin` completo o el HEX exportado, no el BIN de aplicación aislado.

Transporte: MTU solicitado 517, hasta 500 bytes útiles por paquete, Write Without Response, ventana de ocho paquetes y notificación binaria de estado `<BIIB` (estado, offset, total, error). La lectura JSON sigue disponible para clientes anteriores. Mantiene AES-CTR, HMAC, validación de identidad/hash y comprobación del arranque.

Esta fuente corresponde a la prueba física aislada 0069 documentada en `docs/ESP32_R2_OTA_PRUEBA_AISLADA.md`. El binario base publicado es una plantilla con nombre 0000 y clave vacía; no contiene datos de esa unidad.
