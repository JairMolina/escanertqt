# QA Excel mensual (agente QA-EXCEL)

Tests: `tests/test_qa_excel.py` (34 tests, datos reales en BD temporal, sin mocks de BD/openpyxl; el bloqueo de Excel se simula con un handle exclusivo de Windows `CreateFileW` con share=0).

## Bugs encontrados y corregidos

| Bug | Sev. | Causa | Arreglo | Test |
|---|---|---|---|---|
| Firmware que empieza por `=` (p. ej. `=HYPERLINK(...)`) se guardaba como FÓRMULA (inyección de fórmulas; sumaba una fórmula #2111 al libro) | media | openpyxl convierte en fórmula cualquier str que empiece por `=` | `excel_sync.py` `_texto()` (fuerza `data_type="s"`) usada en D, E, G | `TestDatos.test_09` |
| Tarjeta 101+ (o PCB que no cabe) solo aparecía en `omitidas`, sin aviso legible | media | `avisos` no las mencionaba | `excel_sync.py` `export_to_excel`: aviso con máximos y lista de IDs | `TestDatos.test_03` |
| `POST /api/excel/sync` con `excel_path` permitido pero inexistente lo IGNORABA y escribía en la ruta por defecto | media | `create_monthly_excel(mes, anio)` sin `target_path` | `excel_dymo.py` `ejecutar_sync_excel`: pasa la ruta pedida | `TestApiRutas.test_03` |
| PCB DISPONIBLES/FALLA con MAC y sin tarjeta no se exportaban al Catálogo (se perdían en exportar->importar) | media | el catálogo solo se llenaba desde las tarjetas | `excel_sync.py` `_pcb_sueltas()` + uso en `export_to_excel` (con aviso si no caben) | `TestDatos.test_05` (incluye round-trip) |

## Verificado y correcto (sin cambios)
- OPC completo de plantilla y salida (content-types, rels, sin huérfanos, sharedStrings, XML bien formado, sin entradas duplicadas), incl. calcChain: openpyxl la elimina limpiamente (sin referencias colgantes) y se fuerza `fullCalcOnLoad="1"`.
- Mismas 4 hojas y orden, estados, definedName `FirmwareList`, tablas (2), anchos/alto de fila/estilos por celda, validaciones estándar+x14 (tipo y rango), reglas CF (tipos; openpyxl fusiona bloques con el mismo `sqref`, mismo nº de reglas), 2110 fórmulas idénticas, 500 fórmulas array (`t="array"`) conservadas.
- Segundo/tercer sync: byte-idéntico en todas las partes salvo `docProps/core.xml` (fecha de modificación).
- 0, 1, 100 tarjetas; 101 (omitida + aviso); impares (R1 0021), ID fuera de lista, V31 (B literal + aviso, C/F intactas), R3 (aviso), MAC en cualquier formato -> canónica, tarjeta incompleta, todos los estados de prueba (solo bitácora J:AA, B:G siguen fórmulas), >15 IDs por fila de bitácora, acentos/`<&"`.
- Operación: atomicidad (fallo de `os.replace` deja original y sin `.tmp`), 423 con archivo abierto (motor y API, original intacto, sin residuos), `.bak` = versión previa, 4 syncs concurrentes (motor y API), 12 meses en español, mes inválido, plantilla ausente, Excel corrupto (500, original intacto), archivo inexistente.
- Rutas: `..`, UNC, unidad distinta, `.xls/.xlsm/.xlsx.exe/sin extensión`, junction fuera de la carpeta (400 en sync/import/create-monthly/verify/admin export).
- Import: original del Escritorio (copia) -> 0 tarjetas fantasma; round-trip con impares, V31 y pruebas; celdas con espacios/minúsculas/guiones; MAC duplicada reportada en `errores` y nunca guardada dos veces; idempotente.
- `/api/admin/export/excel`: mismo contenido celda a celda que el sync, no toca el mensual ni su `.bak`, 401 sin token.

## No verificable
- **LibreOffice/Excel de escritorio no disponibles** (`soffice` no está en PATH): no pude abrirlo con un motor real. La garantía de "sin reparar archivo" es por validación estructural propia (OPC + XML + calcChain), no por Excel.
- Lo que openpyxl descarta y no se puede recuperar: `xl/metadata.xml` y atributo `cm` (las 500 arrays dejan de ser "dinámicas" y son CSE `{=...}`; LOOKUP(2,1/..) da el mismo resultado), `webextensions` (panel de complemento), `xr:uid`, `calcChain`. No afectan datos/fórmulas.
- Valores en caché de fórmulas: no hay (openpyxl); Excel recalcula al abrir. Visores que no calculan (vista previa móvil/Outlook) mostrarán celdas de fórmula vacías.

## Riesgos abiertos / preguntas
1. **Filas obsoletas**: si se disuelve/borra una tarjeta ya exportada, el sync NO limpia su fila de Producción (E, firmware, fechas quedan; la plantilla trae E prefijado) ni su MAC en el Catálogo (ahora la PCB sigue apareciendo como suelta con su MAC, lo cual es correcto). Limpiar es riesgoso: si el operador tecleó datos a mano en un Excel no importado, un sync los borraría (y el `.bak` solo guarda la versión anterior). ¿Se quiere que el sync trate la BD como única fuente de verdad y limpie esas filas? Habría que marcar qué filas escribió el sistema.
2. La bitácora de Pruebas (J:AA) SÍ se reescribe entera en cada sync (decisión previa): filas manuales del usuario ahí se pierden.
3. `ruta_permitida` admite todo el Escritorio del usuario y el directorio del proyecto (otro agente añadió un bloqueo a `templates/`, lo que rompió `test_excel_dymo.test_04_api_verify` al usar la plantilla como `excel_path`; no es de mi área, revisar).
4. `get_template_path` cae al Excel del Escritorio si falta la plantilla; hoy ese archivo está vacío (igual a la plantilla) pero si un día tuviera datos se copiarían a los meses nuevos.
5. Existe `C:\Users\SKYGUARDIAN\Desktop\Control_Produccion_TQT_Octubre_2026.xlsx` (no lo creé yo; probablemente una prueba previa apuntando al Escritorio). No lo toqué.

## Suite completa (última corrida)
`Ran 301 tests`: fallos ajenos a mi cambio: `test_excel_dymo.test_04_api_verify` (bloqueo de carpeta de plantillas de otro agente) y `test_qa_dymo...test_27` (otro agente). `test_admin.test_22` falló una vez por `.bak` que dejaba mi test en la carpeta compartida; corregido con limpieza en `TestApiRutas.tearDownClass`; tras ello `test_qa_excel + test_admin` = 58 OK.
