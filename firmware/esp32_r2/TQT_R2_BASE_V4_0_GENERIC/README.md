# Base R2 4.0 genérica con OTA rápida

ESP32-WROOM-32E-N4, HW 3.0. La misma imagen se instala por USB en todas las tarjetas y anuncia `TQT_R2_V30_XXXX`. No contiene número de unidad ni secreto compartido. No escribe eFuses; los diagnósticos de VDD_SDIO se conservan.

Ejecutar `compilar.ps1` con Arduino ESP32 3.3.12 y placa `esp32doit-devkit-v1` para exportar BIN completo y HEX. El catálogo usa el archivo normalizado `../TQT_R2_BASE_V4_0_GENERIC.merged.bin`.

En la web, seleccionar la tarjeta del inventario y FW 4.2, pulsar Actualizar por Bluetooth y elegir el dispositivo XXXX. El alta utiliza ECDH, un ticket firmado y AES-GCM para guardar la identidad en NVS. Luego se instala el firmware personalizado y se confirma el inventario solamente tras verificar el nuevo arranque.

Después del alta el nombre coincide exactamente con el inventario: `TQT-R2-V30-0067`, por ejemplo. `XXXX` solo identifica la base sin asignar.

`enrollment_trust.h` contiene únicamente la clave pública del emisor. Su clave privada persistente debe conservarse fuera de Git y respaldarse de forma segura: `/data/r2_enrollment_signing.pem` o `TQT_R2_ENROLL_SIGNING_KEY`. El servidor debe usar la clave correspondiente a esta base; regenerarla impediría el alta de las bases existentes. No cambiar esta relación al desplegar.

Las pruebas físicas de una tarjeta y su conexión se documentan en el estado del proyecto; una compilación correcta no equivale a una grabación verificada.

## Arduino IDE y producción en masa

En Arduino IDE seleccionar **DOIT ESP32 DEVKIT V1**, el COM del USB–TTL y core ESP32 **3.3.12**. Con la R2 en BOOT + RESET, pulsar **Subir**; al verificar la carga, liberar BOOT y reiniciar. No cambiar el nombre XXXX ni editar datos por unidad en esta base.

La compilación puede producir otro hash de aplicación. Para que la web reconozca esa compilación, registrar una vez su BIN completo mediante Subir BIN/HEX. Se admiten varias compilaciones de base registradas sin invalidar las anteriores. Una base desconocida sigue rechazándose.

Para producción en masa usar directamente el BIN fijo ya registrado, sin recompilar. Desde esta carpeta:

```powershell
.\programar_base.ps1 -Puerto COM4
# Solo comprobar herramientas e integridad, sin abrir el puerto:
.\programar_base.ps1 -Puerto COM4 -Comprobar
```

Cambiar COM4 por el puerto real. El comando comprueba el hash del BIN, usa 460800 baud y espera Enter para cada tarjeta en BOOT + RESET. Solo confirma la tarjeta si esptool termina y verifica la escritura. S permite salir. No hay operaciones de eFuses ni de borrado completo de flash.


### Grabacion por Enter o deteccion automatica de BOOT

El modo predeterminado conserva ENTER por tarjeta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\programar_base.ps1" -Puerto COM4
```

Para iniciar cada grabacion al recibir un nuevo arranque DOWNLOAD_BOOT:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\programar_base.ps1" -Puerto COM4 -Modo Automatico
```

Cierra el monitor serial de Arduino u otra aplicacion que use COM4. Espera el aviso «Esperando NUEVO BOOT», conecta una sola R2 y genera BOOT+RESET. El script escucha el mensaje ROM a 115200, cierra ese lector y entrega el puerto a esptool para grabar a la velocidad elegida (460800 predeterminada). No cambia el BIN ni escribe eFuses.

Espera «Grabacion y hash verificados» antes de retirar los contactos. Cambia la tarjeta y genera otro BOOT+RESET despues del nuevo aviso de espera. No identifica por si mismo si has colocado otra unidad: un nuevo reset en modo BOOT de la misma tarjeta tambien inicia otra grabacion. No basta una tarjeta que ya estaba en BOOT sin emitir un nuevo mensaje. Ctrl+C termina la espera; si falla la grabacion automatica, muestra el fallo y vuelve a esperar un NUEVO BOOT+RESET sin cerrar la sesion ni reintentar por su cuenta. No interrumpas una escritura en curso.

Ambos modos admiten `-Comprobar`: valida BIN/herramienta sin abrir el puerto ni escribir. El nuevo modo automatico requiere validacion fisica; las pruebas de software no programan hardware.
