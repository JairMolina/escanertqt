# Matriz de comunicación serial y Bluetooth (v1.4.0)

Inventario de los puntos reales de comunicación con hardware en la web. Excluye librerías vendor (`app/static/js/vendor/esptool-js`). Capa compartida nueva: `app/static/js/serial_web.js` (`window.TQTSerial`): un propietario por puerto, lector incremental, cola de escritura y liberación de locks.

| Ruta / archivo | Hardware | Protocolo | Transporte actual | Agente | Reemplazo viable |
|---|---|---|---|---|---|
| `#/validacion` · `validacion_web.js` (nuevo) | R1 STM32 (UART del banco) | S29/`$SMSG=…`, 57600 8N1, ACK `$OK\r\n` a 180 ms, guardia de 300 ms, barrera S29 | Web Serial mediante `TQTSerial` | No | Hecho: es la ruta normal |
| `#/validacion` · `validacion_web.js` | ESP32 de R1 y R2 (BLE) | GATT `4fafc201…/beb5483e…`, `PPON`/`POFF` ASCII sin terminador | Web Bluetooth | No | Hecho. La MAC BLE no es observable: el vínculo se verifica por PB=2 (R1) y err=13/14 (R2) |
| `#/validacion` · `sec_validacion.js` + `station/test_station/agent.py` | Igual que las dos filas anteriores | Igual (motor Python 0.6.3) | pyserial + bleak en Windows | Sí (`/api/stm32/agent/tests`) | Se mantiene como respaldo. Retirarlo cuando se acepte la ruta web en el banco físico |
| `#/programacion` R2 · `sec_programacion.js` (flasheo) | ESP32 R2 (USB‑UART) | ROM bootloader (esptool-js), 460800 por defecto (921600…115200) | Web Serial directo (`port.open`) | No | Migrar la apertura y el cierre a `TQTSerial`, conservando esptool. Pendiente: se sigue usando el control propio de esptool |
| `#/programacion` R2 · `sec_programacion.js` (monitor) | ESP32 R2 | Texto, 115200 por defecto (seleccionable) | Web Serial directo | No | Migrar a `TQTSerial.abrir` + `crearTramador` (propietario «monitor») |
| `#/programacion` R2/R1 · `leerMacPorSerial` | ESP32 R2 / ESP32 de R1 | `MAC\n` / `INFO\n`, 115200 | Web Serial directo | No | Migrar a `TQTSerial` (propietario «identidad») |
| `#/programacion` R1 (ESP32) · `sec_programacion.js` | ESP32 de R1 (`ESP32_BLE_SERIAL`) | esptool, firmware fijo | Web Serial directo | No | Igual que el flasheo de R2. No reutilizar sus baudios en la Validación |
| `#/programacion` R2 OTA · `esp32_ota.js` | ESP32 R2 v4.x | GATT OTA `d45a0001…` | Web Bluetooth | No | Ya es web (corrección de la sección D a cargo de A) |
| `#/programacion` R1/R3 STM32 · `stm32_programacion.js` + `station/agent.py` | STM32 R1/R3 | SWD | J-Link (ejecutable nativo) | Sí | **Sin reemplazo con Web Serial.** SWD necesita J-Link y su driver. Se conserva el puente |
| `validacion.py` (`/api/…/agent`) · verificación R2 | ESP32 R2 (BLE) | GATT TQT | bleak en Windows | Sí | Se puede llevar a Web Bluetooth con el mismo `BleLink` de `validacion_web.js`. Pendiente |

## Límites

- Web Serial y Web Bluetooth solo funcionan en Chrome o Edge de escritorio, en HTTPS o localhost. Los selectores nativos son inevitables la primera vez. Los puertos y dispositivos ya autorizados se reutilizan con `getPorts()` y `getDevices()`.
- `requestDevice()` necesita un gesto del usuario. En las etapas 7 y 12 el motor reutiliza el permiso si ya existe. Si no, pausa la etapa y pide un clic: con el `solicitarGesto` de la UI o, si la UI no lo da, con un diálogo propio.
- Otra pestaña o programa que tenga el COM abierto hace fallar la apertura: se informa al operador y no se fuerza. Dentro de un mismo navegador, `navigator.locks` impide dos validaciones a la vez.
- El servidor valida la estructura, las tramas S29 crudas y el inventario. No observa el hardware, así que el informe no es una atestación criptográfica.
