# Programación R1 STM32 desde la web

En la consola abre Programación y selecciona R1 · STM32 / J-Link. Elige una R1 de la lista, busca su número o utiliza el botón de escaneo con el celular vinculado. También se acepta el texto del QR en el buscador. Debe estar emparejada con una R2 que tenga MAC registrada. Se muestran nombre de R1, R2, ID y MAC de R2, HW, firmware y CRC.

El firmware base FW 4.3 procede del HEX Debug aportado. La web únicamente añade los 76 bytes de identidad reservados; no recompila por unidad. R1 y R2 pueden tener números distintos.

## Primera configuración de Windows

1. Expande Configurar esta computadora por primera vez, escribe el nombre de la PC y descarga el agente.
2. Extrae el ZIP en una carpeta privada, conecta un J-Link por USB y ejecuta iniciar.cmd. Requiere Python >=3.10 y SEGGER J-Link instalado; en la PC de desarrollo se detectan las instalaciones existentes.
3. Mantén abierta la ventana, vuelve a la web y pulsa Actualizar estaciones. Elige la PC conectada.
4. Conecta la R1 de laboratorio por SWD, revisa los datos y pulsa Programar STM32 con J-Link.
5. Confirma la PCB física en la ventana del agente escribiendo PROGRAMAR. El agente graba y lee de vuelta todos los bytes presentes en HEX, valida la identidad y obtiene el UID. La web registra FW en inventario solo al recibir verificación válida.

La opción Descargar HEX permite inspección o programación manual en herramientas locales. El flujo ESP32 existente queda en ESP32 · USB serial.

## Registro y recuperación

La base SQLite conserva estaciones y trabajos en stm32_stations / stm32_jobs. Cada trabajo registra operador, estación, tarjeta, identidad, firmware, hashes, UID y resultado. No modifica la EEPROM externa ni los option bytes.

El agente hace conexiones salientes al servidor y usa una credencial dedicada guardada únicamente en el ZIP/config.json. El servidor conserva su hash. El agente no expone puertos locales, no desactiva validación TLS y pide confirmación de la unidad física antes de grabar.

Se bloquean trabajos simultáneos por PCB y estación. Se vuelve a consultar inventario antes de tomar el trabajo. Los trabajos pendientes caducan a los 120 s; los que no reportan tras 10 minutos quedan con resultado desconocido. No se reintenta automáticamente una grabación. Si se corta la red después de grabar, el agente reintenta solo el reporte mientras siga abierto y guarda el resultado local en resultados/.

Si el agente se cierra antes de reportar, comprobar la tarjeta y conservar el resultado local; el servidor no debe interpretarlo como éxito ni programar automáticamente otra vez. Un reporte autenticado tardío puede completar el trabajo desconocido. El UID identifica el microcontrolador leído, pero la correspondencia con la PCB seleccionada depende de la confirmación física del operador.

Un nombre válido de EEPROM existente se conserva. Puede ser distinto del nombre de fabricación grabado en Flash.

## Despliegue

Los Dockerfile incluyen station/, firmware/stm32_r1/ y los módulos nuevos de app/. El despliegue de devsky usa servidor/compose.yml con app/, station/ y firmware/stm32_r1/ montados en solo lectura sobre la imagen existente. Esta configuración de desarrollo permite actualizar el código sin reconstruir capas grandes en la partición limitada. Mantener los volúmenes de base y respaldos. Las pruebas usan una base temporal y un J-Link simulado; falta la primera prueba real de escritura/lectura y validación funcional de la R1.

Comandos J-Link utilizados y referencia oficial: [J-Link Commander](https://kb.segger.com/J-Link_Commander).
