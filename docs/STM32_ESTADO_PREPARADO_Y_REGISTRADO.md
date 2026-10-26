# Datos preparados y estado registrado del STM32 — web1.4.43

## Contrato visual

Izquierda: Datos que se van a programar. Nombre/identidad, pareja, HW/FW y CRC proceden del HEX seleccionado y el inventario actual. Es una propuesta de grabación y cambia al elegir otro firmware.

Derecha: datos independientes de la propuesta. GET /api/stm32/estado/{pcb_id} no recibe firmware_id, no abre J-Link y no crea trabajos. Un cambio de selección solo puede actualizar la propuesta; no certifica una instalación.

- Última programación verificada: trabajo persistido de esa PCB con estado verified, resultado verified=true, hashes válidos y coincidentes, UID válido y tipo correcto. Nombre/R2/MAC/HW/FW vienen de la identidad archivada del trabajo, no de la pareja actual. Fecha es la del resultado verificado.
- Último registrado: si solo existe firmware en inventario, se indica su origen y la fecha de bitácora correspondiente si está disponible. No se presenta como lectura física. Si no hay fecha, aparece No disponible.
- Sin verificar: sin firmware registrado ni verificación válida. Si hay un intento posterior fallido/desconocido/en ejecución, se advierte que la Flash actual puede diferir del último registro. Durante la grabación no se adelanta el firmware elegido.

La evidencia es histórica. No demuestra que no haya habido cambios externos posteriores. El nombre de Flash verificada no equivale necesariamente al nombre activo de EEPROM, que este flujo conserva. La interfaz lo indica; no se añadió lectura física automática ni una detección de EEPROM.

Al terminar con resultado verificado se vuelve a consultar el estado. Un error o cancelación no se convierten en una nueva versión instalada. Los datos actuales del inventario tampoco reemplazan la identidad de una Flash archivada.

## Verificaciones

54 pruebas Python de programación/catálogo/estado, incluidas6 nuevas de estado: sin dato, inventario/fecha, preview sin escritura, cambio solo tras resultado verificado, error posterior, identidad archivada distinta del inventario, registros falsos/malformados, R3 verificada y autenticación. La batería de6 se volvió a ejecutar al ampliar el caso R3; todas correctas.

Playwright QA aislada:5 grupos del estado (alternar4.3/4.4 sin grabar; sin datos; identidad histórica; fallo; verificación) y6 grupos de regresión del agente fijo. Dos trabajos del ensayo de estado fueron interceptados y simulados; no llegaron a agentes reales. Cero erroresJS y sin desborde a390px. La plantilla común conserva el contrato de R2 y añade solo propiedades opcionales para STM32.

No se programó ni se leyó hardware. FW4.4 sigue beta y4.3 sigue la opción aprobada predeterminada. Usuario autorizó ajustes, despliegue y actualización de memoria. La transferencia de las tres capturas queda pendiente de la respuesta específica; no se transfieren sin ella.

Capacidades: ECC backend/verificación y reutilización de UI existente con criterios de ui-ux-pro-max. Sin agentes auxiliares ni cambios de infraestructura.
