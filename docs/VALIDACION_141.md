# Pruebas TQT 1.4.1: distribución y compatibilidad Bluetooth

Base de trabajo: 1.4.0, commit `f689b7d8193e621687d7ba5f76de9ce4a52b3f53`.
Alcance: solo Pruebas TQT; actualización de versión y caché. No cambia programación R1/R2/R3 ni firmware. No despliegue de producción en este avance.

## Interfaz

- Tres paneles superiores: Pruebas TQT/modo, serial con ON/OFF, Bluetooth con conexión R1/R2 y ON/OFF.
- Columna izquierda: selector con estilo de Programación, historial y después detalles R1/R2.
- Número + Enter resuelve una coincidencia exacta de número; clic y QR siguen disponibles. Ambigüedad no elige una tarjeta arbitraria.
- Resultado, 14 etapas y sensores permanecen en el área principal.
- Diseño adaptable sin desbordamiento horizontal en las vistas verificadas de 1440 y 390 px.

## Dos transportes, solo en esta sección

**Navegador:** conserva Web Serial/Web Bluetooth. Nombres de una misma identidad admiten guiones, guiones bajos y HW V3_0/V30. No acepta otro número/rol/HW ni resuelve identidades autorizadas duplicadas arbitrariamente. El permiso nativo inicial sigue siendo obligatorio; conectar R1 y R2 desde el encabezado permite reutilizarlo durante la rutina. La MAC física no está disponible por Web Bluetooth: no se fabrica a partir de device.id.

**Usar Windows por MAC:** recupera la ruta existente del motor de pruebas Windows completo, con serial por pyserial y BLE por Bleak. No es un reemplazo JavaScript que acceda mágicamente a la MAC. Necesita el agente local anterior activo. La preferencia se guarda solo para Validación. El serial del navegador se cierra al cambiar; para volver se exige desconectar los recursos del agente. No utilizar simultáneamente ambos motores sobre el banco.

La rutina Windows ya busca R1 por MAC reportada y R2 por MACR después de desconectar R1, sin exigir nombre de inventario idéntico. Se conserva su control de identidad y sus 14 pruebas. La conexión manual del encabezado selecciona una única coincidencia de MAC registrada, nunca la primera TQT encontrada. Si hay varios bancos sin asociación previa, no se elige arbitrariamente uno.

El modo Windows recupera también sus limitaciones previas (incluido el flujo propio de identificación/cambio de tarjeta del motor original); no se afirma que las capacidades nuevas de la ruta web se hayan portado al agente. No se modificó ni reinstaló un agente durante estas verificaciones.

## Controles y evidencia

ON/OFF serial directo pide un S29 fresco, coteja ambas MAC con la tarjeta seleccionada y exige motor en reposo y sensores coherentes antes de enviar el movimiento. No ejecuta Reset_44 ni produce una aprobación automática. Los controles manuales quedan bloqueados mientras se ejecuta la rutina.

Bluetooth manual utiliza el nombre esperado (incluidos sus alias) y no reconecta silenciosamente a una unidad de otro número. La conexión R2 comprueba también la MAC declarada por el servicio OTA cuando está disponible. Firmware antiguo sin esa información conserva las limitaciones de evidencia de la ruta web.

## Verificación

- `node tests/sec_validacion_ui.cjs`: encabezado, orden lateral, selección numérica, filas persistentes, impresión ligada a la identidad confirmada y respaldo agente.
- `node tests/validacion_web_engine.cjs`: rutina original, cancelación/identidad, alias BLE, ambigüedad y rechazo de otro número/rol; guardia manual serial con muestras y transporte simulado.
- `python -m unittest discover -s tests -p test_test_station_web.py -q`: backend de evidencias (16 casos).
- Playwright contra Docker local: escritorio/móvil, selección 0042 por Enter, 14 filas, sin errores JS ni overflow. Alternancia navegador/Windows con presencia de estación simulada, sin tocar radio ni puertos.
- Capturas de QA fuera de Git: `outputs/validacion_141/escritorio.png` y `movil.png` en el workspace raíz.

Vista local aislada: http://127.0.0.1:18084/monitor#/validacion. Contenedor `tqt-validacion141-web-1`, volumen nuevo `tqt-validacion141-data`, únicamente tarjetas sintéticas. No contiene la base productiva ni se dirige a la estación física.

Pendiente: aceptar con tarjetas reales y sus nombres antiguos, probar lectura serial y selección automática por MAC del agente instalado en esa laptop; desplegar únicamente con autorización específica y sin trabajos activos. Las pruebas simuladas no certifican hardware ni tiempos reales.
