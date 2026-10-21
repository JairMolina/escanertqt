# TQT R1 — tabla de comandos por firmware

Versión preparada: **FW4.4 / HW3.0**. La versión de firmware no es la versión de la web.

Sí/No se basa en fuentes revisadas: proyectos locales4.1/4.2, base4.3 integrada en la web y4.4 corregida. No se inventa la disponibilidad en4.0 o anteriores. Esta matriz documenta presencia en el código; no certifica pruebas físicas de todos los comandos.

## Cómo enviarlos

- **Serial/GPS:** escribir el comando respetando mayúsculas y terminar con CRLF (`\r\n`). Los ejemplos omiten ese fin de línea para facilitar su lectura.
- **Bluetooth:** enviar los cuatro caracteres exactos, sin CRLF. El módulo ESP32 los reenvía al STM32 con fin de línea. Los comandos largos `$SMSG=...` no se envían por este puente Bluetooth.
- `n` es un número y `c` un carácter: reemplazarlos por el valor deseado.
- Las consultas no implican un movimiento. Apertura/cierre, salidas, cambios de mapeo y reinicios requieren comprobar el estado físico antes de usarlos.

## Comandos seriales / GPS

| Comando | Para qué sirve | Valores / ejemplo | FW4.1 | FW4.2 | FW4.3 | FW4.4 |
|---|---|---|:---:|:---:|:---:|:---:|
| `$SMSG=ON` | Abre o desbloquea el perno. | `$SMSG=ON`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=OFF` | Cierra o bloquea el perno. | `$SMSG=OFF`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=Status` | Consulta estado general, versiones, entradas, salidas y datos asociados. | `$SMSG=Status`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=Status_Motor` | Consulta si el perno está abierto, cerrado o en otra posición detectada. | `$SMSG=Status_Motor`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=MAC` | Solicita la MAC del módulo Bluetooth y envía estado/configuración. | `$SMSG=MAC`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=Sensores:n` | Elige cómo termina el movimiento. | `$SMSG=Sensores:0`; 0 = sensores; 1 = trabajar por tiempo | Sí | Sí | Sí | Sí |
| `$SMSG=TIEMPO:n` | Añade segundos al límite de apertura Y cierre; usa el mismo valor para ambos. | `$SMSG=TIEMPO:5`; Entero de 0 a 10; límite nominal = 4 + n segundos | Sí | Sí | Sí | Sí |
| `$SMSG=PARO_C:n` | Activa o desactiva el paro por sobrecorriente. En FW4.4 inicia desactivado. | `$SMSG=PARO_C:1`; 0 = desactivar; 1 = activar | No | No | No | Sí |
| `$SMSG=PARO_C:?` | Consulta el estado de la protección del motor. | `$SMSG=PARO_C:?`; Respuesta PARO_C:0 o PARO_C:1 | No | No | No | Sí |
| `$SMSG=PROT_C:n` | Alias de PARO_C: realiza la misma función. | `$SMSG=PROT_C:1`; 0, 1 o ? | No | No | No | Sí |
| `$SMSG=MAP?` | Consulta el mapeo de las parejas de señales. | `$SMSG=MAP?`; Sin valor | No | Sí | Sí | Sí |
| `$SMSG=MAP_M1:n` | Cambia el mapeo del par 1. Solo se permite con el motor detenido. | `$SMSG=MAP_M1:1`; 0 = normal; 1 = intercambiado | No | Sí | Sí | Sí |
| `$SMSG=MAP_M2:n` | Cambia el mapeo del par 2. Solo se permite con el motor detenido. | `$SMSG=MAP_M2:1`; 0 = normal; 1 = intercambiado | No | Sí | Sí | Sí |
| `$SMSG=INT_1:n` | Configura o consulta la entrada 1. | `$SMSG=INT_1:3`; 0 = deshabilitar seguimiento; 1 o 2 = seguimiento habilitado; 3 = lectura puntual sin cambiar configuración | Sí | Sí | Sí | Sí |
| `$SMSG=INT_2:n` | Configura o consulta la entrada 2. | `$SMSG=INT_2:3`; 0 = deshabilitar seguimiento; 1 o 2 = seguimiento habilitado; 3 = lectura puntual sin cambiar configuración | Sí | Sí | Sí | Sí |
| `$SMSG=INT_3:n` | Configura o consulta la entrada 3. | `$SMSG=INT_3:3`; 0 = deshabilitar seguimiento; 1 o 2 = seguimiento habilitado; 3 = lectura puntual sin cambiar configuración | Sí | Sí | Sí | Sí |
| `$SMSG=OUT_1:n` | Controla la salida lógica 1. | `$SMSG=OUT_1:1`; 0 = nivel bajo; 1 = nivel alto | Sí | Sí | Sí | Sí |
| `$SMSG=OUT_2:n` | Controla la salida lógica 2. | `$SMSG=OUT_2:1`; 0 = nivel bajo; 1 = nivel alto | Sí | Sí | Sí | Sí |
| `$SMSG=Bloqueo:n` | Selecciona la salida del equipo GPS utilizada para bloqueo. | `$SMSG=Bloqueo:1`; 0 = ninguna; 1 a 4 = salida del equipo | Sí | Sí | Sí | Sí |
| `$SMSG=Nombre:texto` | Cambia el nombre de configuración/Bluetooth. La identidad fija del inventario continúa en Flash. | `$SMSG=Nombre:TQT_R1_V30_0023`; Hasta 22 caracteres; evitar cambiarlo sin revisar el inventario | Sí | Sí | Sí | Sí |
| `$SMSG=SPAS;c` | Cambia el carácter que separa campos del mensaje de estado. | `$SMSG=SPAS;\|`; Un carácter; distinto de SPAV, comillas y fin de línea | Sí | Sí | Sí | Sí |
| `$SMSG=SPAV;c` | Cambia el carácter que separa el nombre de un campo y su valor. | `$SMSG=SPAV;:`; Un carácter; distinto de SPAS, comillas y fin de línea | Sí | Sí | Sí | Sí |
| `$SMSG=DBG_TQT;n` | Activa o desactiva los mensajes de eventos TQT. No es la opción de compilación MODO_DEBUG. | `$SMSG=DBG_TQT;1`; 0 = desactivar; 1 = activar | Sí | Sí | Sí | Sí |
| `$SMSG=Reset` | Reinicia la tarjeta; no es un restablecimiento de fábrica. | `$SMSG=Reset`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=Reset_BLE` | Reinicia la alimentación del módulo Bluetooth. | `$SMSG=Reset_BLE`; Sin valor | Sí | Sí | Sí | Sí |
| `$SMSG=Reset_44` | Restablece valores predeterminados y reinicia; pierde la configuración personalizada de EEPROM. | `$SMSG=Reset_44`; Sin valor; usar solo con intención de restablecer | Sí | Sí | Sí | Sí |
| `$OK / OK` | Confirmación del mensaje enviado al equipo GPS. Es parte del protocolo, no una orden de operador. | `$OK`; Enviar solo al confirmar recepción correcta | Sí | Sí | Sí | Sí |

## Comandos Bluetooth

| Comando | Para qué sirve | FW4.1 | FW4.2 | FW4.3 | FW4.4 |
|---|---|:---:|:---:|:---:|:---:|
| `PPON` | Abre o desbloquea el perno. | Sí | Sí | Sí | Sí |
| `POFF` | Cierra o bloquea el perno. | Sí | Sí | Sí | Sí |
| `RST4` | Restablece valores de fábrica y reinicia. | Sí | Sí | Sí | Sí |
| `I1_1` | Habilita entrada 1: equivale a INT_1:2. | Sí | Sí | Sí | Sí |
| `I1_0` | Deshabilita seguimiento de entrada 1: equivale a INT_1:0. | Sí | Sí | Sí | Sí |
| `I2_1` | Habilita entrada 2: equivale a INT_2:2. | Sí | Sí | Sí | Sí |
| `I2_0` | Deshabilita seguimiento de entrada 2: equivale a INT_2:0. | Sí | Sí | Sí | Sí |
| `PC_1` | Activa el paro por sobrecorriente. | No | No | No | Sí |
| `PC_0` | Desactiva el paro por sobrecorriente. | No | No | No | Sí |
| `PC_?` | Consulta el ajuste; la respuesta se genera por Serial/GPS. | No | No | No | Sí |

## Tiempo: ejemplos sencillos

| Comando | Límite nominal del movimiento |
|---|---|
| `$SMSG=TIEMPO:0` | 4 segundos |
| `$SMSG=TIEMPO:5` | 9 segundos |
| `$SMSG=TIEMPO:10` | 14 segundos |

El mismo ajuste se usa para abrir y cerrar. Con `Sensores:0`, alcanzar el sensor puede terminar antes. Con `Sensores:1`, trabaja con el límite de tiempo. Se conservan las pausas existentes, incluida la espera posterior con el motor apagado; por eso esos valores no representan la duración exacta de toda la respuesta del proceso.

## Valores y estados predeterminados por versión

**El tiempo base queda en 4 segundos**, con `TIEMPO:0` de fábrica: límite nominal de 4 segundos tanto para abrir como para cerrar. Los sensores pueden detener el movimiento antes. La pausa posterior de 3 segundos es independiente.

Estos son valores de fábrica o de restablecimiento, no una orden de sobrescribir ajustes existentes al actualizar. Por ejemplo, una unidad que ya tenga `TIEMPO:5` conserva su límite de 9 segundos. Los estados de sensores, contadores y señales vivas cambian durante el arranque y el uso.

| Ajuste o estado | FW4.1 | FW4.2 | FW4.3 | FW4.4 | Qué significa |
|---|---|---|---|---|---|
| Entrada 1: seguimiento | 0 | 0 | 0 | 0 | 0 = seguimiento deshabilitado; el nivel eléctrico depende de la señal física. |
| Entrada 2: seguimiento | 0 | 0 | 0 | 0 | 0 = seguimiento deshabilitado; el nivel eléctrico depende de la señal física. |
| Entrada 3: seguimiento | 0 | 0 | 0 | 0 | 0 = seguimiento deshabilitado; el nivel eléctrico depende de la señal física. |
| Salida 1: valor lógico guardado | 0 | 0 | 0 | 0 | 0 = bajo lógico. OUT_3 no tiene comando de edición en los parsers revisados; no expresa tensión ni cableado. |
| Salida 2: valor lógico guardado | 0 | 0 | 0 | 0 | 0 = bajo lógico. OUT_3 no tiene comando de edición en los parsers revisados; no expresa tensión ni cableado. |
| Salida 3: valor lógico guardado | 0 | 0 | 0 | 0 | 0 = bajo lógico. OUT_3 no tiene comando de edición en los parsers revisados; no expresa tensión ni cableado. |
| Tiempo base de apertura y cierre | 4000 ms | 4000 ms | 4000 ms | 4000 ms | Base común a ambos movimientos. |
| TIEMPO: segundos adicionales | 0 s | 0 s | 0 s | 0 s | 0 = sin tiempo extra; límite nominal de fábrica de 4 segundos. |
| Máximo adicional configurable | 10 s | 10 s | 10 s | 10 s | Rango TIEMPO: 0 a 10; máximo nominal 14 segundos. |
| Pausa después del movimiento | 3000 ms | 3000 ms | 3000 ms | 3000 ms | Espera con motor apagado; se añade al proceso, no a los 4 segundos de accionamiento. |
| Constante interna Tiempo_Espera | 5000 ms | 5000 ms | 5000 ms | 5000 ms | Constante interna; no es un ajuste TIEMPO del usuario. |
| Sensores del motor (SEN_MOT) | 0 | 0 | 0 | 0 | 0 = terminar por sensores, sujeto al límite de tiempo; 1 = trabajar por tiempo. |
| Paro por sobrecorriente configurable | No disponible | No disponible | No disponible | 0 | FW4.4: 0 = desactivado; 1 = activado. En FW4.1–4.3 no existe este ajuste: el paro está fijo en la lógica. |
| Mapeo M1 | No disponible | 0 | 0 | 0 | 0 = normal; 1 = intercambiado. FW4.1 no dispone del ajuste. |
| Mapeo M2 | No disponible | 0 | 0 | 0 | 0 = normal; 1 = intercambiado. FW4.1 no dispone del ajuste. |
| Bloqueo: salida GPS elegida | 0 | 0 | 0 | 0 | 0 = ninguna salida GPS seleccionada. |
| Campo MOTOR del estado | 0 | 0 | 0 | 0 | Campo histórico; no equivale al paro por sobrecorriente ni tiene comando MOTOR de edición. |
| SPAS: separador entre campos | \| | \| | \| | \| | Carácter que separa campos de estado. |
| SPAV: separador campo/valor | ; | ; | ; | ; | Carácter entre nombre del campo y valor. |
| DBG_TQT: eventos | 0 | 0 | 0 | 0 | 0 = desactivados; independiente de la compilación Debug/Release. |
| S_ON: estado inicial guardado | 0 | 0 | 0 | 0 | Se actualiza con la lectura del sensor; no asegura perno abierto o cerrado. |
| S_OFF: estado inicial guardado | 0 | 0 | 0 | 0 | Se actualiza con la lectura del sensor; no asegura perno abierto o cerrado. |
| ERROR: valor inicial | 0 | 0 | 0 | 0 | Estado vivo; puede cambiar durante la operación. |
| VIVA: valor inicial | 0 | 0 | 0 | 0 | Se alterna al arrancar y durante operación; puede observarse 1 tras el arranque. |
| RESET: contador inicial | 0 | 0 | 0 | 0 | Se incrementa al arrancar: tras inicializar valores de fábrica puede observarse 1. |
| Versión de estructura EEPROM | 5 | 6 | 6 | 7 | Versión de datos; distinta de la versión de firmware. |
| MOV: contador inicial | 0 | 0 | 0 | 0 | MovMotor se inicializa en 0; aumenta con movimientos reales. |
| Nombre de tarjeta | Identidad de la tarjeta | Identidad de la tarjeta | Identidad de la tarjeta | Identidad de la tarjeta | Nombre individual obtenido de la identidad programada; no existe un nombre numérico universal. |

En FW4.1–4.3 el paro por sobrecorriente se ejecuta en la lógica del motor y no es configurable con `PARO_C`. En FW4.4 su nuevo ajuste inicia en **0, desactivado**, y puede activarse con `PARO_C:1` o `PC_1`.

Los valores de salidas son lógicos y los estados S_ON/S_OFF son iniciales: no determinan el voltaje, cableado ni la posición física del perno. Nombre, MAC e identidad corresponden a cada unidad; no se debe usar la identidad de ejemplo de un proyecto como valor universal.

El JSON conserva los 37 comandos y añade `factory_defaults`, `default_setting_key` y `default_by_version` para relacionar cada comando de configuración con su valor inicial. `null` representa un ajuste no disponible o una acción sin valor propio; `default_note` distingue los casos.

## Detalles importantes para la web

- En4.4 la protección inicia desactivada. `PARO_C:1` / `PC_1` la activa; `PARO_C:0` / `PC_0` la desactiva. El ajuste se conserva tras reinicio cuando el guardado se confirma.
- `PARO_C` no añade un campo a la trama S29 existente. Se informa mediante una línea separada `PARO_C:0` o `PARO_C:1`; conservar ambos mensajes en el lector web.
- `PC_?` llega por Bluetooth, pero esta implementación emite la respuesta por Serial/GPS. No se promete una respuesta de notificación BLE que el puente actual no implementa.
- `TIEMPO`, `PARO_C` y `MAP` comprueban escritura, espera de disponibilidad y lectura de vuelta. Si aparece `ajuste no confirmado`/`EEPROM ERROR`, no asumir que quedó persistido: revisar la unidad.
- No existe un comando `$SMSG=MOTOR:...` en los parsers revisados. Que aparezca `MOTOR` en el estado no significa que exista una orden para editarlo.
- El estado general incluye `VER`, `HW`, `TIEMPO`, `SEN_MOT` y otros datos. La tabla usa la versión interna del firmware, no el nombre del archivo HEX.
- Los ajustes conservan FW4.4 y esquema EEPROM7. El cambio6→7 conserva campos previos y solo inicializa la nueva protección.

Archivo para incorporar posteriormente a la web: `comandos_r1_por_version.json`. No se modificó la web para integrar esta tabla.
