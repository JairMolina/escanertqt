# Firmware STM32 beta y aprobado — web 1.4.41

Base integrada: producción 1.4.39, bfb646517ca5ad0892df1b4c654b39e781c82b06. No se mezclan ramas antiguas ni se modifica R2 OTA.

## Flujo

1. Subir HEX de R1/R3 desde Programación. Cada imagen nueva se guarda como **beta**. Los registros anteriores conservan **aprobado** para no cambiar retroactivamente el funcionamiento.
2. El selector muestra BETA / solo pruebas. Se puede elegir explícitamente para programar una tarjeta de ensayo; no se selecciona de forma automática. La versión aprobada más alta compatible conserva el predeterminado.
3. La grabación y lectura verificadas registran el FW real en la tarjeta, pero no aprueban la imagen ni hacen que el resto de tarjetas deban actualizarse. El catálogo de versiones de inventario omite versiones conocidas únicamente como beta.
4. Después del banco, seleccionar esa imagen y pulsar **Aprobar firmware beta**. Solo un administrador puede confirmar; debe documentar tarjeta, pruebas y resultado. Se registra usuario, fecha, evidencia y hash. Es una declaración humana: el servidor no certifica por sí solo que se hicieron las pruebas físicas.
5. Si es la versión aprobada más alta compatible, pasa a predeterminada. Aprobar una versión inferior no reemplaza una superior ya aprobada. No se modifican los bytes de la imagen ni los trabajos previamente creados.

El estado pertenece al hash de la imagen, no al nombre del archivo. Volver a subir una beta idéntica no la aprueba. Una imagen corrupta no se puede aprobar. La aprobación no se dispara al terminar J-Link.

## Preparación FW 4.4

Corregidos en el proyecto local los dos defectos revisados. Parche sin identidad privada: fw44_control_fix.patch. Prueba reproducible: fw44_test_protocol_arm.py, usando --project con el directorio CubeIDE, --deps para Unicorn2.1.4 y --out para los artefactos de revisión. No abre sondas.

La identidad local de la unidad de ensayo se preparó a partir del inventario; sus datos no se publican en este repositorio. Se preservó copia anterior. El HEX base para catálogo omite identidad y se generó fuera de Git como R1_FW4.4_BETA_Debug_base_web.hex. No sustituye al firmware estable semilla del servidor.

## Verificaciones

- Debug/Release: 28 fuentes, cero errores/advertencias; 74 comprobaciones ARM y 14 pruebas HEX correctas. Ocho resultados suplementarios correctos prueban comandos válidos, inválidos y recuperación BLE, con salidas simuladas.
- 48 pruebas Python de catálogo/STM32, incluyendo exclusión beta del predeterminado y vigencia tras registrar inventario, duplicados, promoción, hash, permisos y preservación de trabajos.
- Playwright en QA localhost18089: estable4.3 predeterminado con beta4.4 visible; etiqueta de tarjeta4.3 sigue actualizada; aprobación simulada registra evidencia y pasa4.4 a predeterminada. Sin errores JS. El ensayo de aprobación solo existe en la base QA aislada y no es una aprobación física del firmware real.
- Interfaz móvil comprobada; no se ejecutaron comandos de programación. El backend de producción permanece1.4.39 mientras no se autorice despliegue.

Capacidades: ECC HW/FW, verificación y backend; UI existente y revisión responsive con ui-ux-pro-max. No se usaron subagentes ni se modificó infraestructura compartida.

Integración concurrente: producción avanzó a1.4.40/b90ee570 durante el ensayo. Se conserva íntegra su reducción de escrituras de presencia de agentes; versión final de esta tarea1.4.41.
