# Código editable y compilación sin web

Este es el programa completo del firmware actual **4.2**, HW **3.0**, con OTA Bluetooth rápida y escritura de eFuses desactivada. La base genérica 4.0 se conserva por separado y no se cambia al crear versiones nuevas.

## Editar y compilar

Modifica la lógica en `TQT_R2_V4_2.ino`, `tqt_ota.cpp` y sus archivos de apoyo. En `tqt_profile.cpp` están HW, FW y el nombre de plantilla. Para una versión 4.3 cambia `"4.2"` a `"4.3"`; no hace falta renombrar la carpeta para que cambie la versión informada. Si renombras el proyecto, la carpeta y el único `.ino` deben tener el mismo nombre.

Desde PowerShell, dentro de esta carpeta:

```powershell
.\compilar_local.ps1 -Nombre TQT-R2-V30-0067
# También puedes escribir los datos manualmente:
.\compilar_local.ps1 -Nombre TQT-R2-V30-0067 -Hardware 3.0 -Firmware 4.3
```

Si editas también el nombre en `tqt_profile.cpp`, puedes omitir `-Nombre`. El nombre debe coincidir exactamente con el inventario; `0000` es una plantilla y no es una unidad válida. El campo de clave del proyecto público debe quedarse en `{0}`: el preparador introduce la credencial en una copia privada antes de compilar.

Se necesitan Python, Arduino IDE/CLI, el core ESP32 3.3.12 y esptool ya instalados. El comando no llama a la web, a Docker ni instala paquetes. Las herramientas tienen que estar disponibles antes de perder internet. La compilación normal `compilar.ps1` sigue generando la plantilla para subir al catálogo web; `compilar_local.ps1` genera el firmware de una tarjeta concreta.

## Archivos privados y reutilización OTA

En esta laptop las identidades están en `C:\Users\usuario\.tqt\R2\identidades\`. La copia compilable activa queda en `C:\Users\usuario\.tqt\R2\proyectos\TQT_R2_V4_2\`. Los BIN y HEX personalizados se archivan en `C:\Users\usuario\.tqt\R2\firmwares\<nombre>\FW-<version>\`. No se incorporan a Git ni a la carpeta pública de códigos.

Para la **0067** se conservó la misma credencial de la web local donde se probó la OTA; no se genera otra al recompilar ni cambiar FW. Su origen está indicado en el JSON privado. Esto no implica que el registro ya exista en producción: el servidor Orange Pi todavía no recibió estos cambios ni los datos de la prueba local.

Para otra unidad que ya exista en la web usa su propia identidad exportada, nunca la de la 0067. Puedes indicar `-Identidad 'ruta\identidad.json'`. Si no hay identidad local, el preparador crea una nueva por unidad y conserva su JSON. Una tarjeta nueva puede funcionar con ese firmware offline, pero esa credencial debe registrarse en el servidor antes de poder autorizar OTA desde esa web. No se implementa aquí un importador de identidades; alternativamente se puede reinstalar la base genérica por USB y darla de alta desde la web. No borres ni compartas los JSON: contienen las credenciales de actualización.

## Grabar por USB

El archivo recomendado es el **BIN completo**, a dirección **0x0**. El HEX también se exporta. Con la tarjeta ya en BOOT + RESET y el COM correcto, se puede usar esptool:

```powershell
& 'C:\Users\usuario\AppData\Local\Arduino15\packages\esp32\tools\esptool_py\5.3.1\esptool.exe' --chip esp32 --port COM4 --baud 460800 --before no-reset --after no-reset write-flash 0x0 'RUTA_DEL_BIN_PERSONALIZADO'
```

Al terminar y verificar el hash, liberar BOOT y reiniciar manualmente. Si falla la comunicación, revisar los contactos y probar 115200. El comando de compilación no graba ninguna tarjeta por sí mismo. La plantilla `0000` no debe grabarse directamente en producción.
