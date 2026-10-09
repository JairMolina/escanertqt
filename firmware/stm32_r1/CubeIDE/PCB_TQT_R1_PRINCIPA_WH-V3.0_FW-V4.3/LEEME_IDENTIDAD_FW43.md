# TQT R1 identidad Flash y firmware 4.3

Este proyecto permite compilar y programar desde STM32CubeIDE y J-Link sin internet. La identidad queda separada de la aplicación para generar después un HEX por tarjeta sin recompilar. La web y el agente Windows todavía no están implementados.

La identidad incluye **nombre, ID de R1, MAC asociada de R2, revisión HW y versión FW**, protegidos con CRC32. La versión FW se toma de la compilación: una identidad que diga 4.2 no puede utilizarse con esta aplicación 4.3.

## Uso manual en CubeIDE

1. Abrir/importar el proyecto `PCB_TQT_R1_PRINCIPA_WH-V3.0_FW-V4.3` desde su carpeta. Si ya está abierto, ejecutar Refresh (F5) y Project > Clean para regenerar los archivos de construcción.
2. Editar los cinco campos de `Core/Inc/Datos_editar.h`: nombre de R1, ID de la R2 asociada (cuatro dígitos, conservar ceros), MAC de esa R2, HW y FW de R1. Los números de R1 y R2 pueden ser diferentes. Los valores 0022/MAC incluidos son ejemplos originales; contrastarlos con inventario antes de una programación real.
3. La versión real FW está en `TQT_FW_VERSION`, dentro del mismo `Datos_editar.h`; cambiarla al liberar una nueva versión del código y recompilar. Ese valor se utiliza tanto en la identidad como en el perfil compilado. No editar el archivo generado. El perfil técnico MCU/HW aprobado vive en el módulo interno de identidad, no requiere edición por tarjeta.
4. Elegir Debug o Release y construir. CubeIDE ejecuta `tools/generate_identity.ps1` antes de compilar; calcula CRC y genera el registro. No requiere Python ni internet. Una validación fallida detiene el build: no programar archivos antiguos después de un error de compilación.
5. Se generan ELF, HEX y MAP en la carpeta de la configuración. Programar el **ELF/HEX completo** mediante J-Link en CubeIDE. La configuración Debug original ya selecciona J-Link/SWD; cerrar otros programas que estén ocupando esa sonda.
6. Comprobar las tramas existentes: `IDR`, `MACR`, `VER`, `HW`, `ID` y `MAC`. `VER` ahora sale de la identidad validada, y debe coincidir con el firmware compilado. `MAC` sigue siendo la MAC BLE del ESP32 de R1; `MACR` es la de R2.

Se incluyen HAL/CMSIS locales y rutas relativas. La copia 4.2 de producción no se modifica. El respaldo previo de 4.3 permite recuperar también la versión de desarrollo original.

## Formato binario esquema 2

Enteros little-endian, estructura empaquetada de **76 bytes**, situada exactamente en `0x0807F800`. La aplicación dispone de 510 KiB, la identidad de una página de 2 KiB y la RAM conserva 64 KiB. La identidad NO reside en EEPROM externa.

| Offset | Bytes | Campo |
|---:|---:|---|
| 0 | 4 | Magic `0x31545154` (bytes TQT1) |
| 4 | 2 | Esquema = 2 |
| 6 | 2 | Longitud = 76 |
| 8 | 23 | Nombre ASCII + NUL y relleno cero |
| 31 | 5 | ID de la R2 asociada, cuatro dígitos + NUL |
| 36 | 18 | MAC de R2 normalizada en mayúsculas + NUL |
| 54 | 8 | Revisión HW + NUL y relleno cero |
| 62 | 8 | **Versión FW** + NUL y relleno cero |
| 70 | 2 | Reservado = 0 |
| 72 | 4 | CRC32 ISO-HDLC de bytes 0..71 |

CRC: polinomio reflejado `0xEDB88320`, inicial y XOR final `0xFFFFFFFF`; vector `123456789` da `0xCBF43926`. CRC detecta corrupción accidental; no es una firma criptográfica.

El nombre debe ser `TQT_R1_V` + HW de R1 sin puntos + `_` + número de R1. `id_r`/`TQT_LOCAL_ID` es el número independiente de la R2 asociada. Ejemplo: nombre `TQT_R1_V30_0045`, ID_R `0032` y MAC de R2 número 0032. La trama conserva `ID=0045` para R1 e `IDR=0032` para R2; no es obligatorio que coincidan. El lector valida también esquema, tamaño, relleno, terminadores, MAC, HW y FW. La lectura es byte a byte desde dirección Flash `volatile`, hacia RAM; no utiliza las constantes de plantilla como identidad de ejecución.

La aplicación contiene además un perfil inmutable `.tqt_fwmeta` de 48 bytes, conservado por el linker: marcador `TQTFWM2\0`, MCU[16], FW[8], HW[8], esquema u16, tamaño u16, dirección u32. La herramienta HEX extrae FW de ese perfil y rechaza inconsistencias. Cambiar un ID no cambia los bytes del firmware base.

## EEPROM y fallos de identidad

Se conserva la estructura CONFIG_TQT y VERSION_ACTUAL=6, sus migraciones, contadores y comandos. Si la EEPROM ya contiene un nombre válido, se conserva; si está vacío/inválido se utiliza el nombre de fabricación de Flash. Para renombrar una tarjeta usada, utilizar el comando de nombre existente de forma explícita. No hacer un reset general solo para cambiar nombre, porque afecta otros datos. Nombre EEPROM y nombre de fabricación pueden ser diferentes por decisión del usuario.

Si falta identidad o es inválida, se mantienen los niveles OFF usados por el firmware original en PA4/PA5 (relés), PA6/PA7 (salidas), PA8 (ESP_ENABLE), PB12/PB5 y PC0/PC7. No se inicia el ADC, temporizadores de aplicación, watchdog ni acceso EEPROM; UART4 emite `TQT IDENTITY ERROR N - REPROGRAM HEX COMPLETO` a 115200 y el LED PC13 parpadea. El código queda también en `tqt_identity_fault` para CubeIDE: 1 formato, 2 CRC, 3 campos, 4 HW, 5 FW.

**Pendiente de laboratorio:** verificar con tarjeta real/esquema eléctrico que estos niveles OFF sean físicamente seguros, incluidos alimentación, reset y conexión del depurador. No se ha programado hardware ni se considera aprobado para producción. Si option bytes activan un watchdog por hardware, comprobar también su comportamiento; esta entrega no los modifica.

Un borrado total elimina la identidad. Recuperar programando el ELF/HEX completo con datos correctos. Un HEX base sin identidad sirve para personalización, no para arrancar una unidad. No modificar option bytes ni desproteger chips sin procedimiento separado. CubeMX puede regenerar el linker/configuración: revisar siempre la reserva y el paso previo después de regenerar.

## Herramienta offline y preparación futura para web

Python 3.9+ se usa **solo para las herramientas opcionales de HEX**, no en el flujo manual CubeIDE. Desde la carpeta del proyecto:

```powershell
python tools/tqt_hex.py inspeccionar --hex Debug/PCB_TQT_R1_PRINCIPA_WH-V3.0_FW-V4.3.hex
python tools/tqt_hex.py preparar-web --hex Debug/PCB_TQT_R1_PRINCIPA_WH-V3.0_FW-V4.3.hex --salida firmware_base.hex
python tools/tqt_hex.py personalizar --hex firmware_base.hex --nombre TQT_R1_V30_0023 --id 0023 --mac-r 8C:8C:29:C3:F4:47 --hw 3.0 --salida r1_0023.hex
python tools/tqt_hex.py validar --hex r1_0023.hex
python tools/test_tqt_hex.py
```

`--fw` es opcional al personalizar: se deriva del perfil compilado. Si se especifica, debe coincidir. El generador no sobrescribe fuentes/salidas, no abre J-Link/USB y crea un manifiesto JSON con HW/FW/MCU/esquema, identidad y hashes SHA-256 exactos. Rechaza corrupción, solapamientos, rango fuera de Flash, perfiles/vectores inválidos y datos incompatibles.

Subir posteriormente el HEX **compilado y aprobado**, no solamente main.c. El catálogo web deberá diferenciar firmware STM32 Principal y firmware ESP32 BLE de R1, sin confundir sus versiones. Mantener los nombres canónicos con guiones de inventario separados del nombre con guiones bajos del firmware y validar el vínculo a la MAC de R2.

## Estado de validación

Comprobados: builds reales CubeIDE Debug/Release, mapa de memoria, exportación HEX con identidad, coincidencia byte a byte entre generador PowerShell/HEX/Python, integridad y pruebas negativas de personalización. Las imágenes de ejemplo son material de revisión; no se grabaron tarjetas.

Pendientes: grabación/lectura J-Link, comprobar identidad personalizada en ejecución, salidas eléctricas, UART/BLE/ATrack, EEPROM nueva/existente/antigua y regresión de motores/sensores/comandos. Estos puntos requieren una R1 de laboratorio; la etapa A no se declara totalmente terminada hasta superar esas pruebas.
