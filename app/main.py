"""App FastAPI principal: rutas REST, WebSocket, archivos estáticos y ciclo de vida."""
import os
import secrets
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from urllib.parse import quote, urlsplit

from fastapi.concurrency import run_in_threadpool

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import db
from app.routers import admin, api, auth, correo_excel, escaner_remoto, ws, excel_dymo, inventario, inventario_tqtr
from app.services import admin_auth, usuarios
from app.routers import stm32, validacion
from app.ssl_cert import ensure_ssl_certificates

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("escaner_tqt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: inicializa base de datos y certificados SSL."""
    logger.info("Iniciando %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    logger.info("IP LAN detectada: %s", settings.LOCAL_IP)

    # Inicializar Base de Datos con WAL
    db.init_db()
    logger.info("Base de datos SQLite inicializada en: %s", settings.DB_PATH)

    if settings.admin_password:
        try:
            admin_auth.sincronizar()
            logger.info("Área de administración habilitada (contraseña desde TQT_ADMIN_PASSWORD).")
        except Exception as e:  # noqa: BLE001
            logger.error("No se pudo preparar la contraseña de administrador: %s", e)
    else:
        logger.warning("TQT_ADMIN_PASSWORD no está configurada: el área de administración queda DESHABILITADA. "
                       "Defínela (mínimo 8 caracteres) y reinicia para habilitarla.")

    try:
        n = usuarios.sembrar()
        logger.info("Cuentas de usuario listas (%d nuevas).", n)
    except Exception as e:  # noqa: BLE001
        logger.error("No se pudieron preparar las cuentas de usuario: %s", e)
    try:  # Inventario TQTR: tablas, trigger de tarjetas borradas y conciliación de consumos
        from app.services import inventario_tqtr
        inventario_tqtr.sincronizar_consumos()
    except Exception as e:  # noqa: BLE001
        logger.error("No se pudo preparar el inventario TQTR: %s", e)

    # Asegurar certificados SSL autofirmados con SAN
    try:
        ensure_ssl_certificates()
    except Exception as e:
        logger.error("Error al asegurar certificados SSL: %s", e)

    yield

    logger.info("Servidor %s detenido correctamente.", settings.APP_NAME)


# Crear instancia FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Sistema de Escaneo y Emparejamiento de Tarjetas de Producción TQT con HTTPS Móvil y WebSockets.",
    lifespan=lifespan,
    # El explorador de la API (/docs) permite ejecutar cualquier endpoint: solo con TQT_DOCS=1
    docs_url="/docs" if os.getenv("TQT_DOCS") == "1" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if os.getenv("TQT_DOCS") == "1" else None,
)

# Sin CORS: la interfaz se sirve desde este mismo origen (https://IP:8443). Sin middleware CORS el
# navegador bloquea que OTROS sitios abiertos en el celular/PC escriban en la API con JSON.



# Compresión gzip de HTML/JS/CSS/JSON (jsQR pesa 250 KB): en la WiFi de la planta reduce ~65 % la carga inicial del celular.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.exception_handler(OverflowError)
async def _entero_fuera_de_rango(request: Request, exc: OverflowError):
    """Un id/lote/offset mayor que 2^63 no cabe en SQLite: es un dato inválido del cliente, no un error 500 del servidor."""
    return JSONResponse(status_code=422, content={"detail": "Número fuera de rango."})


def origen_distinto(headers) -> bool:
    """True si la petición trae `Origin` y no es el propio servidor (otro sitio web intentando usar la API desde el navegador)."""
    origen = headers.get("origin")
    if origen is None:
        return False  # curl, apps y navegadores en navegación normal (GET) no lo envían
    return urlsplit(origen).netloc.lower() != (headers.get("host") or "").lower()


CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
}


# Rutas que NO piden sesión: la pantalla de acceso, el propio login, el pulso de salud (Docker) y los certificados
# (los celulares instalan la autoridad ANTES de poder entrar). Todo lo demás —páginas, API, WebSocket, archivos— exige sesión.
RUTAS_PUBLICAS = {"/login", "/invitacion", "/api/auth/invitacion", "/api/auth/invitacion/aceptar", "/api/auth/login", "/api/auth/olvide", "/api/auth/olvide/estado", "/api/auth/restablecer", "/api/health", "/cert", "/ca", "/favicon.ico"}
PREFIJOS_PUBLICOS = ("/static/css/", "/static/fonts/", "/static/icons/", "/static/js/login.js")


PAGINAS_CONSULTOR = {"/consultar", "/escaner", "/favicon.ico", "/api/health"}
ROL_NOMBRE = {"general": "General", "consultor": "Consultor"}
# Páginas (y sus copias bajo /static) → zona que se nombra en el aviso "sin acceso" (v1.3.42)
ZONA_PAGINA = {"/": "recibir", "/static/index.html": "recibir", "/emparejar": "emparejar", "/static/emparejar.html": "emparejar",
               "/programar": "programar", "/static/programar.html": "programar", "/monitor": "monitor", "/static/monitor.html": "monitor",
               "/dymo": "dymo", "/static/dymo_preview.html": "dymo"}
ZONAS_ADMIN = ("/admin", "/static/admin.html")
# Lo único que un consultor puede ENVIAR (POST): cerrar sesión y cambiar su propia contraseña
POST_CONSULTOR = {"/api/auth/logout", "/api/auth/cambiar-clave"}
# v1.3.44: descargas de Excel bajo /api/admin/ que cualquier rol puede hacer (GET, solo sesión de usuario; sin clave de admin)
DESCARGAS_ADMIN_LIBRES = {"/api/admin/export/excel"}
# v1.3.44: el consultor también entra a la consola de escritorio (en ella solo ve Dashboard, Tarjetas, Inventario, Consultar y Excel)
PAGINAS_ESCRITORIO = {"/monitor", "/static/monitor.html"}


def _sin_acceso(rol: Optional[str], ruta: str, metodo: str, zona: str, detalle: str):
    """403 JSON (API o envíos) con `X-Acceso: rol` para que el frontend muestre el aviso, o redirección de página
    a una zona permitida con `?denegado=<zona>` (la página destino explica por qué no se pudo entrar)."""
    if ruta.startswith(("/api/", "/ws")) or metodo not in ("GET", "HEAD"):
        return JSONResponse(status_code=403, content={"detail": detalle, "zona": zona, "rol": rol}, headers={"X-Acceso": "rol"})
    destino = "/consultar" if rol == "consultor" else "/"
    return RedirectResponse(f"{destino}?denegado={zona}", status_code=302)


def _permiso_rol(rol: Optional[str], ruta: str, metodo: str):
    """Roles (v1.3.35). administrador: todo. general: todo menos la zona de administración. consultor: solo la página
    Consultar (escaneo) y lecturas de la API; nada que cree, edite, mueva o borre. Cada rechazo explica el motivo (v1.3.42)."""
    if rol == "administrador":
        return None
    nombre = ROL_NOMBRE.get(rol or "", rol or "sin rol")
    if ruta in ZONAS_ADMIN or ruta.startswith(("/api/admin/", "/static/js/admin.js")):
        if ruta == "/api/admin/estado" or (ruta in DESCARGAS_ADMIN_LIBRES and metodo in ("GET", "HEAD")):
            return None
        return _sin_acceso(rol, ruta, metodo, "admin",
                           f"Tu cuenta ({nombre}) no tiene acceso a Administración: solo los administradores pueden entrar. Pide ayuda a un administrador.")
    if rol != "consultor":
        return None
    if ruta.startswith("/api/") or ruta.startswith("/ws"):
        if metodo in ("GET", "HEAD", "OPTIONS") or ruta in POST_CONSULTOR or ruta.startswith(("/ws", "/api/escaner/")):
            return None
        return _sin_acceso(rol, ruta, metodo, "accion",
                           "Tu cuenta es de consulta: puede ver y escanear, pero no crear, editar, mover, enviar ni borrar datos. Pide a un administrador que cambie tu rol si lo necesitas.")
    if ruta in PAGINAS_ESCRITORIO:
        return None
    if ruta in ("/", "/static/index.html") and metodo in ("GET", "HEAD"):
        # Su inicio es Consultar; `?inicio=1` le dice a consultar.html que, en PC/tablet, siga a /monitor (sin bucles:
        # /monitor no redirige a "/" y la marca solo existe en esta redirección).
        return RedirectResponse("/consultar?inicio=1", status_code=302)
    if ruta in ZONA_PAGINA:
        return _sin_acceso(rol, ruta, metodo, ZONA_PAGINA[ruta], "")
    if ruta.startswith("/static/") or ruta in PAGINAS_CONSULTOR:
        return None
    return _sin_acceso(rol, ruta, metodo, "otra", "")


async def _exigir_sesion(request: Request):
    """None si puede pasar; si no, la respuesta de rechazo (401 JSON para la API, redirección a /login para las páginas)."""
    ruta = request.url.path
    if ruta in RUTAS_PUBLICAS or ruta.startswith(PREFIJOS_PUBLICOS) or ruta.startswith('/api/stm32/agent/'):
        return None
    if request.scope.get("type") == "websocket":
        return None
    try:
        u = await run_in_threadpool(usuarios.validar_sesion, request.cookies.get(usuarios.COOKIE))
        return _permiso_rol(u.get("rol"), ruta, request.method)
    except usuarios.SesionInvalidaError as e:
        if ruta.startswith(("/api/", "/static/", "/ws")) or request.method not in ("GET", "HEAD"):
            return JSONResponse(status_code=401, content={"detail": str(e) or "Inicia sesión."}, headers={"X-Auth": "login"})
        destino = ruta + (("?" + request.url.query) if request.url.query else "")
        return RedirectResponse("/login?next=" + quote(destino, safe=""), status_code=302)


@app.middleware("http")
async def seguridad(request: Request, call_next):
    """(1) Anti-CSRF: una petición que CAMBIA datos y viene de otro origen (otra web abierta en el celular/PC) se rechaza.
    (2) Cabeceras de seguridad básicas. (3) La API nunca se guarda en caché (datos de producción y sesión de admin)."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and origen_distinto(request.headers):
        return JSONResponse(status_code=403, content={"detail": "Origen no permitido."}, headers=CABECERAS_SEGURIDAD)
    bloqueo = await _exigir_sesion(request)
    if bloqueo is not None:
        for k, v in CABECERAS_SEGURIDAD.items():
            bloqueo.headers.setdefault(k, v)
        bloqueo.headers.setdefault("Cache-Control", "no-store")
        return bloqueo
    respuesta = await call_next(request)
    for k, v in CABECERAS_SEGURIDAD.items():
        respuesta.headers.setdefault(k, v)
    if request.url.path.startswith("/api/"):
        respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


class StaticNoCache(StaticFiles):
    """Estáticos con `Cache-Control: no-cache`: el navegador revalida (304 barato) y tras cada despliegue
    los celulares no se quedan con JS/CSS viejos."""

    async def get_response(self, path, scope):
        respuesta = await super().get_response(path, scope)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


# Montar archivos estáticos
if settings.STATIC_DIR.exists():
    app.mount("/static", StaticNoCache(directory=str(settings.STATIC_DIR)), name="static")

app.include_router(api.router)
app.include_router(inventario.router)
app.include_router(inventario_tqtr.router)
app.include_router(correo_excel.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(ws.router)
app.include_router(excel_dymo.router)
app.include_router(escaner_remoto.router)
app.include_router(stm32.router)
app.include_router(validacion.router)
app.include_router(validacion.agent_router)


def _serve_file(file_path: Path, fallback_path: Path = None) -> FileResponse:
    target = file_path if file_path.exists() else fallback_path
    if target and target.exists():
        return FileResponse(target, headers={"Cache-Control": "no-cache"})
    return FileResponse(settings.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
async def serve_index():
    """Recibir: visor de cámara y lote de recepción (interfaz móvil del operador)."""
    return _serve_file(settings.STATIC_DIR / "index.html", settings.TEMPLATES_DIR / "mobile_scanner.html")


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    """Algunos clientes piden /favicon.ico aunque las páginas declaren su <link rel=icon>."""
    return _serve_file(settings.STATIC_DIR / "icons" / "icon-192.png")


@app.get("/emparejar", include_in_schema=False)
async def serve_emparejar():
    """Emparejar R1+R2(+R3), tarjetas impares y reemplazo de PCB falladas."""
    return _serve_file(settings.STATIC_DIR / "emparejar.html")


@app.get("/programar", include_in_schema=False)
async def serve_programar():
    """Programar: captura de la MAC y del firmware (solo R1/R2; la R3 no lleva ninguno) después de programar."""
    return _serve_file(settings.STATIC_DIR / "programar.html")


@app.get("/consultar", include_in_schema=False)
async def serve_consultar():
    """Consultar: escanea una etiqueta, el QR de una PCB o una MAC y muestra la ficha completa de la tarjeta."""
    return _serve_file(settings.STATIC_DIR / "consultar.html")


@app.get("/escaner", include_in_schema=False)
async def serve_escaner():
    """Escáner remoto: el celular se vincula a la consola de escritorio (QR) y le envía lo que escanea (v1.3.43)."""
    return _serve_file(settings.STATIC_DIR / "escaner.html")


@app.get("/monitor", include_in_schema=False)
async def serve_monitor():
    """Consola de escritorio para PC. Abre sin contraseña: la clave de supervisor solo protege la zona de administración (/admin)."""
    resp = _serve_file(settings.STATIC_DIR / "monitor.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/admin", include_in_schema=False)
async def serve_admin(request: Request):
    """Administración con contraseña: borrar tarjetas/PCB, vaciar lote, exportar Excel."""
    resp = _serve_file(settings.STATIC_DIR / "admin.html")
    if not request.cookies.get("tqt_cid"):   # marca anónima de este equipo, para el límite de intentos fallidos
        resp.set_cookie("tqt_cid", secrets.token_hex(12), max_age=31536000, httponly=True, secure=True, samesite="strict", path="/")
    return resp


@app.get("/invitacion", include_in_schema=False)
async def serve_invitacion():
    """Activar una cuenta invitada (el token viaja en el #fragmento: nunca llega a registros del servidor ni del proxy)."""
    html = (settings.STATIC_DIR / "invitacion.html").read_text(encoding="utf-8").replace("__VERSION__", settings.APP_VERSION)
    resp = HTMLResponse(html)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/login", include_in_schema=False)
async def serve_login(request: Request):
    """Pantalla de acceso (correo y contraseña). Es la única página pública."""
    html = (settings.STATIC_DIR / "login.html").read_text(encoding="utf-8").replace("__VERSION__", settings.APP_VERSION)
    resp = HTMLResponse(html)   # la versión se inyecta aquí para que la pantalla de acceso siempre muestre la que corre
    resp.headers["Cache-Control"] = "no-store"
    if not request.cookies.get("tqt_cid"):   # marca anónima de este equipo, para el límite de intentos fallidos
        resp.set_cookie("tqt_cid", secrets.token_hex(12), max_age=31536000, httponly=True, secure=True, samesite="strict", path="/")
    return resp


@app.get("/api/health", tags=["Config"])
def health():
    """Pulso para Docker: no revela nada del sistema."""
    return {"ok": True}


@app.get("/dymo", include_in_schema=False)
async def serve_dymo():
    """Estación de vista previa e impresión de etiquetas DYMO."""
    return _serve_file(settings.STATIC_DIR / "dymo_preview.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Sin icono propio: 204 evita un 404 (y un error rojo en consola) en cada página."""
    from fastapi.responses import Response
    return Response(status_code=204, headers={"Cache-Control": "public, max-age=86400"})


def _ca_publica() -> FileResponse:
    from app.ssl_cert import ca_paths
    ca = ca_paths()[0]
    if not ca.exists():
        raise HTTPException(status_code=404, detail="La autoridad certificadora aún no se ha generado.")
    return FileResponse(ca, media_type="application/x-x509-ca-cert", filename="escaner-tqt-ca.crt", headers={"Cache-Control": "no-cache"})


@app.get("/cert", include_in_schema=False)
async def descargar_certificado():
    """Autoridad certificadora LOCAL (solo la parte pública, nunca la llave). Instalarla como confiable en la PC y en los
    celulares hace desaparecer el aviso de "sitio no seguro"; sigue valiendo aunque cambie la IP."""
    return _ca_publica()


@app.get("/ca", include_in_schema=False)
async def descargar_autoridad():
    return _ca_publica()


@app.get("/api/config", tags=["Config"])
def get_config():
    """Configuración pública del servidor para clientes frontend."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ip": settings.LOCAL_IP,
        "url": settings.https_url,
        "ws_url": settings.ws_url,
    }
