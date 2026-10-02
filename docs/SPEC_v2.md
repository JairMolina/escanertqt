# Escaner TQT — Especificación v2 (flujo real de planta)

Fuente: descripción del usuario (23/09/2026) + foto real de una PCB. Esta especificación **reemplaza** el wizard de 4 pasos
(R1→MAC→R2→MAC) de la v1: las MAC NO vienen en etiquetas escaneables; salen al **programar** la tarjeta y se **teclean**.

## 1. Flujo real
1. **Recepción.** Llegan las PCB pedidas. Cada PCB trae grabado un QR (blanco sobre negro, **invertido**) cuyo contenido es el
   nombre canónico completo, p. ej. `TQT-R3-V30-0084` (tipo R1|R2|R3, versión `V30`, serie `0084`; la serie también va impresa debajo).
   Algunas PCB vienen seriadas y otras no (las no seriadas se dan de alta a mano).
   La cámara del celular registra **automáticamente** cada PCB que pasa frente a ella (estilo caja de supermercado), sin tocar
   nada. El operador ve la lista, y **confirma el lote de recepción** o **edita/elimina** partidas.
2. **Emparejar.** Con todas las PCB en inventario se arman tarjetas: R1 0001 + R2 0001 + R3 0001 (mismo número por defecto).
   Se etiquetan (DYMO), se sueldan, se programan, se prueban y se validan.
3. **Programar.** Al programar, R1 y R2 (solo ellas; R3 no tiene MAC) entregan una MAC que el operador **anota a mano**.
4. **Fallas y tarjetas "impares".** Muchas fallan: la PCB mala se marca FALLA y se reemplaza con otra PCB suelta del mismo tipo.
   Resultan tarjetas con números distintos, p. ej. R1 0021 + R2 0010.
5. **Pruebas** (Soldadura, Programación, Prueba PCB, Integración, Prueba Final) → LIBERADO.

## 2. Reglas de dominio
- Identidad de PCB: `tipo` (R1|R2|R3) + `version` (texto, p. ej. `30`) + `serie` (4 dígitos). `nombre` = `TQT-R{tipo}-V{version}-{serie}`.
  Única globalmente por (tipo, version, serie). **El inventario de PCB es global** (sobrantes pasan de mes); la **tarjeta** sí pertenece a un lote mensual.
- **La versión es editable**: (a) versión por defecto global para altas manuales (`GET/PUT /api/ajustes`, clave `version_defecto`, inicial `30`);
  (b) editable por PCB y en masa. Un QR trae su propia versión y esa manda al escanear; después se puede corregir.
- Ciclo de PCB (`estado_ciclo`): `RECIBIDA` (borrador de recepción, sin confirmar) → `DISPONIBLE` (confirmada, suelta) → `ASIGNADA` (en una tarjeta) ;
  además `FALLA` y `BAJA`. Reemplazar libera la anterior (a `FALLA` si se marcó falla, si no `DISPONIBLE`).
- `estado_pcb` FUNCIONAL/FALLA/PENDIENTE (de v1) se conserva, derivado de la etapa "Prueba PCB".
- Solo R1 y R2 tienen MAC. MAC única globalmente (R1 y R2 entre sí). R3 rechaza MAC. Se guarda canónica MAYÚSCULAS `70:4B:CA:5B:9F:6E`; se acepta cualquier formato al teclear.
- Tarjeta: `id_tarjeta_num` (4 dígitos, por defecto = serie de su R1, pero independiente) con hasta 3 ranuras (R1,R2,R3), cada una apunta a una PCB del inventario.
  Puede estar INCOMPLETA (ranura vacía) sin romper nada. Los nombres/MAC de la tarjeta se derivan de sus PCB (una sola fuente de verdad).
  Las MAC ya NO son obligatorias al crear la tarjeta (migrar `tarjetas_produccion`: MAC/nombres NULL permitidos, agregar `pcb_r1_id, pcb_r2_id, pcb_r3_id`).
- Migración: los datos actuales de `catalogo_pcb`/`tarjetas_produccion` se conservan (BD real hoy vacía, pero hay tests de BD heredada).

## 3. API (prefijo `/api`, JSON). Errores de negocio: 409 (conflicto/duplicado), 400 (dato inválido), 404.
### Recepción
- `POST /pcb/escanear` `{codigo, operador?, tipo_forzado?, version?}` → `{resultado:'AGREGADA'|'DUPLICADA'|'INVALIDA', mensaje, pcb?, conteos:{R1,R2,R3,total}}` (siempre 200; el resultado va en el cuerpo, para que la cámara nunca reciba errores HTTP en ráfaga). Idempotente: re-escanear la misma PCB → `DUPLICADA` con `pcb` existente (y `estado_ciclo`, `tarjeta` si tiene). Un código sin formato `TQT-Rn-Vnn-nnnn` es `INVALIDA` (salvo que llegue solo el número con `tipo_forzado`).
  Broadcast WS `PCB_RECIBIDA`.
- `GET /recepcion` → `{items:[pcb], conteos:{R1,R2,R3,total}, huecos:{R1:['0003',…],…}, avisos:[…]}` del borrador actual (`RECIBIDA`). `huecos` = series faltantes dentro del rango min–max recibido por tipo; `avisos` p. ej. "R1: 12, R2: 11 (desbalance)".
- `POST /recepcion/confirmar` `{ids?:[…], nota?, operador?}` (sin `ids` = todo el borrador) → `{confirmadas:n, resumen, avisos}`; pasa a `DISPONIBLE`. WS `RECEPCION_CONFIRMADA`.
- `POST /pcb/manual` `{tipo, version?, serie?, cantidad?=1}` → `{pcbs:[…]}`; sin `serie` toma la siguiente libre del tipo (máx+1). Nacen como `RECIBIDA`.
- `PATCH /pcb/{id}` `{tipo?, version?, serie?}` → pcb actualizada (409 si choca con otra). Si está asignada, actualiza también la tarjeta/Excel y deja bitácora.
- `POST /pcb/version` `{ids:[…], version}` cambio de versión en masa.
- `DELETE /pcb/{id}` → 204; 409 si está `ASIGNADA` (hay que desasignar antes). Elimina RECIBIDA/DISPONIBLE; el resto pasa a `BAJA`.
- `GET /pcb` `?tipo=&estado_ciclo=&q=&sin_mac=1&sin_tarjeta=1&limit=&offset=` → `{total, items:[pcb]}`.
- `GET /pcb/por-codigo?codigo=` → pcb + `tarjeta` (resumen) o 404. Sirve para escanear una PCB en Programar/Pruebas.
- `GET/PUT /ajustes` `{version_defecto}`.
- Forma de `pcb`: `{id, tipo, version, serie, nombre, mac|null, estado_ciclo, estado_pcb, origen:'QR'|'MANUAL', recibida_en, tarjeta_id|null, id_tarjeta_num|null, ranura|null}`.

### Emparejar
- `GET /emparejar/sugerencias?lote_id=` → `{completas:[{serie, r1, r2, r3}], incompletas:[{serie, faltan:['R2',…], …}], sueltas:{R1:[pcb],R2:[…],R3:[…]}}` (solo PCB `DISPONIBLE`).
- `POST /emparejar/auto` `{lote_id?, series?:[…]}` → crea una tarjeta por serie con R1+R2 (R3 si existe) → `{creadas:[tarjeta], omitidas:[{serie,motivo}]}`. Exige R1 y R2 disponibles.
- `POST /tarjetas` `{lote_id?, id_tarjeta_num?, r1_id?, r2_id?, r3_id?}` alta manual (tarjetas impares).
- `PUT /tarjetas/{id}/asignar` `{ranura:'R1'|'R2'|'R3', pcb_id|null, marcar_falla?:bool}` asigna, reemplaza o libera; la PCB previa vuelve a DISPONIBLE (o FALLA).
- `POST /pcb/{id}/falla` `{motivo?, reemplazo_id?}` marca FALLA, la saca de su tarjeta y (si hay `reemplazo_id`) asigna el reemplazo en la misma ranura.
- `DELETE /tarjetas/{id}` disuelve la tarjeta y libera sus PCB a DISPONIBLE (409 si tiene pruebas distintas de PENDIENTE salvo `?forzar=1`).
- Forma de `tarjeta` (GET /tarjetas ya existente, se amplía): lo de v1 + `r1,r2,r3` (objetos pcb|null), `completa:bool`, `sin_mac:[ 'R1','R2' ]`.
### Programar
- `PUT /pcb/{id}/mac` `{mac|null}` → pcb; 400 si formato inválido o tipo R3; 409 si la MAC ya pertenece a otra PCB (mensaje con la dueña). Bitácora.
### Etiquetas DYMO (formato nuevo, ver §5)
- `GET /dymo/label/{tarjeta_id}` conserva la forma actual pero `texto`/payload QR = las 4 líneas de §5.
### Compatibilidad
- El wizard v1 (`/api/scan/validate`, `/api/scan/pair`) queda **obsoleto**: el backend decide si lo elimina (y adapta sus tests) o lo deja marcado `deprecated`; el frontend nuevo no lo usa.
- WS nuevos: `PCB_RECIBIDA`, `PCB_ACTUALIZADA`, `PCB_ELIMINADA`, `RECEPCION_CONFIRMADA`, `TARJETA_ACTUALIZADA` (payload = objeto afectado + `conteos`/`stats`). Los de v1 siguen.

## 4. Etiqueta DYMO — trama nueva (texto EXACTO, 4 líneas, `\n`, sin línea final)
```
TQT-R1-V30-0021
70:4b:ca:5b:9f:6e
TQT-R2-V30-0010
70:4b:ca:5b:9c:a2
```
- Línea 1: nombre de la PCB R1 real de la tarjeta (con su versión real). Línea 2: MAC de R1 en **minúsculas** con `:`. Líneas 3–4: R2 igual. R3 no aparece.
- Es el texto impreso y el contenido del QR de la etiqueta. Se conserva el diseño/formatos actuales (30252 y 30334), solo cambia la trama.
- Si falta una MAC, esa línea sale vacía (no se inventa) y la etiqueta se marca como "sin MAC" en la vista previa. Estados: `IDENTIFICACION` (R1+R2 asignadas) y `FINAL` (ambas MAC presentes y PCB FUNCIONAL). Imprimir en modo IDENTIFICACION es posible con aviso. La hoja Etiquetas de Excel arma el mismo texto con CHAR(10).

## 5. Escáner (frontend)
- Lee el QR **invertido** de la foto de referencia `tests/fixtures/qr_R3_V30_0084_invertido.jpg` → debe dar `TQT-R3-V30-0084`.
  `html5-qrcode` no lee QR invertidos: usar `BarcodeDetector` nativo si existe y, si no, `jsQR` (local, `inversionAttempts:'attemptBoth'`) sobre fotogramas reducidos (recorte central ~640 px, 10–15 lecturas/s).
- Modo continuo: sin pausar la cámara. Un mismo código no se re-envía mientras siga en cuadro (y hasta ~3 s después de salir); un código ya visto en la sesión se ignora en silencio salvo un tono suave "ya registrada".
- Tono distinto por tipo (R1/R2/R3) + vibración; error/duplicada = tono grave. Latencia percibida <150 ms (tono al detectar, confirmación del servidor después).

## 6. Diseño (frontend) — dirección
Identidad: **máscara de soldadura + serigrafía**. La foto real es la referencia: fondo azul-negro profundo, texto/serigrafía blanco hueso, y un acento de **oro ENIG** (acabado de las pistas). Modo oscuro por defecto (taller), modo claro "papel serigrafía" disponible (toggle + `prefers-color-scheme`). Todo en tokens CSS.
- Paleta (ajustable con criterio, mantener carácter): suelo `#0A1020`, superficie `#121A2E`, línea `#24304D`, texto `#E9EEF5`, texto tenue `#8C9AB5`, acento oro `#D9A441`. Semánticos aparte: OK `#3FD08A`, alerta `#F2B33D`, falla `#FF5C5C`, info `#5AA9FF`. Identificar R1/R2/R3 con color **y** forma/texto (daltonismo): p. ej. R1 azul, R2 ámbar, R3 turquesa, cada uno con su chip tipo "designador de componente".
- Tipografía **local** (sin CDN; vendorizar woff2 desde fontsource/jsdelivr a `app/static/fonts/`): **Barlow Semi Condensed** (interfaz, rotulación de señalética industrial) + **IBM Plex Mono** (series, nombres, MAC; como serigrafía). Números de serie grandes en mono. Escala tipográfica fija.
- Firma visual: el visor de cámara con esquinas tipo "patrón de posición" de QR; el número de serie recién leído se muestra enorme en mono bajo el visor como la serigrafía de la placa; filas de lista tipo etiqueta de componente. Nada de gradientes morados, emojis como iconos, ni tarjetas idénticas con radio 12 y sombra por todas partes. Iconos SVG propios en línea, consistentes.
- Móvil vertical, un pulgar: barra inferior (Recibir · Emparejar · Programar · Pruebas), acciones primarias abajo, objetivos ≥48 px, contraste AA, `aria-live` en cada lectura, `prefers-reduced-motion`.
- Pantallas móviles: **Recibir** (visor arriba + contadores por tipo + lista viva; tocar partida = editar tipo/versión/serie o eliminar con deshacer; "Confirmar lote" fijo abajo con resumen de desbalances/huecos; chip de **versión por defecto** editable; "Agregar sin QR"), **Emparejar** (sugerencias por serie, emparejar en un toque, armar tarjeta impar, reemplazar PCB fallada), **Programar** (escanear PCB R1/R2 o elegir de la lista "sin MAC" → campo MAC grande con formato automático `XX:XX:…`, pegar, validar/duplicado al instante, guardar y pasar a la siguiente), **Pruebas** (ya existe; rediseñar). Escritorio: monitor con inventario, tarjetas, ediciones y sincronización Excel.

---

## 7. Cambios de contrato implementados por el backend (v2.1) — LEER ANTES DE TOCAR EL FRONTEND

Formas exactas, verificadas por tests (`tests/test_api.py`, `test_inventario.py`, `test_backend.py`, `test_admin.py`, `test_dymo.py`).

### 7.1 Wizard v1 eliminado
`POST /api/scan/validate` y `POST /api/scan/pair` **ya no existen** (404). Las MAC no se escanean: se teclean con `PUT /api/pcb/{id}/mac`.

### 7.2 Objeto `pcb`
`{id, tipo, version, serie, nombre, mac|null, estado_ciclo, estado_pcb, origen, operador, nota, recibida_en, confirmada_en, updated_at, tarjeta_id|null, id_tarjeta_num|null, tarjeta_lote_id|null, ranura|null}`.
`estado_ciclo`: `RECIBIDA` (borrador) · `DISPONIBLE` · `ASIGNADA` · `FALLA` · `BAJA`.
`GET /api/pcb/por-codigo?codigo=` (QR o MAC) añade `tarjeta` (objeto completo) o responde 404.

### 7.3 Objeto `tarjeta` (`GET /api/tarjetas`, `/api/tarjetas/{id}`, WebSocket)
Lo de v1 (`id, lote_id, id_tarjeta_num, nombre_r1, mac_r1, nombre_r2, mac_r2, firmware_r1/2, semana_produccion, fecha_proyectada, fecha_real, soldadura…prueba_final, estado_general, estado_pcb_r1/r2`) **más**:
`nombre_r3`, `mac_r3` (siempre null), `estado_pcb_r3`, `pcb_r1_id/pcb_r2_id/pcb_r3_id`, `r1/r2/r3` (objeto `{id,tipo,version,serie,nombre,mac,estado_ciclo,estado_pcb}` o `null`), `completa` (R1 y R2 presentes) y `sin_mac` (subconjunto de `["R1","R2"]`).
`nombre_*` y `mac_*` son **derivados** de la PCB: `null` si la ranura está vacía (antes eran obligatorios). `search=` busca por número, nombre de R1/R2/R3 y MAC.
El `estado_general` de una tarjeta **incompleta nunca es LIBERADO** (con las 5 etapas OK y sin R2 queda `EN PROCESO`).

### 7.4 Endpoints
| Método y ruta | Cuerpo / respuesta |
|---|---|
| `POST /api/pcb/escanear` | `{codigo, operador?, tipo_forzado?, version?}` → 200 siempre: `{resultado:'AGREGADA'/'DUPLICADA'/'INVALIDA', mensaje, pcb/null, conteos:{R1,R2,R3,total}}`. `DUPLICADA` trae `pcb` (con `estado_ciclo`, `id_tarjeta_num`, `ranura`). Entrada mal formada = 422. |
| `GET /api/recepcion` | `{items:[pcb], conteos, huecos:{R1:[…],R2:[…],R3:[…]}, avisos:[str]}` |
| `POST /api/recepcion/confirmar` | `{ids?, nota?, operador?}` (cuerpo opcional) → `{confirmadas, ids, omitidas, resumen:{R1,R2,R3,total}, avisos, disponibles, conteos}` |
| `POST /api/pcb/manual` | `{tipo, version?, serie?, cantidad?, operador?}` → `{pcbs:[pcb], conteos}`; 409 si alguna ya existe (todo o nada) |
| `GET /api/pcb` | `?tipo=&estado_ciclo=&q=&sin_mac=&sin_tarjeta=&limit=&offset=` → `{total, items}`. `q` busca nombre, serie o MAC (con o sin `:`) |
| `PATCH /api/pcb/{id}` | `{tipo?, version?, serie?}` → pcb. 409 si choca; no se puede cambiar el tipo de una PCB montada |
| `POST /api/pcb/version` | `{ids, version}` → `{actualizadas, version, pcbs}`; todo o nada (409 si alguna chocaría) |
| `DELETE /api/pcb/{id}` | 204. `RECIBIDA/DISPONIBLE` se borra; `FALLA` pasa a `BAJA`; `ASIGNADA` → 409 |
| `PUT /api/pcb/{id}/mac` | `{mac/null, operador?}` → pcb. 400 formato o R3; 409 con mensaje que nombra a la PCB dueña |
| `POST /api/pcb/{id}/falla` | `{motivo?, reemplazo_id?, conservar_pruebas?, operador?}` → `{pcb, tarjeta/null, reemplazo/null}` |
| `GET /api/emparejar/sugerencias` | `?lote_id=` → `{lote_id, completas:[{serie,id_tarjeta_num,r1,r2,r3}], incompletas:[{serie,faltan,r1,r2,r3}], ocupadas:[serie], sueltas:{R1:[pcb],R2:[],R3:[]}}` |
| `POST /api/emparejar/auto` | `{lote_id?, series?}` → `{lote_id, creadas:[tarjeta], omitidas:[{serie,motivo}]}` |
| `POST /api/tarjetas` | `{lote_id?, id_tarjeta_num?, r1_id?, r2_id?, r3_id?}` → 201 tarjeta (permite impares). Sin `id_tarjeta_num` = serie de la R1 |
| `PUT /api/tarjetas/{id}/asignar` | `{ranura, pcb_id/null, marcar_falla?, conservar_pruebas?}` → tarjeta |
| `PATCH /api/tarjetas/{id}` | **nuevo** `{firmware_r1?, firmware_r2?, semana_produccion?(1-53), fecha_proyectada?, fecha_real?}` (YYYY-MM-DD; `""` borra) → tarjeta |
| `DELETE /api/tarjetas/{id}` | `?forzar=1` → `{id, id_tarjeta_num, lote_id, liberadas:[nombre]}`; 409 si tiene pruebas sin `forzar` |
| `GET/PUT /api/ajustes` | `{version_defecto}` |

> Decisiones (QA Emparejar/Programar): el emparejado automático es **por número de serie** e ignora la versión (R1 V30 0005 + R2 V31 0005 sí se unen; cada nombre conserva su versión). Si hay dos PCB del mismo tipo y serie (versiones distintas) se une la de menor id y la otra queda suelta. `PUT /pcb/{id}/mac` rechaza (400) además de 00:…/FF:… las MAC multicast (primer octeto impar) y acepta octetos separados por espacios. En `falla`, `reemplazo_id` no puede ser la propia PCB (400).

**Regla de pruebas al montar PCB:** al **montar** una PCB (reemplazo o llenar una ranura) las 5 etapas vuelven a `PENDIENTE` (hay que soldar, programar y probar la nueva), salvo `conservar_pruebas:true`. Solo **liberar** una ranura conserva las pruebas (la tarjeta queda incompleta, nunca LIBERADA).

### 7.5 WebSocket (`{evento, timestamp, data}`)
`PCB_RECIBIDA {pcb, pcbs?, conteos, operador}` (solo cuando es AGREGADA) · `PCB_ACTUALIZADA {pcb, pcbs?, reemplazo?, conteos}` · `PCB_ELIMINADA {id, nombre, tipo, accion:'ELIMINADA'/'BAJA', conteos}` · `RECEPCION_CONFIRMADA {confirmadas, ids, omitidas, resumen, avisos, disponibles, conteos, operador}` · `TARJETA_EMPAREJADA {tarjeta, stats, mensaje}` · `TARJETA_ACTUALIZADA {tarjeta, stats}` o `{eliminada:true, id, id_tarjeta_num, lote_id, liberadas, stats}` · `AJUSTES_ACTUALIZADOS {version_defecto}` · `ADMIN_CAMBIO {accion, respaldo, …}`.
Siguen de v1: `PRUEBA_ACTUALIZADA`, `PRUEBAS_LOTE_ACTUALIZADAS`, `LOTE_CAMBIADO`, `SYNC_EXCEL_COMPLETO`, `CONEXION_ESTABLECIDA`. **Ya no se emiten:** `ERROR_DUPLICADO` y `TARJETA_ESCANEADA`.

### 7.6 `/api/stats`
Campos de v1 + `total_r3_escaneados`, `incompletas` (tarjetas sin R1 o sin R2) e `inventario` = `{R1,R2,R3}` de PCB **DISPONIBLES** (globales, no del lote). `total_r1/r2/r3_escaneados` cuentan tarjetas del lote con esa ranura llena.

### 7.7 Caché y páginas
`/static/*` y todas las páginas HTML responden `Cache-Control: no-cache`. Páginas: `/` (Recibir), `/emparejar`, `/programar`, `/pruebas`, `/monitor`, `/dymo` (sirven `app/static/{index,emparejar,programar,pruebas,monitor,dymo_preview}.html`).

### 7.8 Certificado
`GET /cert` (público) → `application/x-x509-ca-cert`, archivo `escaner-tqt.crt` (solo el certificado, nunca la llave).

### 7.9 DYMO — formato principal 30334 (57 × 32 mm). Detalle en `docs/DYMO.md`
- Todos los endpoints DYMO usan `label_format=30334` por defecto (`30252` es secundaria; otro valor → 400).
- `GET /api/dymo/label/{id}` añade `estado_etiqueta` (`INCOMPLETA/IDENTIFICACION/FINAL`), `imprimible`, `sin_mac`, `advertencias`, `trama_lineas` (las 4 líneas), `qr_version`, `geometria_mm` (`etiqueta, zona_segura, qr, texto` = `[x,y,w,h]` en mm, y `puntos_por_modulo`), `dcd_xml` (XML `.dymo` para `openLabelXml`) y `dymo_xml` (`.label` v8). `is_ready_to_print` = FINAL.
- **Nuevo** `GET /api/dymo/label/{id}/xml?label_format=&tipo=dymo|label&texto_como=text|address` → XML crudo (`application/xml`, sin BOM) para `dymo.label.framework.openLabelXml(xml)`. `texto_como=address` emite el texto como `AddressObject` (el único objeto de texto que trae el ejemplo oficial del SDK) por si TextObject fallara.
- **Nuevo** `GET /api/dymo/label/{id}/archivo?tipo=dymo|label` → descarga `TQT_<num>.dymo` (o `.label`), `application/octet-stream`, `Content-Disposition: attachment`, con BOM UTF-8 como los archivos oficiales.
- **Nuevo** `GET /api/dymo/lote/archivo?ids=1,2,3&tipo=` → `TQT_etiquetas.zip` con un archivo por tarjeta (ids **internos** de tarjeta; los inexistentes se ignoran; si ninguno existe → 404).
- `GET /api/dymo/batch-labels?modo=final|identificacion|todas` (por defecto `final`).
- `GET /api/dymo/svg/{id}?guia=true|false` y `GET /api/dymo/preview/{id}`: escala real (1 unidad = 1 mm), QR como vectores, zona segura de 3 mm punteada.

### 7.10 Administración (`/api/admin`, detalle en `docs/ADMIN.md`)
`GET /api/admin/estado` (público: `{habilitado, mensaje, token_ttl_segundos}`) · `POST /login {password}` → `{token, expira_en, expira}`.
Con la cabecera `X-Admin-Token`: `GET /resumen`, `POST /cambiar-clave {actual,nueva}`, `DELETE /tarjetas {ids, liberar_pcb}`, `DELETE /pcb {ids}`, `POST /lote/{id}/vaciar {confirmar:"VACIAR", eliminar_pcb?}`, `POST /reset {confirmar:"BORRAR TODO"}`, `GET /export/excel?lote_id=&ruta=`.
Códigos: 401 (token o clave), 429 (bloqueo, con `Retry-After`), 503 (admin deshabilitado). Toda acción destructiva devuelve `{respaldo, …}`. La descarga del Excel exige la cabecera, así que no puede ser un `<a href>`: usar `fetch` + `blob`.

### 7.11 Excel
- `Producción!B` (fórmula) se sustituye por el nombre real de la R1 **solo** cuando difiere de `TQT-R1-V30-<ID>` (otra versión o número) y se restaura si vuelve a coincidir. La respuesta de sincronización trae `avisos:[str]`.
- Una tarjeta cuyo ID no está en la lista de la plantilla reutiliza un renglón reservado sin datos (con aviso); si no quedan renglones libres, queda en `omitidas`.
- **R3 no existe en la plantilla:** se guarda en la BD y la sincronización avisa; la plantilla no se altera. Para llevarla al Excel habría que añadirle columnas de R3 (sin tocar las fórmulas existentes) y mapearlas en `excel_sync._escribir_produccion`.
- Importar: solo entran PCB con MAC del catálogo del libro (los renglones sin MAC de la plantilla no son PCB reales).


## 8. Cambios del 2026-09-24 (a petición del usuario)
- **Sección Pruebas eliminada.** Ya no existen `/pruebas`, `pruebas.html`, `pruebas.js`, `app/routers/pruebas.py`, `GET/PUT /api/tarjetas/{id}/pruebas`, `POST /api/pruebas/lote` ni los eventos WS `PRUEBA_ACTUALIZADA`/`PRUEBAS_LOTE_ACTUALIZADAS`. Se conserva **solo** la tabla interna `pruebas_historial` y la hoja `Pruebas` de la plantilla Excel (son parte de la estructura del Excel). El monitor y las listas muestran ahora el estado real de la tarjeta: *Completa* (R1+R2+R3), *Falta R1/R2/R3* o *Sin MAC*. La etiqueta DYMO FINAL exige solo R1 y R2 asignadas con MAC (ya no hay "PCB FUNCIONAL").
- **Nueva pantalla `/consultar`** (pestaña "Consultar"): escanea la etiqueta DYMO (4 líneas), el QR de una PCB o una MAC y muestra la ficha completa: tarjeta, pareja R1/R2/R3, versión (V30), serie, MAC (R1/R2) y firmware. Avisa si la etiqueta ya no coincide con la tarjeta (placa reemplazada o MAC distinta). API: `GET /api/consulta?codigo=` (400 no reconocido, 404 no registrada). También `?codigo=` en la URL (el monitor enlaza así a "Ficha").
- **Versión de hardware vs firmware.** El `V30` del nombre (`TQT-R1-V30-0021`) es la **versión de HARDWARE**. Además cada **R1 y R2** (solo ellas) lleva la **versión de FIRMWARE** con la que se programó (`pcb_inventario.firmware`; catálogo `firmware_catalogo` sembrado con las listas del Excel: Principal/R1 `2, 3.2, 3.3, 4.0, 4.1, 4.2`, Respaldo/R2 `2, 2.1`). **La R3 no lleva MAC ni firmware.** API: `PUT /api/pcb/{id}/programacion {mac, firmware}`, `PUT /api/pcb/{id}/firmware`, `GET/POST /api/firmware`, `DELETE /api/firmware/{rol}/{version}` (supervisor). El firmware viaja con la placa (si se reemplaza, la tarjeta muestra el de la nueva); `PATCH /api/tarjetas/{id}` acepta `firmware_r1|r2` y lo escribe en la PCB de esa ranura. El Excel recibe el firmware en `Producción!D/G` y las versiones nuevas se agregan a las listas `N`/`P`. En **Programar** R1/R2 capturan MAC + firmware; al escanear una R3 solo hay un aviso.
- **Logo**: en el monitor lleva al escáner (`/`).
- **Monitor y acciones de supervisor con contraseña** (ver docs/ADMIN.md).
- **Movimientos (admin):** `GET /api/admin/movimientos` consulta la bitácora (altas, ediciones, eliminaciones, sesiones, Excel). "Borrar TODO" ya no la borra.
- **Lotes:** el encabezado móvil abre una hoja para usar/crear/consultar lotes; `GET /api/lotes` incluye `tarjetas`.
- **HTTPS sin aviso:** autoridad local `certs/ca.pem` (se instala una vez por dispositivo; `/cert`, `instalar_certificado.ps1`) que firma el certificado del servidor.
