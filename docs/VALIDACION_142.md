# Validación 1.4.2: Web Serial y Bluetooth Windows por MAC

Sustituye el modo Windows completo descrito en VALIDACION_141.md. La distribución de tres bloques y selector izquierdo de 1.4.1 se conserva.

## Operación

En Pruebas TQT el serial sigue usando Web Serial del navegador, con el mismo protocolo y temporización. Solo BLE recupera Bleak de Windows: descubre y conecta la MAC validada contra inventario y S29, aunque el nombre anunciado use guiones bajos o una versión de hardware antigua en el texto. El nombre no acredita el HW físico.

El puente se prepara una vez desde «Preparar puente Bluetooth». El instalador registra una estación del operador con ble_only=true. Esa instancia no abre el COM, no ejecuta las 14 etapas ni acepta órdenes del motor completo. Usa la cola autenticada existente del servidor; no abre un servidor HTTP local. «Actualizar Bluetooth Windows» actualiza su presencia, sin cambiar la conexión serial.

Se necesita ese puente ejecutándose en Windows y conexión con la web. Web Bluetooth sigue disponible en el motor para compatibilidad, pero no ofrece descubrimiento silencioso por MAC. No se ha eliminado la necesidad del puente nativo en este flujo.

El servidor autoriza cada operación una sola vez, vincula operador/estación/tarjeta/ejecución, limita vigencia y coteja MAC. PPON/POFF requieren S29 válido con ambas MAC. Se rechazan estaciones usando serial, otra prueba y trabajos STM32 activos. No hay reintento automático de movimientos. La prueba requiere las evidencias funcionales originales PB=2 y err=13/14 además de la MAC observada autenticada.

## Resultado físico verificado

2026-10-16, ejecución local 44d7b1fc0e23708d0817f0bf09613c8c, tarjeta 0039, COM7, banco libre y Reset_44/movimientos expresamente autorizados. Inicio 13:31:59 y fin 13:33:48 (hora México), duración aproximada 108,2 segundos.

- R1: inventario TQT-R1-V30-0039, anuncio TQT_R1_V3_0_0039, MAC 8C:8C:29:C3:F7:46.
- R2: inventario TQT-R2-V30-0039, anuncio TQT_R2_V2_0_0039, MAC 8C:8C:29:C3:E0:EE.
- Las 14 etapas aprobaron; cambio automático R1 a R2 por MAC sin selector Bluetooth. Final abierto (ON=0, OFF=1), MOV=4.
- Servidor confirmó coincidencia de inventario, 43 evidencias S29, métodos mac_windows_y_pb2 y mac_windows_y_err13_14.
- Resultado aprobado_con_advertencias: 28 líneas corruptas de 99 (28,3%), descartadas como evidencia. No se identificó la causa física; no se modificó temporización serial para ocultarla. release_authorized=false.

No se repitió la rutina. Antes se comprobaron conexiones BLE sin movimientos; después solo pruebas de software aisladas. No hubo programación de firmware ni escritura de eFuses.

## Verificación de software

23 pruebas Python de puente y resultado web; 14 pruebas del motor JS, incluida preservación del puerto Web Serial al cambiar/conectar BLE nativo; humo sec_validacion_ui. Playwright comprobó selección 0039, conexión BLE real de R1/R2 y estado verde R2 con serial desconectado en contexto separado, sin tomar COM7. Captura fuera de Git en outputs/validacion_141/ble_solo_windows_0039_conectada.png.

Backend y adaptador incorporan pruebas de propietario, MAC, uso único, caducidad/cancelación, S29 obligatorio y rechazo de MAC observada fabricada por navegador. No se publican credenciales, bases ni capturas de operación en Git.

## Entorno y pendientes

Preview http://127.0.0.1:18084/monitor#/validacion, contenedor tqt-validacion141-web-1 (nombre histórico), versión 1.4.2. Base local aislada; 0039 incorporada selectivamente desde inventario real. Puente privado en %USERPROFILE%\.tqt\BLE-Preview142; no compartir config.json porque contiene su credencial.

Estado actualizado al integrar 1.4.3: se comprobó que producción corre 1.4.1, commit 76d71a1; esa base se incorporó preservando sus dos correcciones. Su despliegue requiere autorización expresa. No se cambió Programación R1/R3 ni firmware. Revisar calidad UART en otra intervención; Android y Skytec continúan pendientes.

Capacidades aplicadas: ECC backend y seguridad para autorización y evidencia del puente; CM para continuidad, checkpoint y Git. Se conservó el diseño existente.
