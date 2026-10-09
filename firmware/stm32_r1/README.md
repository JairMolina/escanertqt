# R1 STM32 / FW 4.3

fw43_base.hex procede del HEX Debug entregado por el usuario. Se retiró únicamente la página de identidad mediante tqt_hex.py preparar-web. El perfil interno declara STM32F103RET6, HW 3.0, FW 4.3 y esquema 2 de 76 bytes en 0x0807F800.

Actualizado el 2026-10-09 desde el proyecto local PCB_TQT_R1_PRINCIPA_WH-V3.0_FW-V4.3, probado en tarjeta por el operador. Los bytes de aplicación y el vector de inicio coinciden con ese HEX; se excluye únicamente la identidad local de ejemplo. Esta prueba del firmware es distinta de la primera grabación con el agente web.

La web añade la identidad consultando R1 y su R2 vinculada en inventario, sin recompilar y sin exigir igualdad entre sus números. El archivo base solo sirve para personalización; no se programa directamente sin identidad.

Para actualizar firmware: compilar y probar en CubeIDE, preparar un HEX base con la herramienta validada y sustituir el archivo de este directorio en una nueva revisión. HW/FW se extraen del perfil interno. No editar FW a mano dentro del HEX.

Se conservan los campos EEPROM. No restablecer VERSION_ACTUAL para una simple actualización de firmware.
