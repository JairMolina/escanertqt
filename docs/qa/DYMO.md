# QA DYMO (30334, LabelWriter 550)

**Hardware real NO disponible**: no se imprimió nada. En esta PC hay un DYMO Connect real corriendo en 127.0.0.1:41951 (con una LabelWriter 450 desconectada, sin 550): no se le mandó ningún trabajo. El servicio se simuló con `page.route` (mismos endpoints StatusConnected/GetPrinters/PrintLabel que usa el framework). Tampoco se probó abrir el `.dymo` en DYMO Connect ni la fuente Consolas en la impresora.

| Bug | Sev. | Causa | Arreglo | Test |
|---|---|---|---|---|
| ZIP de lote con nombres repetidos (mismo número de tarjeta en dos lotes) | media | `TQT_<num>.dymo` sin desambiguar | `app/services/dymo_service.py` `zip_lote` (sufijo `_id<id>`) | `test_qa_dymo.py::test_27` |
| "Descargar lote" sondeaba con HEAD (405) y bajaba N archivos sueltos; enviaba `solo_finales` inexistente | media | Sonda innecesaria | `app/static/js/dymo.js` (un solo ZIP) | `qa_dymo_frontend.py` |
| Selector ofrecía impresoras de cinta (LabelManager) | media | filtro `/DYMO/` en el nombre | `app/static/js/dymo_connect.js` `esLabelWriter` | `qa_dymo_frontend.py` |
| Tarjeta inicial = la primera de la lista aunque fuera INCOMPLETA (Imprimir deshabilitado) | baja | | `dymo.js` `load()` | `qa_dymo_frontend.py` |
| Vista previa a 3x cortada en celular (390 px) | media | zoom fijo 3x | `dymo.js` (zoom inicial según ancho) | captura `10_celular_390.png` |
| Caché: `dymo.js`/`dymo_connect.js` bumpeados a `?v=20260924r/q` en `dymo_preview.html` | - | | | |

## Pasó
- Trama: impar 0021+0010, V31/V5/V100/V7, MAC faltante (línea vacía, IDENTIFICACION -> FINAL al completar), incompleta, MAC mayúscula en BD -> minúscula, ceros, 404 en todas las rutas, PCB sustituida tras falla (refleja la PCB actual) y sin reemplazo (INCOMPLETA).
- Geometría (SVG rasterizado con PyMuPDF a 300 dpi): 674×378 px, nada dentro de los 3 mm, QR ≥20 mm con silencio, QR decodificado con ZXing = trama exacta (peor caso `TQT-R1-V31-9999`/`ff:ff:ff:ff:ff:fe` y variantes), texto sin desbordar, solo #000/#fff, fuente ≥7 pt.
- XML: `.dymo` con los mismos elementos y orden que los ejemplos oficiales (`tests/fixtures/dymo_oficial/`, de dymosoftware/DCD-SDK-Sample: AddressObject y BarcodeObject), `.label` v8, escapes `&<>"'`, `texto_como=address`, cabeceras de `/archivo`, ZIP de 100, ids repetidos/vacíos/inexistentes.
- Frontend (50 comprobaciones, 1280×800 y 390×844, capturas en `docs/qa/dymo_img/`): estados no detectado / detectado / desconectada / sin impresoras / celular; una petición PrintLabel por tarjeta con XML idéntico a `/xml` y `Copies` correcto (límites 1–99); doble clic = 1 petición; error del servicio con mensaje; lote finales (2) vs todas (4); `.dymo` descargado; `window.print` nunca invocado; consola limpia (salvo ERR_CONNECTION_REFUSED del sondeo de puertos 41952-41960 del framework, esperado).

## Hallazgos / riesgos abiertos
- **`cv2.QRCodeDetector` (OpenCV 5.0) NO decodifica el QR del peor caso aunque es válido** (ZXing y móviles lo leen; sí decodifica la trama canónica). Los tests usan ZXing (`pip install zxing-cpp`; se omiten si falta).
- La vista previa web usa IBM Plex Mono 7.5 pt (aproximación); el `.dymo` usa Consolas 8 pt. Los módulos del QR en el SVG caen en fracciones de píxel (bordes con antialias en rasterizado; decodifica igual).
- Sin verificar: aceptación de `TextObject` por DYMO Connect (usar `?texto_como=address` si falla), `LabelName=SmallMultipurpose`, tamaño físico del módulo QR impreso.
- Ejecutar el frontend: `python tests/qa_dymo_frontend.py` (puerto 8455, BD temporal, cert propio; no lo descubre unittest).

Tests: `tests/test_qa_dymo.py` (30). Suite completa: ver informe final.
