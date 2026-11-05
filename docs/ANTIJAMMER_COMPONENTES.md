# AntiJammer · Inventarios y solicitud de material

Base: main `be4e152` (1.4.87). Piloto revisado como 1.4.88 e integrado sobre producción en 1.4.89; solo se habilita en AntiJammer. No necesita migración.

- **Inventario de PCB** (`/antijammer#inventario`): placas físicas, serie, lote, estado y firmware; conserva la recepción, los filtros y las acciones existentes.
- **Inventario de componentes** (`/antijammer#materiales`): Resumen (ensambles posibles, pendientes RX/TX y mínimos), Componentes (búsqueda, BOM por tarjeta, existencias, mínimos y movimientos), Registro (movimientos y consumo por PCB) y Solicitud de material. El catálogo se edita en Costos, sin duplicarlo. Los permisos de consulta y edición siguen siendo los del módulo.
- **Solicitud**: indica RX y TX por separado o la misma cantidad para equipos completos. Para cada material de producción se suman sus cantidades por tipo multiplicadas por las placas solicitadas. Los recurrentes y los materiales históricos retirados no entran. Se usa la unidad del catálogo, sin convertir a paquetes de compra. El CSV contiene solo renglones con cantidad a solicitar positiva.
- **Descontar existencias**: el saldo del componente se aplica una sola vez al total. Un saldo negativo se muestra y se toma como cero material utilizable. **Ignorar existencias**: se solicita la cantidad total. Los mínimos no generan compras adicionales. El plan no escribe movimientos, activa consumos, reserva material ni crea un pedido. «Actualizar existencias» vuelve a leer el inventario y conserva el plan; la conciliación habitual del módulo no cambia.
- No se presentan compras parciales si falta la BOM de un tipo seleccionado, si falta la cantidad por tarjeta de un componente de esa BOM o si las unidades del mismo material discrepan. Corregir en Costos.

## Verificación local

Docker independiente en `127.0.0.1:18095` con datos de ejemplo. Inventario de demostración: Conector de banco (RX: 2 pza, TX: 3 pza, disponible: 12), Cable de prueba (RX: 0.25 m, disponible: 4), Relevador de prueba (TX: 1 pza, disponible: 0). Las entradas llevan la nota «Datos de ejemplo del piloto local».

Con 5 RX y 4 TX el cálculo bruto da 22 conectores, 1.25 m de cable y 4 relevadores. El cálculo con existencias pide 10 conectores y 4 relevadores. El cable queda en cero y se omite en el CSV neto.

Pruebas: `test_materiales`, `test_costeo`, `test_antijammer`, `test_inventario_tqtr`, `test_version_estaticos` y `test_qa_version_hoy` con SQLite temporal (50 pruebas). La suite histórica TQTR usa sus dos JSON de referencia locales montados en solo lectura. `tests/antijammer_materiales.playwright.js` recibe la página y la clave del entorno sintético como argumentos; verifica los dos inventarios, búsqueda, historial, ambos modos, CSV, decimales, stock cubierto/negativo, BOM inválida y móvil sin escrituras.

Para extenderlo a otro módulo, habilitar la exposición de cantidades por tipo y los controles de solicitud en ese módulo, adaptar las etiquetas de tarjetas y validar sus unidades y casos de compra con sus propios datos. No requiere compartir el stock de AntiJammer.
