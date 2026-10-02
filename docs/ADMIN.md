# Área de administración

Todo lo destructivo (borrar tarjetas o PCB, vaciar un lote, reiniciar) está detrás de una contraseña de administrador y hace **siempre un respaldo automático antes**.

## Habilitar

Define la variable de entorno **`TQT_ADMIN_PASSWORD`** (mínimo 8 caracteres) y reinicia el servidor:

- Windows: `$env:TQT_ADMIN_PASSWORD = "mi-clave-larga"; python run_server.py`
- Docker: en `.env` / `docker-compose.yml` → `TQT_ADMIN_PASSWORD: ${TQT_ADMIN_PASSWORD}`

**No existe contraseña por defecto.** Sin la variable, el admin queda deshabilitado: `POST /api/admin/login` responde 503 con el mensaje "falta configurar TQT_ADMIN_PASSWORD" y el arranque deja un aviso en el log. `GET /api/admin/estado` (público) dice si está habilitado.

Variables opcionales: `TQT_BACKUP_DIR` (por defecto `respaldos/`; en Docker `/backups`), `TQT_ADMIN_TOKEN_TTL` (1800 s), `TQT_ADMIN_MAX_FALLOS` (5), `TQT_ADMIN_BLOQUEO_SEG` (300), `TQT_ADMIN_RETARDO_MS` (400), `TQT_ADMIN_PBKDF2_ITER` (600000).

## Cómo se guarda y se valida

- La contraseña se guarda en la tabla `ajustes` como hash **PBKDF2-SHA256** con sal aleatoria de 16 bytes (`pbkdf2_sha256$600000$<sal>$<hash>`); nunca en claro.
- `POST /api/admin/cambiar-clave {actual, nueva}` (mín. 8 caracteres, distinta de la actual) la cambia; los tokens anteriores dejan de valer. La clave cambiada **sobrevive a los reinicios** mientras la variable de entorno no cambie. Si el admin la olvida: cambiar `TQT_ADMIN_PASSWORD` y reiniciar la restablece.
- `POST /api/admin/login {password}` devuelve un token firmado con **HMAC-SHA256** (secreto persistente en `ajustes`) que **caduca a los 30 minutos**. Se envía en la cabecera **`X-Admin-Token`**. Comparaciones en tiempo constante.
- **Bloqueo por IP:** 5 fallos → bloqueo de 5 minutos (`429` con `Retry-After`); un login correcto reinicia el contador. Cada login dura como mínimo 400 ms, acierte o falle.
- Detrás de Docker Desktop en Windows todas las peticiones pueden llegar con la misma IP (la del puente): el bloqueo sería entonces compartido por todos. Es un fallo seguro (bloquea de más, nunca de menos).

## Endpoints (cabecera `X-Admin-Token`)

| Ruta | Efecto |
|---|---|
| `GET /api/admin/resumen` | conteos por lote y estado, inventario por tipo y ciclo, tamaño de la BD, últimos respaldos |
| `DELETE /api/admin/tarjetas` `{ids, liberar_pcb}` | borra las tarjetas (y sus pruebas). `liberar_pcb:true`: sus PCB vuelven a `DISPONIBLE`; `false`: también se eliminan |
| `DELETE /api/admin/pcb` `{ids}` | elimina PCB del inventario (aunque estén montadas: la tarjeta queda incompleta y nunca LIBERADA) |
| `POST /api/admin/lote/{id}/vaciar` `{confirmar:"VACIAR", eliminar_pcb?}` | borra las tarjetas del lote; sus PCB vuelven a DISPONIBLE (o se eliminan) |
| `POST /api/admin/reset` `{confirmar:"BORRAR TODO"}` | borra tarjetas, pruebas e inventario. **Conserva** lotes, ajustes (incluida la clave) y los **movimientos** (se añade `ADMIN_RESET`) |
| `GET /api/admin/movimientos?limite&desplazamiento&categoria&q&desde&hasta&lote_id` | historial de lo que se hizo (ver «Movimientos») |
| `GET /api/admin/export/excel?lote_id=&ruta=` | Excel con la estructura de la plantilla mensual (ver abajo) |

Toda acción destructiva: (1) valida la confirmación / que exista el objetivo (si no, 400/404 **sin** respaldo ni cambios), (2) hace el respaldo `tqt_YYYYmmdd_HHMMSS_µs_<motivo>.db` en `TQT_BACKUP_DIR` con la API de backup de SQLite, (3) borra en una sola transacción, (4) deja una fila en la bitácora (`ADMIN_TARJETAS_BORRADAS`, `ADMIN_PCB_BORRADAS`, `ADMIN_LOTE_VACIADO`, `ADMIN_RESET`), (5) emite el evento WebSocket `ADMIN_CAMBIO` y (6) devuelve `{respaldo: "<nombre>", …}`. Para deshacer, cierra el servidor y copia el respaldo sobre `tqt_produccion.db`.

## Movimientos (qué se hizo, cuándo y quién)
El «evento en bitácora» del Resumen y los movimientos son **el mismo registro** (tabla `escaneos`). La pestaña **Movimientos** de `/admin` lo muestra: altas, ediciones (MAC, firmware, versión, reemplazos, fallas), eliminaciones (placas, tarjetas, borrados del admin), sesiones (inicio, cierre, intentos fallidos) y Excel (sincronizado/exportado). Más reciente arriba, con «hoy 10:32» / «ayer» / fecha, insignia de tipo (color + icono + texto), operador y lote.
- Filtros: tipo (con contador), texto (placa, MAC, operador, detalle), desde/hasta, lote; «Cargar más» de 50 en 50 («N de total»); «Actualizar»; «Exportar CSV» de lo filtrado (hasta 5000 filas; neutraliza celdas que empiecen por `=`, `+`, `-`, `@`).
- El Resumen muestra los últimos 5 y el acceso «Ver movimientos».
- **No se borra con «Borrar TODO»** (queda además un `ADMIN_RESET`). La búsqueda trata `%`, `_` y `!` como texto literal; el `_` también coincide con nombres de evento internos (p. ej. `PCB_ALTA`).

## Cerrar sesión y `?next=`
- «Cerrar sesión» llama `POST /api/admin/logout` (borra la cookie), limpia sessionStorage, tablas, estado y hojas abiertas, quita `?next=` de la URL y muestra **«Sesión cerrada»** (aviso, no error) con dos salidas: **Ir al escáner** (`/`) y **Volver a entrar**. Avisa por `BroadcastChannel` a las demás pestañas de administración, que también salen.
- El logo de Administración y «Ir al escáner» del login llevan a `/`, nunca a `/monitor` (que exige sesión y devolvía al login: era el bucle confuso).
- Con `?next=/monitor` el login explica: «Para abrir el monitor necesitas la contraseña de supervisor.»; tras entrar vuelve al monitor. Solo se admite `/monitor` como destino.
- Un monitor abierto en otra pestaña vuelve al login (con ese motivo) en su siguiente petición, no al instante.

## Exportar a Excel

`GET /api/admin/export/excel?lote_id=` genera una **copia nueva de la plantilla** (hojas Producción / Catálogo PCB / Pruebas / Etiquetas con sus 2,110 fórmulas, validaciones de datos y formatos condicionales) con los datos del lote y la devuelve como **descarga** (`Control_Produccion_TQT_[Mes]_[Año].xlsx`). **No toca el archivo mensual en uso.** Cabeceras `X-Total-Tarjetas` y `X-Integridad-Valida`.
Con `ruta=<carpeta o archivo .xlsx>` lo guarda ahí (solo dentro de `TQT_EXCEL_DIR`, el proyecto o el Escritorio) y responde `{success, ruta, filename, total_tarjetas, avisos, integridad_valida}`.
Como exige la cabecera `X-Admin-Token`, desde el navegador se descarga con `fetch(...)` + `Blob`, no con un enlace.

## Riesgos conocidos

- No hay usuarios individuales: es una sola contraseña compartida. Quien la tenga puede borrar todo (siempre con respaldo).
- Los respaldos se acumulan en `TQT_BACKUP_DIR`; no se purgan solos.
- El resto de la API (escaneo, MAC, pruebas) **no** tiene autenticación: cualquier equipo de la WiFi de planta puede usarla. Es una decisión de diseño de la v1; conviene un PIN de operador si la red no es de confianza.

## Qué exige contraseña (actualizado)
Acceso masivo a los datos = solo con sesión de administrador (`X-Admin-Token`):
- Todo lo de `/api/admin/*` (resumen, borrar tarjetas/PCB, vaciar lote, borrar todo, exportar, cambiar clave).
- `GET /api/export/excel` (descarga completa del Excel del lote), `POST /api/excel/import` (carga masiva desde un Excel) y `POST /api/excel/create-monthly`.
- El explorador de API `/docs`, `/redoc` y `/openapi.json` están **apagados**; para depurar: `TQT_DOCS=1` en `.env`.

Siguen abiertas, sin contraseña, las acciones normales del taller: escanear, confirmar recepción, editar/eliminar una PCB, emparejar, teclear MAC, registrar pruebas, imprimir etiquetas y "Sincronizar Excel" del monitor.
El botón "Descargar" del monitor ahora lleva a `/admin` (ahí se descarga con contraseña).

## Endurecimiento (QA de seguridad)
- La sesión de administrador es un token sin estado: **"Cerrar sesión" solo lo olvida el navegador** (sessionStorage de la pestaña, nunca en la URL ni en localStorage); sigue siendo válido hasta caducar (30 min) o hasta que se cambie la clave. Cambiar la clave devuelve un token nuevo y la pantalla lo adopta.
- Peticiones que cambian datos (POST/PUT/PATCH/DELETE) con `Origin` de otro sitio, y WebSockets desde otro origen, se rechazan (403 / cierre 1008). No hay CORS.
- `ruta`/`excel_path`/`target_path`/`ruta_excel` de lote: solo `.xlsx` dentro de `TQT_EXCEL_DIR`, el proyecto o el Escritorio; se rechazan nombres reservados de Windows (`CON`, `NUL`, `COM1`…) y, para escribir, la carpeta `templates/`. La ruta guardada en un lote también se valida al sincronizar.
- Ids fuera del rango de SQLite (> 2^63) responden 422 (antes 500).

## Qué pide contraseña (actualizado v1.1.2)
La contraseña de supervisor protege **solo la zona de administración**: `/admin` y `/api/admin/*` (borrar tarjetas/PCB, vaciar lote, borrado total, exportar, movimientos, cambiar clave) y el acceso masivo a datos (`GET /api/export/excel`, `POST /api/excel/import`, `POST /api/excel/create-monthly`).
**No** piden contraseña: la consola de PC (`/monitor`), las pantallas del celular, usar/crear lote, sincronizar Excel y las acciones normales del taller.
