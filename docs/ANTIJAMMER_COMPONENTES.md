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

## Producción · 2026-11-05

- Piloto aprobado `9a9a96a`; producción de partida `5dc5d76` (incluye `8686e2d`, Centro de Administración, y etiqueta R3). GitHub y Orange Pi recibieron el merge `34f184a` como 1.4.89. El agente conserva su código operativo y solo alinea su constante de versión con la web.
- Se repitieron 89 pruebas aisladas sobre la integración y el recorrido Playwright de AntiJammer en escritorio y móvil, con ambos cálculos y CSV. No se usaron datos de producción para ejecutar las pruebas.
- Respaldo SQLite online en el propio servidor: `/backups/predeploy_1.4.89_20261105_171553.db` (UTC), 68 272 128 bytes, SHA-256 `19a73e9152b24edc15865ea02c729f9deea953de84dd9d3832ad48a620985292`, `integrity_check=ok`. Sin campañas ni trabajos activos antes de recrear exclusivamente el servicio `tqt`; el túnel mantuvo el mismo contenedor.
- Tras el cambio: contenedor saludable, API de salud interna y por HTTPS correcta, acceso público de AntiJammer servido con versión 1.4.89, API y JS privados protegidos sin sesión, ocho hashes del contenedor iguales a Git. SQLite `quick_check=ok`; comparación bidireccional de filas contra el respaldo sin diferencias en PCB AntiJammer (28), tablas de costos/materiales y PCB/tarjetas TQT (446/100).
- Consulta de producción en solo lectura: 30 componentes distintos; 27 referencias RX y 21 TX, todas con cantidad positiva y unidades compatibles. No se registraron pedidos ni movimientos para probar el despliegue.
