# Catálogo HEX de STM32 — v1.3.72

En Programación R1/R3, **Subir HEX** abre la validación y un formulario para registrar el firmware. Guardar firmware conserva la imagen en el sistema. **Firmware a programar** permite seleccionar una versión compatible antes de crear el trabajo; inicialmente se elige la versión numérica más alta (1.10 después de 1.9), con la subida más reciente para versiones iguales. Subir una versión antigua no sustituye la nueva ni elimina las anteriores.

R1 obtiene HW/FW del perfil interno compatible. Si el archivo contiene identidad de una tarjeta, la valida y elimina la página de identidad antes de guardarlo; cada programación añade los datos actuales de R1/R2 del inventario. R3 no contiene perfil interno: el operador confirma HW/FW. El nombre del archivo únicamente propone FW. El hash sirve para conservar y verificar la integridad de la imagen; no añade una firma al código.

## Persistencia y trabajos

Tabla adicional `stm32_firmwares` en la misma SQLite persistente que el inventario: identificador, tipo, HW/FW, nombre de archivo, hashes de origen/imagen, metadatos, HEX, fecha y operador. Solo se agregan registros; no hay endpoint para reemplazar o borrar imágenes. Se registran Movimientos `STM32_FIRMWARE_GUARDADO`. Los respaldos completos de la base incluyen el catálogo.

La migración conserva como entradas iniciales únicamente los firmware ya incluidos en la app: R1 4.3 y R3 1.0. No incorpora archivos de esta laptop automáticamente.

El trabajo contiene `firmware_id`, metadatos, HEX y hashes elegidos. Al tomarlo, el agente recibe exactamente esa imagen; el servidor revalida inventario contra ese firmware, no contra el nuevo predeterminado. Subir otro HEX mientras espera no modifica el trabajo. Firmware del inventario se actualiza solo tras lectura verificada; la cancelación mantiene su comportamiento.

API: GET/POST `/api/stm32/firmwares`, GET `/api/stm32/preview/{pcb_id}?firmware_id=...` y GET `/api/stm32/hex/{pcb_id}?firmware_id=...`. POST `/api/stm32/jobs` incluye `firmware_id`. Guardado sujeto a sesión, rol y protección de origen; el agente conserva su bearer separado. No se necesita cambiar el agente Windows para elegir firmware.

Validación: ASCII y límite 4 MB; registros Intel HEX y checksum; ausencia de solapamientos; Flash de aplicación y página reservada; vectores de arranque y entrada del STM32F103RET6; perfil y compatibilidad HW de R1, y metadata confirmada para R3. Un tipo/HW diferente se rechaza al preparar la placa. Nombre de archivo tratado como texto, no como ruta del servidor; ningún archivo subido se ejecuta en el servidor.

## Evidencia local

- 37 casos STM32/catálogo correctos: ocho casos nuevos cubren versiones numéricas, selección anterior, trabajo fijo ante nueva subida, duplicados, archivo inválido, identidad R1, hash alterado y autenticación/origen. 11 casos de Pruebas TQT correctos.
- Playwright: selector R3, formulario del HEX aportado con sugerencia FW 1.1/HW 3.0 y cancelación antes de Guardar; registro del HEX base ya existente devuelve duplicado, sin añadir registros. Catálogo conservado al recrear Docker; vista móvil de 390 px sin desbordamiento.
- El HEX V1.1 aportado se validó solo en lectura. **No se registró en el catálogo local ni en producción y no se programó ninguna tarjeta.** Las pruebas de nuevas versiones usaron HEX simulados en una base temporal sin red ni hardware.
- Revisiones ECC backend y seguridad aplicadas a estados, persistencia y entradas externas, con comprobaciones ejecutables de los límites de confianza. No se introdujeron procesos ni memoria ECC.

La prueba confirma el formato y el flujo de almacenamiento/selección; el funcionamiento físico de cada firmware sigue dependiendo de su prueba en la tarjeta correspondiente.

## Despliegue verificado

Aplicación 1.3.72 en inventariotqt.site, commit cdad30fa90f61b5a471cff394ff42f7c1bacb047. Respaldo previo de código y SQLite: /home/orangepi/escanertqt/servidor/data/respaldos/pre-tqt-1372-20261014T002844Z. Integridad verificada, contenedor saludable y API pública ok; inventario conserva 100 tarjetas y 300 PCB. Se reinició únicamente la web, sin cambiar Compose ni Cloudflare. Catálogo de producción al cierre: R1 4.3 y R3 1.0. No se cargó el HEX V1.1 de prueba.
