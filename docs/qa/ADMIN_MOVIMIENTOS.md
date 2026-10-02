# Movimientos de /admin y cierre de sesión (agente ADMIN-MOVIMIENTOS)

Entorno: servidor aislado en 8463 (`tests/e2e/servidor.py`, BD temporal, clave `ClaveQA-12345`), Chrome real (Playwright `channel=chrome`). `escaner-tqt` (8443), `.env` y datos reales no se tocaron.
Respuesta a la duda del usuario: «eventos en bitácora» y «saber qué se hizo (borrado, editado…)» son **el mismo registro** (tabla `escaneos`); antes solo se mostraba su conteo, ahora tiene pantalla.

## 1. Causa raíz del cierre de sesión «que se confunde»
Reproducido en Chrome (script `admin_mov_sesion.py repro` antes del arreglo):
1. Cerrar sesión solo volvía a pintar **el mismo formulario de login** de siempre, sin decir que se había cerrado: parecía que «entra a administración pidiendo la contraseña otra vez».
2. Las dos únicas salidas de esa pantalla, el enlace **«Cancelar»** y el **logo** de Administración, apuntaban a `/monitor`. El monitor exige sesión, así que el servidor respondía 302 a `/admin?next=/monitor` y aparecía **un segundo login** (bucle: login -> salir -> login). Comprobado: tras «Cancelar» la URL era `/admin?next=/monitor`.
3. Factores agravantes: no había motivo visible para `?next=/monitor`; `?next=` quedaba en la URL tras cerrar sesión; otras pestañas de administración seguían con su token hasta caducar; los avisos de sesión caducada salían como error rojo.
La cookie sí se borraba correctamente y Atrás/`pageshow` ya funcionaban (verificado); no era un fallo del backend.

## Flujo nuevo (verificado en navegador, 19/19)
- Cerrar sesión: `POST /api/admin/logout` (botón deshabilitado durante la llamada), limpia sessionStorage, estado, tablas, hojas abiertas y `?next=`, y muestra **«Sesión cerrada»** (aviso verde, no error) con **Ir al escáner** (`/`) y **Volver a entrar** (muestra el formulario con foco en la contraseña). Nunca dos logins encadenados.
- Logo de Administración y salida del login: `/` (escáner).
- `?next=/monitor`: aviso «Para abrir el monitor necesitas la contraseña de supervisor.»; tras un login correcto vuelve a `/monitor`. `next` hostil (`//evil.com`) se ignora.
- Cerrar sesión avisa por `BroadcastChannel` a las demás pestañas de administración (salen también). Un monitor abierto en otra pestaña vuelve al login (con su motivo) en su siguiente petición.
- Sesión caducada / token no válido: login con aviso ámbar (warn), sin panel ni datos.
- Atrás/Adelante tras cerrar: sin panel ni datos.

## 2. Pestaña Movimientos
Cambios por archivo:
- `app/static/admin.html`: pestaña «Movimientos» (línea explicativa pedida, tira de categorías con contador, búsqueda, desde/hasta, lote, Quitar filtros, Actualizar, Exportar CSV, «Cargar más»); pantalla «Sesión cerrada»; aviso de motivo `next`; logo y salida a `/`; texto de Borrar TODO («Se conservan los lotes, la contraseña y los movimientos»); `<style>` propio (tabla en escritorio, tarjetas apiladas con borde de color por categoría en móvil).
- `app/static/js/admin.js`: módulo Movimientos (`cargarMov`, `pintarMov`, `cuando`, `cargarUltimos`, CSV), Resumen con «Últimos movimientos» (5) + «Ver movimientos» y KPI «Movimientos registrados», nuevo flujo `verLogin(msg, {cerrada, kind})`, `BroadcastChannel`, texto/diálogo de Borrar TODO sin «bitácora» (y sin el KPI bitácora entre lo «que se borra»). Todo dato del servidor entra con `h()`/textContent. Insignias: Alta verde + icono más, Edición ámbar + lápiz, Eliminación rojo + papelera, Sesión gris + info, Excel azul + icono Excel (color, icono y texto). Respuestas viejas se descartan (`pedido`), debounce 300 ms en búsqueda, aviso claro si Desde > Hasta (sin llamar a la API). CSV: pide páginas de 200 (tope 5000), BOM UTF-8, neutraliza `=`, `+`, `-`, `@`.
- `docs/ADMIN.md`: sección Movimientos, sección Cerrar sesión/`?next=`, fila de reset corregida.
- `tests/test_qa_movimientos.py` (17 tests), `tests/e2e/admin_mov_seed.py`, `admin_mov_ui.py`, `admin_mov_sesion.py`, `admin_mov_reinicia.ps1`.
- Edit mínimo ajeno: `tests/test_qa_admin2.py` (regex de `verLogin` acepta la nueva firma `verLogin(msg, opts)`).
- No se encontró ningún bug en el backend de movimientos.

## 3. Pruebas
- Navegador, Chrome real, `admin_mov_ui.py`: **67/67** con datos sembrados por API (altas, MAC, firmware, versión masiva, falla + reemplazo, borrado de placa y de tarjeta, borrados del admin, login fallido, logout, exportación Excel, 130 cambios de MAC = 164+ movimientos): chips y contadores = API, 50 filas por página y «Cargar más» hasta el total («N de total», botón se oculta), cada categoría solo muestra sus filas, búsqueda (MAC, operador, `%`, `_`, `!`, HTML hostil sin inyección), estado vacío, Desde/Hasta/lote, Quitar filtros, Actualizar trae el movimiento nuevo, CSV descargado con el mismo número de filas, resumen con 5 últimos, 1280/390/320 px x claro/oscuro sin scroll horizontal (tabla en escritorio, tarjetas en móvil), **axe-core 0 violaciones** (Movimientos y Resumen x 3 anchos x 2 temas, «Sesión cerrada» y login), consola sin errores ni peticiones externas.
- Navegador, `admin_mov_sesion.py`: **19/19** (todos los caminos de cierre de sesión descritos arriba).
- `python -m unittest tests.test_qa_movimientos`: 17 OK (categorías/conteos, orden, paginación sin repetidos, `%`/`_`/`!` literales, fechas inválidas 400, categoría inválida 400, sin token 401, reset conserva movimientos + `ADMIN_RESET`, login fallido/ok/logout, contraseña nunca en el registro, exportación registrada, estáticos de pantalla).
- Capturas: `docs/qa/admin_mov_img/` (`movimientos_1280_light/dark`, `movimientos_390_dark/light`, `movimientos_320_*`, `eliminaciones_1280`, `vacio_1280`, `resumen_1280`, `sesion_cerrada_390/1280`, `login_next_monitor_1280`).
- Suite completa: `Ran 399 tests`, **1 FAIL y 1 ERROR**: el ERROR era mío (regex de `test_qa_admin2` por la nueva firma de `verLogin`; corregido, `test_qa_admin2` + movimientos + monitor_auth = 44 OK). El FAIL restante es ajeno: `test_api.test_17_certificado_publico_para_instalar_en_el_celular` espera `filename="escaner-tqt.crt"` y el servidor entrega `escaner-tqt-ca.crt` (cambio de otro agente en `/cert`).

## Observaciones / no verificable
- Buscar `_` devuelve también filas por el nombre de evento interno (`PCB_ALTA`, `MAC_GUARDADA`): el backend busca en `evento`; comportamiento inocuo pero puede sorprender.
- Los movimientos no se actualizan solos por WebSocket (usa Actualizar; al cambiar de pestaña se recarga).
- La fecha de algunos eventos puede venir en UTC y otros en hora local (ya señalado en QA-ADMIN-PROFUNDO): «hoy/ayer» se calcula con lo que llegue.
- El monitor abierto en otra pestaña no se entera al instante del cierre de sesión (`monitor.js`/`common.js` no son míos); lo hace en su siguiente petición.
- Importar `app.main` en los tests imprime que emite un certificado en `certs/` (comportamiento existente).
- No probado: Safari/iOS, lector de pantalla real, más de ~200 movimientos en móvil real (probé 164 en Chrome de escritorio con viewport de 390 px), CSV de 5000 filas.
