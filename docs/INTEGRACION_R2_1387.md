# Integración sobre la versión actual de la web

El 15 de octubre de 2026 se descargaron las referencias de GitHub y se comparó la aplicación en ejecución por SSH, sin reiniciar ni modificar producción:

- Orange Pi: rama `codex/r2-ota-rapida`, commit `ee604dea9a8984eff1404fe313a083515fb52f48`, aplicación y checkout **1.3.84**, sin cambios locales.
- `origin/main`: `cdd39b1`, más antiguo; no se eligió como base.
- Ajustes R2 probados localmente: rama `codex/r2-alta-generica-42`, commit `8580b278d2a4`, aplicación **1.3.86**, más la evidencia física final pendiente de commit que se conservó por separado.

La rama de integración `codex/r2-integracion-1387` parte del commit exacto de producción y aplica los ajustes R2 encima. Se conserva el código de etiquetas de cable DYMO, incluida la orientación vertical del número, la terminal única de programación, la precarga de esptool y las optimizaciones J-Link de lectura por páginas, SWD y sondeo. La integración de R2 mantiene el alta genérica, FW 4.2, nombre exacto, OTA rápida y recuperación GATT. Versión integrada **1.3.87**.

La preparación offline añade código Python de biblioteca estándar y un comando PowerShell. El proyecto público sigue siendo plantilla sin credenciales; la copia personalizada y las identidades se guardan en `.tqt\R2` dentro del perfil privado del usuario. Las fuentes están listas para editar y generar versiones posteriores. La base 4.0 se conserva como artefacto fijo separado.

La prueba física final de la 0067 pertenece al firmware y protocolo ya verificados, sin cambios de lógica del firmware en esta integración. No se vuelve a grabar la unidad para probar cambios de composición de la web o la compilación offline.

## Verificación ejecutada

- Nueva consulta de GitHub confirmó que la rama desplegada seguía en `ee604dea9a8984eff1404fe313a083515fb52f48`; los archivos de etiquetas DYMO quedaron idénticos a esa referencia.
- 140 pruebas de R2/local, ESP32, STM32, DYMO y estación de pruebas aprobadas; 12 escenarios de transporte OTA aprobados.
- Playwright en la vista previa aislada 18083: versión 1.3.87, una sola terminal visible, cero terminales antiguas, Bluetooth habilitado y paneles R1/R3 presentes. Escritorio y móvil 390 px sin errores JS ni desbordamiento horizontal.
- Compilación nativa local sin llamadas a web/Docker: 1.130.907 bytes de programa, 42.084 bytes RAM; BIN completo de 4 MB y HEX preparados para la 0067. Perfil, integridad y credencial se validaron después contra la copia local de la base: nombre exacto, HW3.0/FW4.2, protocolo OTA1 y misma clave registrada. No se grabó hardware en esta compilación.

## Archivos preparados para el usuario

Carpeta pública: `C:\Users\usuario\Mi unidad\ESP32_BLE_SERIAL\TQT_R2_Programacion_Web_y_Local`.

- `FW_GENERAL_4_0\BASE_GENERAL_4_0.bin` y HEX: base fija, idéntica para todas las unidades, nombre XXXX antes del alta.
- `FW_ACTUAL_4_2\TQT_R2_V4_2\`: código editable completo, `compilar.ps1` para plantilla web y `compilar_local.ps1` para una unidad offline.
- BIN/HEX personalizado de prueba: `C:\Users\usuario\.tqt\R2\firmwares\TQT-R2-V30-0067\FW-4.2\`. Su identidad se conserva en `.tqt\R2\identidades`, fuera del repositorio y de la carpeta pública.

Para unidades creadas enteramente offline se conserva una credencial propia por tarjeta. Ese JSON debe incorporarse al servidor antes de OTA desde esa web; no se añadió un importador en esta entrega. Para una tarjeta ya registrada se debe reutilizar su identidad existente. La 0067 está preparada contra el servidor local de pruebas, no contra la base de producción que no se modificó.
