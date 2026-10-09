# Programación R1 STM32 desde la web

En la consola abre Programación y selecciona R1 · STM32 / J-Link. Elige una R1 de la lista, busca su número o utiliza el botón de escaneo con el celular vinculado. También se acepta el texto del QR en el buscador. Debe estar emparejada con una R2 que tenga MAC registrada. Se muestran nombre de R1, R2, ID y MAC de R2, HW, firmware y CRC.

El firmware base FW 4.3 procede del HEX Debug aportado. La web únicamente añade los 76 bytes de identidad reservados; no recompila por unidad. R1 y R2 pueden tener números distintos.

## Primera configuración de Windows

1. Expande Configurar esta computadora por primera vez, escribe el nombre de la PC y pulsa Instalar agente en esta laptop.
2. Abre el archivo Instalar_TQT descargado. Instala el agente en LocalAppData del usuario actual, crea su acceso de inicio con Windows y lo inicia en segundo plano. Usa Python >=3.10 y SEGGER J-Link instalado por separado o el incluido con STM32CubeIDE en C:\ST; avisa si faltan. El navegador requiere que el usuario abra el instalador una vez. Si CubeIDE está depurando, termina esa sesión para liberar la sonda.
3. Vuelve a la web. La lista de estaciones se actualiza automáticamente cada cinco segundos; elige la laptop conectada. No hace falta mantener una terminal abierta.
4. Conecta la R1 de laboratorio por SWD, revisa los datos y pulsa Programar STM32 con J-Link.
5. Pulsa Programar R1: este botón identifica y confirma la R1 física conectada. El servidor registra operador y confirmación vinculada al nombre y la PCB; el agente rechaza trabajos sin esa confirmación. Graba y lee de vuelta todos los bytes presentes en HEX, valida la identidad y obtiene el UID. La web muestra el resultado y registra FW en inventario solo al recibir verificación válida. No hay confirmación en consola.

La opción Descargar HEX permite inspección o programación manual en herramientas locales. El flujo ESP32 existente queda en ESP32 · USB serial.

Para comprobar la instalación sin programar, ejecuta `python agent.py --check` desde la carpeta del agente. Comprueba HTTPS y localiza J-Link sin abrir la sonda. Si ya descargaste un agente anterior a v1.3.48, descarga y extrae el nuevo paquete para recibir la detección de CubeIDE.

El firmware base se actualizó el 2026-10-09 desde el HEX FW 4.3 probado por el operador. La prueba de escritura/lectura desde la web debe realizarse con la R1 física seleccionada y su R2 correctamente emparejada en inventario; el ID y la MAC proceden de esa R2, aunque los números de R1 y R2 sean distintos.

## Registro y recuperación

La web muestra un indicador de actividad y la etapa reportada por el agente: preparación, conexión/grabación, lectura/verificación, reinicio y reporte. No representa un porcentaje estimado. Commander se ejecuta sin ventana de consola en Windows. Solo el resultado final verificado permite desconectar la tarjeta; los avisos de avance no registran firmware.

La base SQLite conserva estaciones y trabajos en stm32_stations / stm32_jobs. Cada trabajo registra operador, estación, tarjeta, identidad, firmware, hashes, UID y resultado. No modifica la EEPROM externa ni los option bytes.

El agente hace conexiones salientes al servidor y usa una credencial dedicada guardada únicamente en el ZIP/config.json. El servidor conserva su hash. El agente no expone puertos locales, no desactiva validación TLS y pide confirmación de la unidad física antes de grabar.

Se bloquean trabajos simultáneos por PCB y estación. Se vuelve a consultar inventario antes de tomar el trabajo. Los trabajos pendientes caducan a los 120 s; los que no reportan tras 10 minutos quedan con resultado desconocido. No se reintenta automáticamente una grabación. Si se corta la red después de grabar, el agente reintenta solo el reporte mientras siga abierto y guarda el resultado local en resultados/.

Si el agente se cierra antes de reportar, comprobar la tarjeta y conservar el resultado local; el servidor no debe interpretarlo como éxito ni programar automáticamente otra vez. Un reporte autenticado tardío puede completar el trabajo desconocido. El UID identifica el microcontrolador leído, pero la correspondencia con la PCB seleccionada depende de la confirmación física del operador.

Un nombre válido de EEPROM existente se conserva. Puede ser distinto del nombre de fabricación grabado en Flash.

## Despliegue

Los Dockerfile incluyen station/, firmware/stm32_r1/ y los módulos nuevos de app/. El despliegue de devsky usa servidor/compose.yml con app/, station/ y firmware/stm32_r1/ montados en solo lectura sobre la imagen existente. Esta configuración de desarrollo permite actualizar el código sin reconstruir capas grandes en la partición limitada. Mantener los volúmenes de base y respaldos. Las pruebas usan una base temporal y un J-Link simulado; falta la primera prueba real de escritura/lectura y validación funcional de la R1.

Comandos J-Link utilizados y referencia oficial: [J-Link Commander](https://kb.segger.com/J-Link_Commander).
