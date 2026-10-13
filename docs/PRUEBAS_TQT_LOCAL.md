# Pruebas TQT integradas — entorno local

## Alcance y arquitectura

Implementación local sobre GitHub main 4bfbc88 (v1.3.69), rama codex/tqt-test-station. No se publicó ni desplegó código en producción.

La sección existente /monitor#/validacion se reemplaza por Pruebas TQT. FastAPI/SQLite están en Docker local y el agente Python saliente trabaja en Windows con COM y BLE. No hay puertos entrantes del agente, Web Bluetooth ni acceso de Docker a COM. Se reutilizan sin modificar engine.py, serial_port.py, ble.py, protocol.py y reporting.py originales de TQT Test Station 0.6.3. El adaptador agent.py transmite eventos y reportes y añade guardas contra discrepancias de identidad; no modifica tiempos de firmware, ACK ni las 14 etapas.

El agente tiene una credencial dedicada y un mutex por estación. Solo acepta HTTPS o HTTP de localhost/127.0.0.1. La API aplica sesión de usuario y roles; las rutas del agente usan bearer de estación y comprueban propiedad de cada ejecución. La web conserva la protección de origen existente.

## Base real y migración

Respaldo existente obtenido del almacenamiento privado de Mini PC: tqt-20261013T090003059316Z.tar.gz. SHA256 del archivo: bca04fdaeed770af73e97b2be012bd75f220365a591c36eea6c085f2dab9256f. SQLite extraída: e677efbc6d04003fcd0ebdb9f9bcbbc46f3f475f70d9bee009908f9556fcea2e; integrity_check=ok.

El original está fuera del repositorio, en outputs/tqt_test_local/private del espacio de trabajo. La copia vive en el volumen cm-local-tqt-web_test_data. Se verificó igualdad fila por fila de tarjetas_produccion (100), pcb_inventario (300) y pruebas_historial (100) tras la prueba física; la integración no modifica estados de fabricación ni autoriza liberar tarjetas. Se conservan usuarios existentes y se añadió únicamente un operador de desarrollo local, con credenciales privadas fuera de Git.

Tablas nuevas: tqt_test_runs, tqt_test_events, tqt_test_commands y tqt_test_presence. Se reutilizan stm32_stations y las tarjetas/PCB existentes. El snapshot de inventario conserva el cotejo histórico aunque el inventario cambie después. Ejecuciones y eventos son independientes e inmutables; índices excluyen trabajos simultáneos por tarjeta y estación. La asociación verificada tarjeta_id queda nula si falla identidad/MAC; requested_card conserva qué tarjeta intentó probar el operador. No se relaciona automáticamente con una tarjeta distinta.

Se cotejan nombre y número R1, MAC firmware/BLE de R1 y R2 y el IDR real de R2; números R1 y R2 pueden diferir. Se rechazan tarjetas inexistentes, MAC ausentes/duplicadas y datos cambiados antes de iniciar. El alta y emparejamiento siguen en Inventario, sin crear identidades ficticias.

## Inicio y detención

Desde la raíz del repositorio:

```powershell
.\deploy\local-tests\local.ps1 iniciar
.\deploy\local-tests\local.ps1 validar
.\deploy\local-tests\local.ps1 estado
.\deploy\local-tests\local.ps1 detener
```

Web: http://localhost:18080/monitor#/validacion, publicada solo en loopback. El contenedor de desarrollo usa Python 3.12 sin toolchain Arduino para evitar builds pesados innecesarios; no reemplaza el Dockerfile de producción. `compose.tests.yaml` ejecuta pruebas con base temporal y sin red.

Para otra restauración, usar un respaldo cerrado y un ProjectName nuevo:

```powershell
.\deploy\local-tests\restaurar.ps1 -BackupPath C:\ruta\respaldo.db -ProjectName cm-local-tqt-web-otra-copia
```

El script valida SQLite, monta el respaldo en solo lectura y rechaza sobrescribir una base local existente. No borra volúmenes. No restaurar sobre producción ni usar `down -v` para apagar.

## Agente Windows

En la web, Descargar agente de pruebas genera un ZIP privado con config.json, módulos originales, requisitos y scripts. Extraer y ejecutar iniciar.cmd: crea una venv, instala pyserial/bleak y arranca el agente oculto; diagnóstico en agent.log. Se necesita Python 3.10+ y Bluetooth Windows disponible. El agente instalado durante esta sesión está en outputs/tqt_test_local/agent fuera del repositorio y usa la venv existente del programa aportado. No abrir Tkinter, un monitor serial ni otro agente sobre el mismo COM.

La evidencia local y la cola SQLite persistente quedan en evidence/. Un fallo de red reintenta reportes, no pruebas ni comandos. Reiniciar un agente interrumpido no reanuda movimientos automáticamente: la web clasifica la ejecución como no verificada y conserva la evidencia recibida. El agente guarda el LOG original completo; al terminar lo transmite sin modificar espacios ni saltos de línea. La cancelación solicita detener la secuencia, pero el firmware puede terminar el movimiento en curso.

## Uso

Buscar la R1/tarjeta o escanear su QR. Cargar COM, conectar, consultar STATUS y revisar S29. Buscar y conectar BLE permite control manual fuera de una prueba automática. Los movimientos manuales requieren inventario seleccionado y MAC coincidentes. La secuencia automática necesita confirmación de tarjeta/banco libre: usa Reset_44 original (restablece ajustes) y mueve el perno.

Tarjetas → detalle → Pruebas e historial abre solo las ejecuciones de esa tarjeta. Reporte: identidad, cotejo con inventario, comunicación, 14 etapas/duraciones, advertencias, parámetros y al final LOG original completo. Texto serial se inserta como texto, nunca HTML. Ofrece copiar/descargar LOG, descargar JSON con eventos y imprimir/guardar PDF. Las pruebas fallidas/interrumpidas también se conservan; no sustituyen las anteriores.

## Evidencia ejecutada

- Compose validado; imagen construida; contenedor saludable en 127.0.0.1:18080.
- 41 pruebas originales de motor/protocolo/reportes con simuladores: correctas en Docker.
- 8 pruebas iniciales nuevas de persistencia, MAC, reintentos y aislamiento: correctas; verificación final: 11 casos correctos, incluidos IDR, exclusión con programación y rechazo de tarjetas inexistentes; 22 casos STM32 correctos.
- Regresión comparada: baseline 610 tests; integración 618 tests. Ningún fallo/error nuevo. Hay 13 fallos y 29 errores existentes en este entorno Linux (catálogo/semillas no presentes, rutas Windows y comprobaciones de empaquetado/certificados); 14 casos omitidos. No se declara verde la batería completa.
- Dos pruebas físicas reales de R1 0036 en COM10 y R2 0077: 14/14 aprobadas; primera 50 tramas y segunda 52, ambas sin corrupción ni reintentos ACK, posición final abierta. Segunda coteja IDR 0077 explícitamente.
- IDs: 4f9e5a54dfd61b7eba379d0d5b5eae68 y 35ea0d0c04ac444338c45c5cc59c3f9f, tarjeta interna 354.
- LOG de la primera prueba: 20047 bytes, SHA256 65a95182a78a278a67a31be15f9e10d134d2498fa9f5b468422c19cd59e77892, idéntico en agente y descarga web.
- Historial conservado al recrear Docker. Datos originales del inventario conservados.

## Límites

La aprobación funcional no es autorización de entrega ni una certificación eléctrica. Una interrupción abrupta puede dejar solo evidencia parcial en servidor y el LOG adicional en Windows; hay que revisar la tarjeta antes de repetir. No se ocultó la deuda de regresión anterior. Los originales y bases privadas no van a GitHub. Producción, túneles y servicios de Mini PC/Orange Pi no se modificaron.
