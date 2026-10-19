# TQT Android 0.2.0: consulta de inventario y QR

Fecha: 2026-10-19. Rama: `codex/android-inventario-qr-20261019`, derivada del
trabajo Android `b81eeb2`. No se desplegó ni reinició el servidor.

## Causa comprobada

Desde la sesión que el usuario inició en el teléfono Android 13, el servidor
respondió 404 a `GET /api/android/devices?limit=1`. La app 0.1.0 dependía de esa
ruta para llenar el listado; por eso abría un diálogo «Not Found».

Los GET `/api/pcb?tipo=R2&q=0011&limit=1` y `/api/esp32/r2/status` sí respondieron
200. La primera consulta encontró la R2 0011. No era necesario copiar la base,
modificar el inventario ni desplegar un backend para resolver la consulta.

## Comportamiento final

- Cliente de inventario sobre los contratos de lectura de la web.
- Listado completo mediante páginas de 100, contador y Cargar más; filtros de
  tipo Todas/R1/R2/R3 y Ver todas para recuperar una búsqueda vacía.
- `11` se normaliza a `0011`, sin asumir una versión de hardware; también
  admite `R2 11`, nombre completo y MAC.
- Botón Escanear QR con cámara nativa, permiso explícito, decodificación local,
  cancelación y rechazo explicativo de códigos ajenos. No abre enlaces del QR
  ni crea PCB al escanear. Una etiqueta de pareja DYMO prioriza R2.
- Ficha por selección: nombre, hardware, firmware, MAC, ciclo y tarjeta
  asociada. La evidencia R2 es la de la web; un firmware registrado sin
  evidencia no se presenta como una programación física verificada.
- Errores de conexión/permisos y ausencia de resultados diferenciados.
  Respuestas previas conservadas tras un fallo quedan advertidas como tales.
- Detección de servicio Android no desplegado: consulta disponible y nuevas
  operaciones de programación deshabilitadas con explicación. Se conservan los
  contratos y guardas de OTA/alta/offline; no se escribieron eFuses ni firmware.
- Navegación y teclado respetan las barras del sistema; versión visible desde
  BuildConfig. APK de ensayo firmado con la misma identidad debug existente.

## Verificación ejecutada

- `assembleDebug`, `assembleDebugAndroidTest`, `testDebugUnitTest`, `lintDebug`:
  BUILD SUCCESSFUL. 40 pruebas JVM, cero fallos. Lint: 0 errores, 15 avisos de
  mantenimiento/compatibilidad; no se actualizó el stack fuera del alcance.
- Teléfono USB real Android 13: 9 pruebas instrumentadas correctas inicialmente
  (3 de inventario, 5 de almacenamiento aislado y 1 de Keystore). La compilación
  final pasó las 4 de inventario, incluyendo el caso nuevo de recuperación de
  búsqueda sin resultados: 10 casos instrumentados distintos comprobados.
- Búsqueda `11` y frame QR sintético decodificado con ZXing localizaron el mismo
  registro; ficha y firmware coincidieron con la web.
- Paginación real: 300 registros, tipos R1/R2/R3, sin duplicados ni corte en 100.
- Prueba del gestor: `9999` sin resultados, recuperación con `11`, selección,
  estado y catálogo, sin diálogo Not Found ni error de detalle.
- Uso manual por ADB de la interfaz real: filtro R2, escritura 11, Buscar,
  resultado único y apertura del detalle con los datos del servidor.
- Cámara física abierta desde Escanear QR (cliente activo com.tqt.ota) y regreso
  al cancelar. No había etiqueta/R2 física para comprobar su lectura óptica.
- SDK `apksigner verify` y `aapt dump badging`: firma válida, paquete
  `com.tqt.ota`, versionCode 2, versionName 0.2.0, minSdk 26, targetSdk 36.
- Reinstalaciones de app y test: Success, sesión conservada, sin confirmación
  manual en las repeticiones verificadas. Depuración USB, instalación USB,
  control de entrada y mantener pantalla cargando activos. Autorización ADB
  sin caducidad configurada a petición del usuario. No se desactivaron los
  verificadores globales de aplicaciones ni de bytecode.

Las comprobaciones autenticadas fueron GET de consulta. Las pruebas de
almacenamiento usan contextos y bases aislados; no borran la sesión ni outbox
del usuario. Logs, capturas, paquetes de prueba y datos reales quedan fuera de
Git. No hubo cambios web/backend/Docker: se verificó Android nativo mediante
Gradle, instrumentación y ADB; no se atribuyen pruebas Playwright nuevas.

## Límites y continuación

No hay una R2 física conectada. Quedan las pruebas BLE/OTA, instalación y
verificación de arranque reales, cortes y recuperación del firmware. El backend
Android preparado en la rama anterior sigue pendiente de su proceso de
despliegue autorizado y respaldo; no está habilitado por instalar este APK.
La firma/distribución definitiva del APK y la publicación privada productiva
siguen pendientes. Este archivo no convierte el APK debug en una release.

Se usaron CM para continuidad, checkpoint, memoria y Git; ECC Android para
estado Kotlin/Compose, ECC backend para contrastar contratos existentes y ECC
verificación para build, pruebas y diff. ui-ux-pro-max aportó el patrón de
estado vacío recuperable; el diseño conserva colores y componentes existentes.
No se delegaron agentes ni se exportó contexto a Gemini.
