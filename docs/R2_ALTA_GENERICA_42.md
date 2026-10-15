# Alta genérica R2 y actualización 4.2

## Flujo

1. Instalar por USB la base genérica 4.0, idéntica para todas las unidades. Anuncia `TQT_R2_V30_XXXX`, HW 3.0, sin clave de unidad.
2. En Programación, elegir la R2 del inventario y el firmware 4.2. Una tarjeta sin programación registrada puede iniciar Bluetooth; una versión instalada conocida inferior a 4.0 requiere USB.
3. Elegir el dispositivo XXXX. El servidor valida la base, el HW y el arranque, reserva la credencial y emite un ticket de asignación firmado y cifrado para esa conexión y MAC.
4. La base verifica el ticket y conserva el nombre y la credencial en NVS. Este paso no marca la tarjeta como programada en inventario.
5. La web envía el 4.2 personalizado con el nombre seleccionado. Tras reiniciar se verifican nombre, MAC, HW, FW, imagen, credencial y partición antes de guardar el resultado.

La primera asociación requiere elegir físicamente la tarjeta correcta. El esquema no equivale a un certificado de fábrica del dispositivo. Si se interrumpe el alta, la misma unidad puede retomar con una conexión nueva y la credencial ya reservada; no se reemplaza silenciosamente su identidad por otra MAC.

## Firmware y claves

Los proyectos nuevos son `firmware/esp32_r2/TQT_R2_BASE_V4_0_GENERIC` y `firmware/esp32_r2/TQT_R2_V4_2`. Las versiones anteriores se conservan. En ambos proyectos la escritura de eFuses está desactivada expresamente por el usuario. Los comandos y salidas de operación originales se conservan.

La base contiene una clave pública de confianza. La clave privada del emisor vive en el volumen persistente del servidor, `/data/r2_enrollment_signing.pem`, configurable mediante `TQT_R2_ENROLL_SIGNING_KEY`. Debe respaldarse fuera de Git y trasladarse de forma segura al desplegar; una clave diferente no corresponde a la base ya grabada.

El ticket de 286 bytes usa P256 ECDH, AES-256-GCM y firma ECDSA-SHA256. Liga la clave efímera del dispositivo, nonce y MAC. Los secretos de unidad no se envían en texto claro al navegador ni se incluyen en la plantilla. El mensaje INFO genérico omite campos HMAC y partición que aún no aplican, para respetar el límite GATT de 512 bytes; después del alta se usa INFO autenticado normal.

## Validación y estado físico

Entorno local aislado: web 1.3.86 en `http://127.0.0.1:18082`, sin modificar producción. Compilaciones nativas con Arduino ESP32 3.3.12, placa `esp32doit-devkit-v1`. Pruebas de alta verifican firma, cifrado, rechazo de identidad/hash/nonce y recuperación. Las doce pruebas de transporte cubren alta seguida de OTA con tamaños de paquete 16 y 500, cancelación, recuperación del resultado, conexión obsoleta tras reinicio, transición de formato de nombre y desconexión durante el descubrimiento GATT del segundo paso.

R2 0067: el 15 de octubre de 2026 se grabó por COM4 la primera compilación genérica, con hash de escritura verificado. MAC de silicio `8C:8C:29:C3:D7:E8`, Bluetooth `8C:8C:29:C3:D7:EA`. La lectura Bluetooth detectó INFO vacío por exceder 512 bytes. Se corrigió el formato, se agregó una prueba de tamaño y se volvió a grabar con hash verificado. La lectura física posterior confirmó `TQT_R2_V30_XXXX`, FW 4.0, HW 3.0, arranque válido, alta habilitada, paquete de 500 bytes y hash de aplicación `bb88893209fa8078d351af70544db2008156c0de2e24e3472769dda2b8486701`. La conexión de comprobación fue de solo lectura y quedó cerrada. Imagen genérica normalizada SHA256 `a731d5115a24b7f718090a1ebbfe4aa46070195090ffd7abbd290955cbedcaec`.

El usuario completó el alta y envío OTA 4.2 en Chrome. La web no observó la desconexión al reiniciar y dejó el resultado pendiente. La lectura Bluetooth independiente confirmó FW 4.2, HW 3.0, nombre heredado `TQT_R2_V30_0067`, partición nueva 0x150000 y hash de aplicación `0dc9488c37c1cd60991f32897f2d615ab2da0d3c5b5a14579f96ef77e8c2c222`. Esa lectura real se envió al endpoint normal `/api/esp32/ota/result/0f6c9342ca68457ff47dc903`: el servidor validó HMAC, imagen, nombre, MAC y nuevo arranque. Inventario, alta y trabajo OTA quedaron verificados con FW 4.2 y MAC `8C:8C:29:C3:D7:EA`.

Se corrigió la detección de reinicio: si el navegador mantiene `connected=true`, se cierra GATT y se vuelve a abrir; la confirmación sigue requiriendo toda la evidencia criptográfica del nuevo arranque. No se da por exitosa una desconexión por sí sola.

No se han probado interrupciones de alimentación en esta unidad. Las simulaciones no sustituyen esas pruebas.

## Nombre exacto del inventario

Por petición del usuario, el FW 4.2 actualizado y las altas nuevas deben usar exactamente `pcb.nombre`, por ejemplo `TQT-R2-V30-0067`, sin convertir guiones a guiones bajos. La base genérica sigue anunciando `TQT_R2_V30_XXXX` antes del alta, para distinguir unidades nuevas. Una vez asignada, utiliza el nombre del inventario.

Los firmwares anteriores exigen conservar el nombre con guiones bajos al recibir una OTA. Cuando se elige el 4.2 nuevo desde una unidad con ese receptor antiguo, el servidor prepara primero una imagen de compatibilidad con el nombre heredado y la misma credencial. Su arranque se verifica, pero no confirma una programación final en inventario. La web continúa automáticamente con una segunda OTA que aplica el nombre exacto. El receptor nuevo admite únicamente el cambio de separadores para la misma identidad; número, HW, clave, firma e imagen siguen verificados. El cierre final exige el nombre exacto de la imagen autorizada. Una unidad nueva con la base actualizada llega directamente al nombre exacto en una OTA.

La primera fase de transición sí se completó físicamente en la 0067: trabajo `8ff1da75607b4d959b4dc454` verificado y lectura independiente con nombre `TQT_R2_V30_0067`, FW 4.2, HW 3.0, partición 0x10000, `name_format=2` y hash de aplicación `860e91765f971a975869262346ca8f87f0ce8689e2df7eaceef2fb3e92bdad84`. La web falló al abrir los servicios GATT para el segundo paso; todavía no había autorizado otro trabajo de firmware.

Se corrigió el ciclo de conexión en 1.3.86: la transición reutiliza la conexión que verificó la compatibilidad, sin desconectarla deliberadamente. Tanto la apertura de servicios y características como la lectura INFO se reintentan antes de autorizar un nuevo trabajo si GATT se desconecta. La prueba de regresión reproduce ese fallo justo al entrar al segundo paso y comprueba que no se creen trabajos ni grabaciones adicionales. Playwright confirmó versión 1.3.86, recurso OTA con caché 1386, botón habilitado y ausencia de errores JS.

La transición se completó físicamente desde la web 1.3.86: el usuario obtuvo `OTA verificada ✓ · FW 4.2`. El trabajo final `9a5e54b583bff4ea0a427c64` quedó verificado. Una lectura Bluetooth independiente y de solo lectura confirmó nombre exacto `TQT-R2-V30-0067`, FW 4.2, HW 3.0, MAC `8C:8C:29:C3:D7:EA`, `name_format=2`, arranque válido, partición nueva 0x150000 y hash de aplicación `78d28604f878255f8f5ff7e937d302becda538748bdd65ae02f6e7921966554a`.

Esa lectura fresca se validó con la credencial guardada mediante el verificador HMAC normal y se contrastó con el trabajo autorizado, la imagen personalizada del catálogo y el estado de programación. Los tres coinciden. Hay un único registro de la R2 0067, método `ble_ota`, FW/HW/MAC guardados y ningún trabajo OTA pendiente. La conexión de lectura quedó cerrada. No se necesitó otra grabación serial para completar la transición.

La prueba queda cerrada en el entorno local aislado. Producción no se desplegó. Antes de desplegar hay que conservar la clave privada del emisor y las credenciales de las unidades fuera de Git; la base pública debe corresponder al emisor persistente del servidor. La ruta directa de una unidad nueva con la última base que ya asigna guiones está cubierta por compilación y pruebas de protocolo; la prueba física documentada de la 0067 recorrió la base genérica inicial y la transición posterior.
