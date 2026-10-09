# TQT R1 — hardware 3.0 / firmware 4.3

Proyecto derivado de FW 4.1. Agrega el intercambio independiente de los pares PA1/PB0 y PA2/PB1. No requiere reinicio para aplicar el mapeo.

## Comandos

Enviar con el mismo terminador de línea usado por los comandos existentes (`\r\n`). Se reciben por las rutas actuales de comandos `$SMSG` de plataforma/UART5 y depuración/UART4. No se agregaron comandos abreviados de Bluetooth.

| Comando | Función |
|---|---|
| `$SMSG=MAP_M1:0` | Cierre en PA1; INT_1 en PB0. Predeterminado. |
| `$SMSG=MAP_M1:1` | Cierre en PB0; INT_1 en PA1. |
| `$SMSG=MAP_M2:0` | Apertura en PA2; INT_2 en PB1. Predeterminado. |
| `$SMSG=MAP_M2:1` | Apertura en PB1; INT_2 en PA2. |
| `$SMSG=MAP?` | Consulta ambos mapas, sin escribir EEPROM. |

Una configuración correcta y la consulta responden con ambos valores, por la función de envío GPS existente. Ejemplo:

```text
AT$POST=1,0,"MAP M1:0 M2:1"
```

La respuesta usa el encabezado, cierre de comillas y terminador actuales. La trama periódica `S29`, sus campos y sus separadores no cambian. Los mapas se consultan con `MAP?`.

Repetir el valor vigente confirma el estado sin volver a escribir EEPROM. Una petición inválida responde `MAP ERROR: COMANDO INVALIDO`. Un cambio con motor/relevadores activos responde `MAP ERROR: MOTOR ACTIVO`. Si la escritura I2C falla, responde `MAP ERROR: EEPROM` y no aplica el nuevo mapa en RAM. Estos mensajes usan la misma envoltura `AT$POST`.

El procesamiento de comandos conserva el ciclo principal existente: durante una maniobra bloqueante, un comando recibido se procesa cuando el ciclo principal vuelve a atenderlo.

## Adquisición y lógica

ADC1 conserva el modo continuo, DMA circular y tiempo de muestreo. Ahora adquiere cinco canales en orden fijo:

| Índice DMA | Pin | Canal |
|---|---|---|
| 0 | PA0 | ADC1_IN0 — corriente |
| 1 | PA1 | ADC1_IN1 |
| 2 | PA2 | ADC1_IN2 |
| 3 | PB0 | ADC1_IN8 |
| 4 | PB1 | ADC1_IN9 |

Los mapas seleccionan el índice utilizado por cada función. PA1, PA2, PB0 y PB1 permanecen analógicos. INT_3/PB2 conserva su configuración digital.

- Limitadores: se mantiene exactamente `lectura < 2480` como activo, junto con secuencias, retardos, errores, memorias e indicadores existentes.
- Corriente: conserva PA0 y su tratamiento actual. Al agregar canales aumenta la duración del barrido ADC; no cambia el periodo de TIM3 que procesa las lecturas.
- INT_1/INT_2: nivel eléctrico bajo con ADC <= 2233; alto con ADC >= 2482. Equivalen aproximadamente a 1.8 V y 2.0 V con VDDA de 3.3 V. Entre umbrales conserva el nivel anterior.
- Al arrancar o cambiar de mapa, una entrada en la banda intermedia se inicializa en alto/inactivo.
- Las entradas generales mantienen habilitación `Config.Int1/Int2`, comprobación cada 100 ms, filtro de diez comprobaciones, lectura inmediata por sus comandos existentes e inversión del reporte `EST1/EST2`.
- El cambio reinicializa únicamente las memorias y filtros del par afectado, protegido frente a TIM3. Los errores que ya estaban pendientes se conservan.

## EEPROM y proyecto

La versión interna del formato EEPROM pasa de 5 a 6. `MapM1` y `MapM2` se agregan al final de la estructura, sin desplazar los campos anteriores. Al migrar FW 4.1 se conservan sus ajustes y ambos mapas arrancan en cero. También se conserva la migración de los formatos anteriores 2, 3 y 4. Un reinicio conserva el mapa guardado; un reset de fábrica lo regresa a cero.

La configuración se carga antes de inicializar las memorias de entrada y habilitar TIM3. El archivo `.ioc`, el nombre del proyecto, el lanzamiento de depuración y los nombres de los archivos compilados corresponden a FW 4.3.

## Verificación

Compilación completa con GNU Tools for STM32 13.3.rel1, sin advertencias ni errores. Se comprobaron los cuatro mapas, los umbrales, los comandos y la migración; véase `VALIDACION_FW_4.3.txt`. Las funciones existentes de motor, sobrecorriente, indicadores y trama de estado se compararon con FW 4.1.

No se ha grabado ni probado físicamente en una tarjeta. La prueba en banco debe confirmar cada mapa, persistencia después del reinicio, umbrales de INT_1/INT_2 y movimientos de apertura/cierre.
