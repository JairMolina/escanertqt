# Programación R2 mediante firmware completo BIN/HEX (web 1.3.76)

R2 V4.0 incorpora un perfil de 92 bytes: marcador `TQT_R2_CFG_V1`, esquema 1,
HW, FW, nombre BLE y módulo. Las lecturas volátiles durante inicialización
evitan que el compilador convierta estos campos en literales separados.
El firmware original V3.1 se conserva y la compilación anterior por Arduino CLI
sigue disponible por su endpoint para compatibilidad; el nuevo panel R2 usa
el catálogo de imágenes completas y no compila por unidad.

`esp32_firmwares` guarda imágenes inmutables en la misma SQLite persistente del
inventario. Un respaldo completo de esa BD también respalda el catálogo. Cada
imagen se guarda con nombre plantilla 0000 para quitar la identidad de la unidad.
Duplicados por hash reutilizan el registro. El selector ordena versiones
numéricamente y filtra HW; un ID explícito mantiene la versión elegida.

API autenticada:
- GET `/api/esp32/firmwares?hw=30`
- POST `/api/esp32/firmwares/analizar` y `/firmwares`: filename + contenido base64.
- GET `/api/esp32/preview/{pcb_id}?firmware_id=...`
- POST `/api/esp32/bin/{pcb_id}?firmware_id=...` (requiere rol con permiso de programación).

Se aceptan merged.bin (máximo 4 MiB) e Intel HEX (máximo 12 MiB) que contengan
bootloader ESP32 clásico, tabla de particiones válida y aplicación en 0x10000
con SHA256 y perfil único. Se rechazan firmware sin perfil, application.bin,
otras familias ESP32, STM32, solapamientos, corrupción, contenido NVS y firmas
Secure Boot. No se generan ni eluden firmas criptográficas. SHA256 y checksum
son comprobaciones de integridad, no identificación del autor.

El nombre procede de `pcb.nombre` del inventario, normalizado de guiones a
guiones bajos. Se cambia solamente el campo de nombre y checksum/SHA256 de la
aplicación. Bootloader, particiones y código permanecen idénticos. HW/FW del
archivo son inmutables y deben corresponder al hardware registrado.

Tras el flasheo Web Serial se solicita INFO periódicamente hasta 8 segundos;
también se emite al arrancar. Se comparan nombre, HW, FW y MAC antes de guardar.
La API de resultado vuelve a validar identidad y versión elegida, y registra
firmware_id/hash en bitácora. Un resultado discordante no actualiza MAC/FW.

Base: fuente V3.1.2 aportada, SHA256
`e3bb4e47a7013485b1a369c9e6cbe36a0bcce595724d0e4899bfb4c5de9722b0`.
Objetivo ESP32-WROOM-32E-N4; eFuse/relés se conservan. El original realiza una
escritura eFuse irreversible VDD_SDIO=3.3 V al primer arranque si falta.
La compilación no acredita una validación eléctrica. No se programó hardware
durante la implementación. BIN base empaquetado es un recurso necesario de
runtime; los ELF, MAP y directorios build quedan fuera de Git.

Capacidades: CM actualizar/adjuntar/checkpoint y ECC HW/FW, C++, backend,
seguridad y verificación; ui-ux-pro-max para carga, selector y estado accesibles.
Pruebas y resultados concretos se registran en CODEX_ESTADO/HISTORIAL.

Desplegado el 14 de octubre de 2026 en Orange Pi, web **1.3.76**, commit de
aplicación `0e8bedcf115756fc137ebc93bf33e221575227de`, rama
`codex/esp32-r2-v4`. Conserva los tres commits de producción 1.3.73–1.3.75
(orden de botones/semáforo, rediseño de Pruebas y estación J-Link local), que
se incorporaron a esta misma rama de GitHub. `main` de GitHub sigue separado.

Servidor: `/home/orangepi/escanertqt/servidor/compose.yml`. Se añadió únicamente
`../firmware/esp32_r2:/app/firmware/esp32_r2:ro` y se recreó el servicio `tqt`,
sin reconstruir imagen ni reiniciar `cloudflared`. App/estación/R2 permanecen
montados en modo de solo lectura. La configuración del host continúa fuera de
este repositorio; aquí se conserva la trazabilidad del despliegue.

Respaldo SQLite verificado antes del despliegue:
`/home/orangepi/escanertqt/servidor/data/respaldos/pre-r2-v4-1376-20261014T200710Z.db`,
SHA256 `d665ad29f0d8064d45c7164f46bc2f895b0fc50909cf23f241c0c1fa31e9d424`.
Compose previo: `compose-pre-r2-1376-20261014T200829Z.yml` en esa misma carpeta.
El anterior commit del servidor `394487d7739e78cf94dcc92953754d9105f05c8b`
permanece en su rama main para recuperar el código si fuera necesario.

Comprobaciones: contenedor saludable; API local/pública 1.3.76; catálogo real
solo R2 4.0/HW3.0; imagen de R2 0013 preparada y validada por HTTPS sin grabarla;
HTML/JS con caché 1376. SQLite íntegra y mismos hashes de las 100 tarjetas,
300 PCB y 7 usuarios. Los firmwares simulados 4.9/4.10 se usaron exclusivamente
en la vista previa local y no se subieron a producción. Tras integrar se
repitieron 37 tests STM32/catalogo y 14 ESP32: todos correctos.

Pendiente: validación física de V4.0 en una R2 autorizada. Preparar o descargar
la imagen por API no certifica que se haya grabado una placa.
