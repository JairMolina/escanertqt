# Consola de escritorio (PC) — contrato de diseño y de código

## Qué es y qué NO es
La PC (pantalla ancha + ratón) entra por `/` y salta sola a `/monitor`, que pasa a ser la **consola de escritorio**.
Es una vista de **consulta y gestión**, **SIN CÁMARA**: no carga `jsQR.js`, `scanner.js`, `visor.js`, no pide permiso de cámara y no escanea nada
(las cámaras de laptops/PC son malas). La captura de datos es con **teclado**: sobre todo las **MAC de R1 y R2** (la R3 no lleva MAC ni firmware) y el
firmware. Todo lo administrativo (lotes, movimientos, Excel, etiquetas, borrados, contraseña) se gestiona desde aquí.
Sigue exigiendo la sesión de supervisor (cookie `tqt_admin`, ver docs/ADMIN.md) cuando hay contraseña configurada: `/monitor` redirige a `/admin?next=/monitor`.
El celular sigue igual (`/`, `/emparejar`, `/programar`, `/consultar` con cámara). Elección manual: `localStorage['tqt.vista'] = 'movil'|'escritorio'`
(enlaces "Versión móvil" en la consola y "Versión de escritorio" en el menú móvil).

## Dirección visual (es la misma marca, en versión densa de escritorio)
Tokens de `app/static/css/app.css` (máscara de soldadura azul-negro, acento oro ENIG, Barlow Semi Condensed + IBM Plex Mono locales, claro/oscuro). Sin CDN.
- **Armazón**: barra lateral izquierda fija (≈232 px, colapsable a iconos con `[`), cabecera superior (título de la sección, selector de LOTE, punto de conexión WS,
  tema, "Versión móvil", cerrar sesión), contenido a ancho completo (máx. ≈1680 px) con rejillas y **tablas densas** (filas ≈40 px, cabecera fija, ordenar, filtros,
  selección múltiple, acciones por fila). Usa el ancho: 2–3 columnas, paneles laterales de detalle en vez de hojas modales cuando convenga.
- **Teclado primero**: atajos (`/` buscar, `g` luego `r|i|t|m|c` ir a sección, `Esc` cerrar panel, `Enter` guardar y saltar a la siguiente fila), foco visible,
  orden de tabulación lógico, sin depender del ratón.
- Accesibilidad AA, `aria-live` en resultados, objetivos ≥ 32 px (ratón), `prefers-reduced-motion`, texto en español claro (ver skill `design:ux-copy`).
- Nada de clichés de "diseño de IA": jerarquía tipográfica, densidad útil, números en mono tabular, color solo con significado (y siempre con texto/icono).

## Secciones (barra lateral) y rutas hash
| Grupo | id / hash | Sección |
|---|---|---|
| Operación | `#/resumen` | KPIs, avance por tipo (R1/R2/R3 recibidas → asignadas → con MAC), tarjetas que necesitan atención, actividad en vivo |
| | `#/inventario` | Inventario de PCB: filtros (tipo, estado, hardware V, sin MAC), edición, versión de hardware en masa, eliminar |
| | `#/tarjetas` | Tarjetas del lote: búsqueda, estado (completa/falta/sin MAC), detalle en panel lateral, etiqueta DYMO, ficha |
| | `#/macs` | **MAC y firmware de R1/R2** (captura con teclado, pegado masivo) |
| | `#/consultar` | Consulta (sin cámara): escribir/pegar número, nombre de PCB, MAC o el texto de 4 líneas de la etiqueta → ficha completa |
| Gestión | `#/lotes` | Lotes: lista, usar como activo, crear, ver |
| | `#/movimientos` | Bitácora de movimientos (misma que /admin) |
| | `#/etiquetas` | Etiquetas DYMO (enlace a `/dymo`, integrado por la etapa 4) |
| | `#/excel` | Sincronizar/exportar Excel del lote |
| | `#/admin` | Administración (borrados, contraseña): enlace a `/admin` con el mismo armazón (etapa 4) |
`/monitor?lote=<id>` deja ese lote seleccionado; `/monitor#/consultar?codigo=<texto>` abre la consulta.

## Contrato del armazón (`app/static/js/escritorio.js`, lo crea la etapa 2)
```js
// Cada sección vive en su propio archivo js/sec_<id>.js y se registra sola:
window.TQTEscritorio.registrar({
  id: 'macs', titulo: 'MAC y firmware', icono: 'programar', grupo: 'operacion', orden: 40,
  montar(host, ctx) {            // host: <section> vacío donde dibujar; ctx abajo
    /* ...dibuja... */
    return { actualizar() {},    // se llama cuando cambia el lote, llega un evento WS relevante o el usuario pulsa Actualizar
             desmontar() {} };   // limpieza de listeners/timers
  },
});
// ctx = { T /* window.TQT */, api /* T.api */, h, icon, toast, sheet,
//         lote() /* lote activo/seleccionado {id,codigo_lote,mes,anio,...} */, alCambiarLote(fn), ws /* T.ws() */,
//         ir(id, params) /* navegar a otra sección */, sesion /* {admin:true|false} */, titulo(t) /* cambia el título de la cabecera */ }
```
`monitor.html` incluye los `<script src="/static/js/sec_*.js">` bajo el comentario `<!-- SECCIONES -->`; el armazón monta la sección según `location.hash`.

## API que usa la consola (todas existentes salvo lo marcado)
`GET /api/lotes` · `POST /api/lotes` · `POST /api/lotes/{id}/activar` · `GET /api/pcb` (`sin_mac=1`, `tipo`, `estado_ciclo`, `q`, `limit≤5000`) · `PATCH/DELETE /api/pcb/{id}` ·
`POST /api/pcb/version` · `PUT /api/pcb/{id}/programacion {mac, firmware}` · `PUT /api/pcb/{id}/firmware` · **`POST /api/programacion/lote`** (nuevo: `{items:[{pcb_id|nombre, mac, firmware?}], simular?}` →
`{total, guardadas, fallidas, resultados:[{indice, ok, nombre, pcb_id, mac, firmware, error?, codigo?}]}`; con `simular:true` valida todo y no guarda) · `GET /api/firmware` (catálogo `{R1:[…],R2:[…]}`) ·
`GET /api/tarjetas` · `GET /api/consulta?codigo=` · `GET /api/dymo/*` · `POST /api/sync/excel` · `GET /api/admin/*` (movimientos, resumen, export…) · WebSocket `/ws`
(eventos `PCB_RECIBIDA`, `PCB_ACTUALIZADA`, `PCB_ELIMINADA`, `TARJETA_ACTUALIZADA`, `RECEPCION_CONFIRMADA`, `LOTE_CAMBIADO`, `ADMIN_CAMBIO`, `SYNC_EXCEL_COMPLETO`).
Versión de HARDWARE = el `V30` del nombre; FIRMWARE = versión con la que se programó (solo R1/R2). Rotular siempre "Hardware V30" y "Firmware 4.1".
