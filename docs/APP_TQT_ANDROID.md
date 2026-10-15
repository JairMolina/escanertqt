# TQT: especificación y prompt para implementar la aplicación Android

Fecha de la solicitud: 2026-10-15. Nombre de la aplicación: **TQT**.

Estado: requisitos documentados; aplicación, API offline y FW 4.3 todavía no implementados. Este documento pertenece al mismo proyecto de la web y es el punto de partida para su implementación. No implica autorización para desplegar, grabar hardware o modificar producción.

## Instrucción de trabajo

Desarrollar una aplicación Android para actualizar tarjetas **TQT R2 ESP32** por Bluetooth BLE, integrada con el inventario web. Primero recuperar memoria, inspeccionar las fuentes y presentar el diagnóstico, la arquitectura y las decisiones pendientes. Después implementar por etapas verificables. No sustituir contratos existentes por suposiciones ni ampliar a R1/R3 sin solicitud.

Leer `AGENTS.md`, `docs/CODEX_ESTADO.md` y los avances relevantes de `docs/CODEX_HISTORIAL.md`. Consultar Git y comparar con la versión real del servidor antes de modificar: no sobrescribir cambios locales ni asumir que esta referencia sigue siendo la última versión.

## 1. Problema y resultado esperado

Actualmente una base genérica se instala por USB y la web puede asignar la identidad, personalizar el firmware y actualizar la R2 mediante OTA Bluetooth rápida. Necesitamos ese mismo proceso desde Android, online y offline, con registro automático de resultados al recuperar internet.

La web sigue siendo la fuente principal de inventario, identidades, firmware y permisos. La aplicación no debe crear un inventario independiente ni exigir copiar claves, editar JSON o corregir registros manualmente. El operador selecciona una tarjeta, programa, verifica y continúa con la siguiente.

Objetivos:

- Con internet: actualizar por BLE y registrar inmediatamente el resultado en la web.
- Sin internet: actualizar unidades previamente autorizadas y guardar resultados duraderamente.
- Al recuperar conexión: sincronizar automáticamente sin duplicados ni pérdida de evidencia.
- Conservar la misma identidad de cada tarjeta entre web, app y futuras actualizaciones.
- Permitir nuevas versiones funcionales, empezando por la evolución de 4.2 a 4.3; FW 5 es solamente un ejemplo futuro y no existe aún.

## 2. Referencias comprobadas al redactar

- Web: https://inventariotqt.site.
- Repositorio: https://github.com/JairMolina/escanertqt.
- Checkout: `C:\Users\usuario\Mi unidad\Inventario TQT\work\escanertqt_publish`.
- Rama de referencia: `codex/r2-integracion-1387`.
- Despliegue documentado: web **1.3.88**, commit `abaee0b80ed048101bae048e028a642576f87cee`, Orange Pi con Docker Compose.
- Checkpoint posterior de referencia: `ff4a901`.
- Producción: `/home/orangepi/escanertqt`, Compose `servidor/compose.yml`, servicio `tqt`. No modificar servicios compartidos, red o Cloudflare como parte rutinaria de esta app.

Estas referencias describen el estado conocido, no reemplazan una consulta actual. Conservar R1, R3, DYMO, J-Link, estación de pruebas y otras funciones existentes.

## 3. Base general FW 4.0: decisión cerrada

La base ya está terminada. El usuario decidió utilizar siempre el **BIN fijo**, igual para todas las R2 HW compatibles. No recompilar por unidad ni modificar la base al crear versiones funcionales nuevas.

- Instalación inicial por USB–TTL con BOOT + RESET.
- Nombre sin asignación: `TQT_R2_V30_XXXX`.
- OTA Bluetooth rápida y ancla pública del firmante de altas.
- Sin número de unidad asignado.
- Escritura de eFuses desactivada; debe seguir desactivada.

BIN:

```text
C:\Users\usuario\Mi unidad\ESP32_BLE_SERIAL\TQT_R2_Programacion_Web_y_Local\FW_GENERAL_4_0\BASE_GENERAL_4_0.bin
```

SHA-256 del BIN fijo entregado:

```text
05f89f68497bf92cbe4bc80dee9c4d101e59fc22202d8e2d5e2945035f14a487
```

Grabador repetitivo:

```text
C:\Users\usuario\Mi unidad\ESP32_BLE_SERIAL\TQT_R2_Programacion_Web_y_Local\FW_GENERAL_4_0\TQT_R2_BASE_V4_0_GENERIC\programar_base.ps1
```

Desde esa carpeta: `./programar_base.ps1 -Puerto COM4` (usar el puerto real). El script verifica el BIN fijo, espera al operador por cada tarjeta y comprueba la escritura. Una tarjeta totalmente vacía necesita esta instalación USB antes de cualquier operación BLE.

## 4. Programa actual 4.2 y evolución 4.3

Programa actual: FW **4.2**, HW **3.0**, OTA rápida. Próxima evolución prevista: **4.3**. No inventar otros cambios de comportamiento funcional, comandos o relevadores: se definirán por separado.

Fuentes versionadas: `firmware/esp32_r2/TQT_R2_V4_2/`.

Copia editable pública:

```text
C:\Users\usuario\Mi unidad\ESP32_BLE_SERIAL\TQT_R2_Programacion_Web_y_Local\FW_ACTUAL_4_2\TQT_R2_V4_2
```

La plantilla se personaliza con nombre exacto del inventario, HW, FW real y credencial propia de la unidad. Ejemplo: **`TQT-R2-V30-0067`**. Conservar guiones y ceros iniciales; no sustituir por `TQT_R2_V30_0067`.

Leer HW/FW del perfil del firmware; no deducirlos únicamente del nombre del archivo. Conservar la credencial al actualizar de versión; el operador no debe editarla. El catálogo ofrece selección de versión y por defecto la más reciente compatible/autorizada.

El preparador offline de laptop existe, pero no hay importador automático de identidades offline al servidor. No presentar esta sincronización como ya implementada. Tampoco existe todavía un contrato universal para cargar por Arduino y conservar automáticamente cualquier identidad: inspeccionar y diseñar antes de prometerlo.

## 5. Fuentes y API que deben revisarse

Backend:

```text
app/routers/esp32.py
app/services/esp32_firmware.py
app/services/esp32_ota.py
app/services/r2_enrollment.py
app/services/r2_programming.py
app/database/inventario.py
```

Web:

```text
app/static/js/esp32_ota.js
app/static/js/sec_programacion.js
```

Firmware:

```text
firmware/esp32_r2/TQT_R2_V4_2/tqt_ota.cpp
firmware/esp32_r2/TQT_R2_V4_2/tqt_profile.cpp
firmware/esp32_r2/TQT_R2_BASE_V4_0_GENERIC/tqt_enrollment.cpp
```

Rutas actuales:

```text
GET  /api/esp32/firmwares
GET  /api/esp32/ota/capability/{pcb_id}
POST /api/esp32/enroll/prepare/{pcb_id}
POST /api/esp32/enroll/result/{identifier}
POST /api/esp32/ota/prepare/{pcb_id}
POST /api/esp32/ota/result/{identifier}
POST /api/esp32/ota/cancel/{identifier}
```

La autenticación actual utiliza sesiones web. Diseñar autenticación Android reutilizando usuarios, permisos y límites de acceso; no crear una cuenta administrativa compartida.

UUID del servicio OTA actual, a confirmar en las fuentes antes de implementarlos:

```text
Servicio d45a0001-6a76-4e41-9f38-a7043f0ec069
INFO     d45a0002-6a76-4e41-9f38-a7043f0ec069
CONTROL  d45a0003-6a76-4e41-9f38-a7043f0ec069
DATA     d45a0004-6a76-4e41-9f38-a7043f0ec069
STATUS   d45a0005-6a76-4e41-9f38-a7043f0ec069
```

El contrato existente usa credencial por unidad, INFO autenticado con HMAC, nonce de sesión, manifiesto autenticado y transporte cifrado. El alta genérica utiliza ECDH y ticket firmado. Revisar tamaños, orden de bytes, hashes, perfiles y particiones en las fuentes; no reconstruir el protocolo de memoria.

## 6. Flujo común de programación

1. Seleccionar tarjeta del inventario y firmware compatible.
2. Conectar e identificar físicamente la R2.
3. Comprobar nombre, identidad, HW, MAC cuando corresponda y capacidad real OTA.
4. Autorizar y preparar la imagen personalizada.
5. Transferir, verificar integridad y activar la imagen.
6. Reiniciar, reconectar y verificar nuevo arranque, imagen, identidad y versión.
7. Registrar como verificado solamente al cumplir el contrato completo.

No marcar éxito solamente por terminar el envío. Si falta confirmar el reinicio, mantener un estado recuperable pendiente de verificación, sin indicar automáticamente una reinstalación USB.

El estado «sin programar» en inventario no demuestra que físicamente no haya OTA: el usuario puede haberlo borrado para simular una unidad nueva. Comprobar la tarjeta, sin eliminar validaciones de identidad. Versiones antiguas o incompatibles deben recibir instrucciones claras de recuperación USB.

## 7. Arquitectura Android propuesta

Evaluar app nativa **Kotlin + Jetpack Compose**, salvo que la inspección justifique otra opción. Consultar documentación oficial actual antes de fijar herramientas, permisos BLE y servicios de segundo plano.

Componentes:

- BLE nativo separado de la interfaz.
- Casos de uso de programación, alta, verificación y recuperación.
- Cliente API y autenticación.
- Base local persistente y cola durable de resultados.
- Gestor de sincronización con reintentos adecuados.
- Protección de material sensible mediante Android Keystore y cifrado apropiado.
- Separación explícita de producción y pruebas.

Entregar APK instalable, código fuente mantenible y procedimiento reproducible de compilación. La app nativa no se ejecuta en Docker; las ampliaciones web/API sí deben conservar la arquitectura Docker existente.

## 8. Online y equivalencia con la web

Iniciar sesión, buscar o escanear tarjeta, elegir firmware, conectar, actualizar y verificar. Mostrar siempre el nombre del inventario y el dispositivo conectado para evitar equivocaciones.

Reutilizar la lógica de negocio que hoy registra OTA web: inventario, MAC/FW cuando corresponda, historial, estado de programación/verificación, eventos, conteos y notificaciones pertinentes. Obtener la lista exacta del backend. No duplicar reglas divergentes entre Android y navegador.

## 9. Paquete de trabajo offline

Con internet, descargar únicamente tarjetas autorizadas, firmware, metadatos, revisiones, identidades/capacidades necesarias y límites de autorización. No descargar la base completa ni secretos de unidades ajenas al trabajo.

Sin internet, permitir programación de unidades realmente preparadas para ese modo. Guardar de forma durable:

- UUID de operación, tarjeta, identidad física y origen del paquete.
- Firmware origen/destino, identificadores, hashes y perfil personalizado.
- Evidencia previa y posterior al arranque.
- Operador, dispositivo Android, método y revisiones conocidas.
- Tiempos, errores, cancelaciones y estado de sincronización.

Estados visibles mínimos:

```text
Pendiente de programar
Enviando
Verificando nuevo arranque
Programada y verificada · pendiente de sincronizar
Sincronizada
Fallida
Pendiente de verificar
Conflicto que requiere revisión
```

Perder internet no debe impedir completar una operación totalmente preparada y autorizada para offline. Una programación física exitosa no puede perderse por fallar el registro remoto.

## 10. Decisiones criptográficas obligatorias antes de implementar offline

No basta con guardar una respuesta OTA preparada online: el contrato actual liga autorización/cifrado al nonce real de sesión y los trabajos caducan. Diseñar cómo autorizar sesiones nuevas sin servidor y cómo validar sus resultados después.

Comparar alternativas indicando compatibilidad 4.2, cambios necesarios en 4.3, alcance de credenciales, protección, revocación offline y garantías reales. No exportar al celular la clave privada general de altas. No eliminar HMAC, nonces, cifrado o comprobación de identidad para facilitar offline.

Si Android recibe la clave simétrica de una unidad, pasa a ser participante de confianza capaz de generar pruebas con ella. No describir esas pruebas como atestación independiente e imposible de falsificar desde el celular. Diferenciar firma de paquetes/autorizaciones, validación del dispositivo y confianza en el operador/app.

### Límite del primer alta offline con base 4.0 fija

La base verifica al firmante del servidor y utiliza información efímera de la sesión. Descargar inventario o reservar números no produce por sí solo un ticket utilizable después contra cualquier tarjeta XXXX.

No entregar la clave privada global al celular ni cambiar silenciosamente la base fija. Determinar lo que permite realmente el contrato. Si el primer alta completamente offline no es compatible de forma segura, mantener **alta inicial online una vez y actualizaciones posteriores offline** como flujo compatible y explicar el límite.

No confundir alta de una tarjeta genérica con actualización de una unidad ya identificada. Cualquier ampliación que requiera cambiar el modelo de confianza o la base congelada debe presentarse y acordarse antes.

## 11. Sincronización automática y conflictos

Sincronizar al recuperar conexión y al abrir la app, respetando restricciones reales de Android. No prometer ejecución ilimitada con la aplicación detenida forzosamente.

El servidor debe:

- Procesar idempotentemente cada UUID de operación y evitar duplicados.
- Validar identidad, autorización y evidencia; no aceptar un simple booleano de éxito.
- Aplicar cambios transaccionalmente y conservar historial.
- Distinguir recepción de un evento histórico de certeza sobre el estado físico actual.
- Evitar que un resultado offline antiguo sobrescriba una actualización más reciente.
- Resolver o señalar conflictos usando revisiones y relaciones entre operaciones, no solo la hora del celular.

Diseñar el caso de dos celulares que descargan la misma tarjeta y trabajan sin conexión. No prometer exclusión global offline; contemplar asignación previa y detección de conflictos. Separar aceptación del historial de actualización del estado actual.

## 12. UX y rendimiento

Interfaz en español orientada a producción: tarjeta visible, firmware instalado/objetivo, conectividad, preparación offline, progreso real, velocidad, tiempo estimado, detener, recuperar verificaciones pendientes, pendientes de sincronizar y siguiente tarjeta.

Mantener OTA rápida: negociar MTU, adaptar paquetes, controlar flujo y limitar colas. Evitar consultas por cada paquete o esperas artificiales. Tratar reinicios, GATT desconectado y referencias obsoletas de servicios/características. Si el protocolo no admite reanudar una transferencia, reiniciar de forma segura; no afirmar reanudación inexistente.

No mover relevadores ni salidas como parte rutinaria de verificación. Conservar los servicios y comandos operativos actuales de la R2.

## 13. Pruebas y seguridad operativa

Verificar:

- OTA online y todos sus efectos en la web.
- OTA offline y sincronización posterior.
- Reenvío, duplicados, conflictos y resultados fuera de orden.
- Cierre de app, reinicio Android y persistencia de pendientes.
- Pérdida de red y desconexión BLE en distintas etapas.
- Reinicio no confirmado y recuperación sin reinstalar innecesariamente.
- Imagen corrupta, HW incorrecto, tarjeta equivocada y autorización inválida.
- Inventario «sin programar» con OTA física funcional.
- Migración desde nombres antiguos con guiones bajos.
- Compatibilidad web y BLE con versiones existentes.
- Medición real de velocidad y duración, sin prometer un tiempo no medido.

La R2 0067 fue usada con éxito en pruebas de nombre exacto y OTA 4.2. No asumir que sigue disponible o conectada. Antes de grabar, identificar unidad y pedir confirmación de banco. El usuario sostiene contactos durante USB: preparar herramientas y archivos antes de pedir conexión.

**Escritura de eFuses expresamente desautorizada.** No incluirla en FW 4.3, herramientas o pruebas. No sustituir la base productiva con fixtures locales. Probar aislado; no desplegar o reiniciar producción sin autorización específica. No llevar claves, bases, respaldos o imágenes personalizadas con secretos a Git ni a documentación pública.

## 14. Etapas y entregables

Primero entregar diagnóstico del contrato, matriz base4.0/FW4.2/FW4.3, arquitectura, decisión de autorización offline, riesgos, migraciones y cuestiones que requieren aprobación.

Después implementar por etapas:

1. Cliente Android y OTA online equivalente a la web.
2. Preparación de trabajo offline y contrato seguro aprobado.
3. Ejecución offline, verificación, persistencia y sincronización idempotente.
4. Recuperación de fallos y conflictos.
5. Cambios mínimos justificados de backend y FW4.3.
6. Pruebas reales, APK, fuentes, documentación y procedimientos de respaldo/recuperación.

El orden puede ajustarse por dependencias demostradas. No omitir validaciones críticas. Registrar resultados reales, limitaciones y siguientes pasos mediante CM, Git y memoria del mismo proyecto.

## Criterio de aceptación final

El operador puede seleccionar una R2, instalar un firmware autorizado por BLE y verificar el arranque, desde la web o TQT Android. Con conexión, el resultado queda en el servidor inmediatamente; sin conexión, permanece visible y durable hasta sincronizar automáticamente. No hay edición manual de credenciales ni duplicación de registros. Los límites del primer alta offline y de la revocación sin conexión están documentados y no se ocultan con validaciones más débiles.
