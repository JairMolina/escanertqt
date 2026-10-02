# Etiquetas DYMO LabelWriter 550 — formato 30334

Impresora: **DYMO LabelWriter 550** (térmica directa, cabezal de 300 dpi, solo negro). Etiqueta principal: **30334 Multi-Purpose**, 2-1/4" × 1-1/4" = **57 × 32 mm**, apaisada. La 30252 (89 × 28 mm) queda como secundaria (`label_format=30252`).

## Trama (texto impreso y contenido del QR)

```
TQT-R1-V30-0021
70:4b:ca:5b:9f:6e
TQT-R2-V30-0010
70:4b:ca:5b:9c:a2
```

Cuatro líneas separadas por `\n`, sin salto final. Nombre y versión son los **reales de cada PCB** (una R1 en V31 imprime `V31`). MAC en **minúsculas** con `:`. La R3 no aparece. Si falta una MAC, esa línea sale vacía (no se inventa).

## Estados de etiqueta

| Estado | Condición | ¿Imprimible? |
|---|---|---|
| `INCOMPLETA` | falta R1 o R2 | no |
| `IDENTIFICACION` | R1 y R2 asignadas, pero falta alguna MAC, o una PCB no está FUNCIONAL, o calidad no liberable | sí, con aviso |
| `FINAL` | ambas MAC válidas, ambas PCB `FUNCIONAL`, calidad no detenida (regla de la hoja *Etiquetas* del Excel) | sí (`LISTA PARA IMPRIMIR`) |

## Geometría (a 300 dpi: 1 mm = 11.81 puntos)

- Zona segura: **1.5 mm por lado** → área útil 54 × 29 mm (638 × 343 puntos). Nada se imprime en el borde ni pegado al borde de avance.
- **QR a la izquierda**: nivel de corrección **M**. El payload de 4 líneas (≈ 67 caracteres) da **versión 5** (37 × 37 módulos); con nivel L saldría en versión 4. Módulo de **7 puntos** (0.59 mm; nunca menos de 4) + zona de silencio de 2 módulos = **24.3 mm** de lado, centrado en vertical.
- **Texto a la derecha** (28.2 mm de ancho): **Consolas 8.5 pt negrita**, 4 líneas. El peor caso (`TQT-R1-V31-9999` / `ff:ff:ff:ff:ff:fe`) mide 26.4 mm de ancho y 14 mm de alto: cabe con margen. Courier New (28.8 mm) no cabría, por eso se usa Consolas (viene con Windows).
- Solo blanco y negro puros: sin grises ni degradados; ningún texto menor a 7 pt.
- La vista previa (`/api/dymo/preview/{id}` y `/api/dymo/svg/{id}`) está a escala real 57:32 con la zona segura punteada.

## Qué archivo abre cada programa (con fuente)

| Extensión | Programa | Contenido |
|---|---|---|
| **`.dymo`** | **DYMO Connect** (el software de la LabelWriter 550) | `<DesktopLabel Version="1"><DYMOLabel Version="3">…`, unidades en **pulgadas** |
| `.label` | DYMO Label v8 (DLS, LabelWriter 4xx/Twin Turbo…) | `<DieCutLabel Version="8.0" Units="twips">` |

Fuente: repositorio oficial `github.com/dymosoftware/DCD-SDK-Sample` → `JavaScript/PreviewAndPrintLabel/` trae la misma etiqueta en los dos formatos (`PreviewLabelFramework.dymo` = DYMO Connect, `PreviewLabelFramework.label` = DYMO Label v8) y `VisualBasic_Sample/.../samplelabel.dymo` (con un `BarcodeObject`). Su README indica que *"abrir una etiqueta creada con DYMO Label Software, con DYMO Connect instalado, convierte la estructura DLS en una etiqueta DYMO Connect"* y que `label.isDCDLabel()` valida que el contenido es una etiqueta DYMO Connect. El framework JavaScript (`dymo.label.framework.init / checkEnvironment / getPrinters / openLabelXml / printLabel`) está en `github.com/dymosoftware/dymo-connect-framework` y habla con el servicio web local de DYMO Connect (`https://127.0.0.1:41951…41960`).

Para la 550 se usa **`.dymo`**. Un `.label` también lo abre DYMO Connect (lo convierte), pero no es el formato nativo.

## Endpoints

| Ruta | Para qué |
|---|---|
| `GET /api/dymo/label/{tarjeta_id}` | datos, estado, trama, geometría, `dcd_xml` y `dymo_xml` |
| `GET /api/dymo/label/{tarjeta_id}/xml` | XML crudo para `dymo.label.framework.openLabelXml(xml)` (`?tipo=label` = v8) |
| `GET /api/dymo/label/{tarjeta_id}/archivo` | descarga `TQT_<num>.dymo` (`Content-Disposition: attachment`, `application/octet-stream`); Windows lo abre con DYMO Connect |
| `GET /api/dymo/lote/archivo?ids=1,2,3` | ZIP con un `.dymo` por tarjeta |
| `GET /api/dymo/batch-labels?modo=final\|identificacion\|todas` | cola de etiquetas |
| `GET /api/dymo/preview/{id}`, `/svg/{id}` | vista previa a escala real |

## Objetos con nombre

`QR` (BarcodeObject, `BarcodeFormat=QRCode`, dato = trama de 4 líneas) y `TEXTO` (TextObject con 4 `LineTextSpan`). Sirven para `label.setObjectText('TEXTO', …)` si algún día se quiere una plantilla fija con datos variables.

## Lo que NO se pudo verificar (sin DYMO Connect ni impresora en esta PC)

1. El XML `.dymo` copia **exactamente** la estructura de los ejemplos oficiales, pero el SDK solo trae `AddressObject` y `BarcodeObject`. El objeto `TEXTO` usa `TextObject` con la misma forma que `AddressObject` (sin `BarcodePosition`). Si una versión de DYMO Connect lo rechazara, usar `?texto_como=address` (emite `AddressObject`, verificado en el ejemplo).
2. `LabelName=SmallMultipurpose` (el `Id` de la 30334 en DYMO Label v8) y el tamaño de módulo del QR: en DYMO Connect el módulo depende de `Size`/caja del objeto; el diseño fija la caja a 20.8 mm pero la impresión real debe medirse con una etiqueta de prueba y un lector.
3. Fuente Consolas instalada en la PC de la impresora (si no, DYMO sustituye y podría reducir el texto por `AlwaysFit`).
4. Nivel de corrección: en el `.label` v8 se usa `<ECLevel>1</ECLevel>` (M, según la numeración L=0, M=1, Q=2, H=3); no está documentado en los ejemplos.

**Prueba recomendada antes de imprimir un lote:** imprimir una etiqueta desde `/api/dymo/label/{id}/archivo`, leerla con el celular (debe dar las 4 líneas) y medir que nada toca el borde.

## Impresión directa: DYMO Label v8 (DLS) vs DYMO Connect (actualizado v1.2.13)

El framework JS habla con el servicio local que tenga la PC: **DYMO Label Software v8** (`DYMO.DLS.Printing.Host.exe`, LabelWriter 450/4xx) o **DYMO Connect** (550). DLS solo acepta `<DieCutLabel>`; Connect acepta `<DesktopLabel>` (y convierte `.label`). El framework solo devuelve "Error: 400" sin detalle, así que la app prueba v8 y luego Connect. Referencia v8 verificada con `RenderLabel` del servicio: `Id=Small30334`, `PaperOrientation=Portrait`, `RoundRectangle 3240x1800`, `BarcodeObject` con `TextFont` (no `Font`). Diagnóstico rápido: `curl -sk https://127.0.0.1:41951/DYMO/DLS/Printing/GetPrinters`.

**QR en v8 (v1.2.14):** el servicio DLS ignora la caja de un `BarcodeObject` y usa un tamaño fijo (Small 10.8 / Medium 13.6 / Large 16.2 mm medidos con `RenderLabel`). Por eso el QR de la `.label` v8 es un `ImageObject` PNG 1 bit con módulos de 7 puntos exactos (24.3 mm); en la `.dymo` de DYMO Connect sigue siendo `BarcodeObject`.
