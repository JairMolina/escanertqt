
## 2026-10-13 20:27 UTC | 4bfbc88aa104
Avance: Pruebas TQT 0.6.3 integradas solo en Docker local; dos pruebas físicas R1 0036 COM10/R2 0077 aprobaron 14/14 con historial independiente y LOG completo; inventario original intacto.
Siguiente: Mantener desarrollo local; revisar deuda de regresión Linux preexistente y no publicar/desplegar sin autorización.
Evidencia: docs/PRUEBAS_TQT_LOCAL.md; 41 simuladores originales, 11 pruebas TQT y 22 STM32 correctas; SHA256 LOG igual entre Windows y web; baseline 610 vs integración 618 sin fallos nuevos.

## 2026-10-13 21:14 UTC | 3ca48b5d0318
Avance: Integracion local terminada en codex/tqt-test-station: commits 3129648 y 3ca48b5. Agente Windows oculto y Docker saludable en localhost:18080. Dos pruebas fisicas independientes de R1 0036 / COM10, 14/14 aprobadas, inventario original conservado. Reporte con JSON, LOG original y PDF; sensores S29 interpretados.
Siguiente: Revision del usuario en Docker local. No publicar ni desplegar sin autorizacion. Deuda de regresion previa documentada.
Evidencia: 41 pruebas originales, 11 de integracion y 22 STM32 correctas. Comparacion de regresion sin nuevos fallos; interfaz movil sin desborde y PDF de 7 paginas verificado. LOG web y original SHA256 identicos.

## 2026-10-13 21:32 UTC | 41ed4f27aeed
Avance: v1.3.70 publicada en GitHub main y desplegada en inventariotqt.site por autorizacion expresa. Commit de aplicacion 41ed4f2; Orange Pi 192.168.4.70 via MiniPc, /home/orangepi/escanertqt. Agente developer4 online, oculto y con inicio automatico. Respaldo pre-tqt-1370-20261013T212830Z verificado.
Siguiente: Uso operativo desde la web publicada; conectar COM/BLE y ejecutar solo cuando el banco este libre. Deuda de regresion previa documentada; no se realizaron movimientos adicionales durante el despliegue.
Evidencia: Contenedor healthy, API publica ok, runtime 1.3.70, cuatro tablas nuevas. 100 tarjetas y 300 PCB intactas; 22 tablas anteriores comparadas, solo heartbeat de estaciones cambia. 11 casos de integracion correctos; dos pruebas fisicas previas 14/14.
