"""App FastAPI principal: rutas REST, WebSocket, archivos estáticos y ciclo de vida."""
import os
import re
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
from app.routers import test_station, esp32, dymo_remoto, plataforma, activos, tpms, antijammer, speedlocker, sigfox, caiquen, costeo
from app.ssl_cert import ensure_ssl_certificates
from app import modulos as modulos_cat

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
app.include_router(esp32.router)
app.include_router(esp32.agent_router)

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
RUTAS_PUBLICAS = {"/inicio", "/impresora/acceso", "/tpms/acceso", "/antijammer/acceso", "/speedlocker/acceso", "/sigfox/acceso", "/caiquen/acceso", "/api/modulos", "/api/plataforma/entrar", "/login", "/invitacion", "/api/auth/invitacion", "/api/auth/invitacion/aceptar", "/api/auth/login", "/api/auth/olvide", "/api/auth/olvide/estado", "/api/auth/restablecer", "/api/health", "/cert", "/ca", "/favicon.ico"}
PREFIJOS_PUBLICOS = ("/static/css/", "/static/fonts/", "/static/icons/", "/static/js/login.js", "/static/js/inicio.js")


PAGINAS_CONSULTOR = {"/consultar", "/escaner", "/favicon.ico", "/api/health", "/impresora", "/tpms", "/antijammer", "/speedlocker", "/sigfox", "/caiquen", "/documentacion"}   # v1.4.14: Impresora en solo lectura; v1.4.27: TPMS (solo escaneo); v1.4.31: AntiJammer; v1.4.32: SpeedLocker; v1.4.33: Skudo Sigfox
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


def _sin_modulo(ruta: str, metodo: str, mod: Optional[str] = None):
    """v1.4.11: la cuenta no tiene asignado el módulo de la ruta: vuelve al portal (página) o 403 (API, archivos y envíos)."""
    mod = mod or modulos_cat.ESCANER_TQT
    nombre = next((m["nombre"] for m in modulos_cat.MODULOS if m["id"] == mod), mod)
    if ruta.startswith(("/api/", "/ws", "/static/")) or metodo not in ("GET", "HEAD"):
        return JSONResponse(status_code=403, content={"detail": f"Tu cuenta no tiene acceso al módulo {nombre}. Pide a un administrador que te lo asigne.",
                                                       "zona": "modulo", "modulo": mod}, headers={"X-Acceso": "modulo"})
    return RedirectResponse("/inicio?denegado=" + mod, status_code=302)


async def _exigir_sesion(request: Request):
    """None si puede pasar; si no, la respuesta de rechazo (401 JSON para la API, redirección a /login para las páginas)."""
    ruta = request.url.path
    if ruta in RUTAS_PUBLICAS or ruta.startswith(PREFIJOS_PUBLICOS) or ruta.startswith(('/api/stm32/agent/', '/api/dymo/remoto/agente/')):
        return None
    if request.scope.get("type") == "websocket":
        return None
    try:
        u = await run_in_threadpool(usuarios.validar_sesion, request.cookies.get(usuarios.COOKIE))
        db.USUARIO_LOTE.set(u["email"])   # v1.4.24: el lote activo es por usuario (lo leen get_active_lote/resolver_lote_id)
        mod = modulos_cat.modulo_de_ruta(ruta)   # v1.4.14: cada módulo con su permiso (antes todo era Escáner TQT)
        if not (modulos_cat.puede(u, mod) if mod else modulos_cat.alguno(u)) and not ruta.startswith("/api/auth/"):
            return _sin_modulo(ruta, request.method, mod)
        return _permiso_rol(u.get("rol"), ruta, request.method)
    except usuarios.SesionInvalidaError as e:
        if ruta.startswith(("/api/", "/static/", "/ws")) or request.method not in ("GET", "HEAD"):
            return JSONResponse(status_code=401, content={"detail": str(e) or "Inicia sesión."}, headers={"X-Auth": "login"})
        if ruta == "/":   # v1.4.10: sin sesión, la portada es el portal de módulos (el resto sigue yendo al login)
            return RedirectResponse("/inicio", status_code=302)
        destino = ruta + (("?" + request.url.query) if request.url.query else "")
        acceso = modulos_cat.login_de(modulos_cat.modulo_de_ruta(ruta))   # v1.4.17: cada módulo con su pantalla de acceso
        if acceso != "/login":
            return RedirectResponse(acceso + "?next=" + quote(destino, safe=""), status_code=302)
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
app.include_router(test_station.router)
app.include_router(test_station.agent_router)
app.include_router(dymo_remoto.router)   # v1.4.2: DYMO compartida (Raspberry)
app.include_router(plataforma.router)   # v1.4.12: cuentas por módulo desde el portal
app.include_router(activos.router)      # v1.4.14: módulo Impresora (activos con etiqueta DYMO + QR)
app.include_router(tpms.router)         # v1.4.27: módulo TPMS
app.include_router(antijammer.router)   # v1.4.31: módulo Skudo AntiJammer
app.include_router(speedlocker.router)   # v1.4.32: módulo SpeedLocker
app.include_router(sigfox.router)        # v1.4.33: módulo Skudo Sigfox
app.include_router(caiquen.router)       # v1.4.37: módulo Caiquén
for _r in costeo.routers:                # v1.4.34: Costos (cotizador) por módulo: /api/<modulo>/costos
    app.include_router(_r)


def _pagina_acceso(request: Request, archivo: str) -> HTMLResponse:
    html = (settings.STATIC_DIR / archivo).read_text(encoding="utf-8").replace("__VERSION__", settings.APP_VERSION)
    html = _VER_ESTATICO.sub(lambda m: m.group(1) + "?v=" + settings.APP_VERSION, html)
    resp = HTMLResponse(html, headers={"Cache-Control": "no-store"})
    if not request.cookies.get("tqt_cid"):   # misma marca anónima que /login para el límite de intentos
        resp.set_cookie("tqt_cid", secrets.token_hex(12), max_age=31536000, httponly=True, secure=True, samesite="strict", path="/")
    return resp


@app.get("/impresora/acceso", include_in_schema=False)
async def serve_impresora_acceso(request: Request):
    """v1.4.17: inicio de sesión propio del módulo Impresora (misma cuenta y API que /login, otra identidad)."""
    return _pagina_acceso(request, "impresora_acceso.html")


@app.get("/tpms/acceso", include_in_schema=False)
async def serve_tpms_acceso(request: Request):
    """v1.4.27: inicio de sesión propio del módulo TPMS (misma cuenta y API que /login)."""
    return _pagina_acceso(request, "tpms_acceso.html")


@app.get("/tpms", include_in_schema=False)
async def serve_tpms():
    """v1.4.27: módulo TPMS; por ahora solo la ventana de escaneo de QR."""
    return _serve_file(settings.STATIC_DIR / "tpms.html")


@app.get("/antijammer/acceso", include_in_schema=False)
async def serve_antijammer_acceso(request: Request):
    """v1.4.31: inicio de sesión propio del módulo Skudo AntiJammer (misma cuenta y API que /login)."""
    return _pagina_acceso(request, "antijammer_acceso.html")


@app.get("/antijammer", include_in_schema=False)
async def serve_antijammer():
    """v1.4.31: consola del módulo Skudo AntiJammer (clon de TPMS)."""
    return _serve_file(settings.STATIC_DIR / "antijammer.html")


@app.get("/speedlocker/acceso", include_in_schema=False)
async def serve_speedlocker_acceso(request: Request):
    """v1.4.32: inicio de sesión propio del módulo SpeedLocker (misma cuenta y API que /login)."""
    return _pagina_acceso(request, "speedlocker_acceso.html")


@app.get("/speedlocker", include_in_schema=False)
async def serve_speedlocker():
    """v1.4.32: consola del módulo SpeedLocker (clon de Skudo AntiJammer)."""
    return _serve_file(settings.STATIC_DIR / "speedlocker.html")


@app.get("/documentacion", include_in_schema=False)
async def serve_documentacion():
    """v1.4.38: módulo Documentación TEAM HW, presentación cinematográfica de los proyectos (GSAP + ScrollTrigger en /static/documentacion)."""
    return _serve_file(settings.STATIC_DIR / "documentacion" / "index.html")


@app.get("/caiquen/acceso", include_in_schema=False)
async def serve_caiquen_acceso(request: Request):
    """v1.4.37: inicio de sesión propio del módulo Caiquén (misma cuenta y API que /login)."""
    return _pagina_acceso(request, "caiquen_acceso.html")


@app.get("/caiquen", include_in_schema=False)
async def serve_caiquen():
    """v1.4.37: consola del módulo Caiquén (clon de Skudo Sigfox)."""
    return _serve_file(settings.STATIC_DIR / "caiquen.html")


@app.get("/sigfox/acceso", include_in_schema=False)
async def serve_sigfox_acceso(request: Request):
    """v1.4.33: inicio de sesión propio del módulo Skudo Sigfox (misma cuenta y API que /login)."""
    return _pagina_acceso(request, "sigfox_acceso.html")


@app.get("/sigfox", include_in_schema=False)
async def serve_sigfox():
    """v1.4.33: consola del módulo Skudo Sigfox (clon de SpeedLocker)."""
    return _serve_file(settings.STATIC_DIR / "sigfox.html")


@app.get("/impresora", include_in_schema=False)
async def serve_impresora():
    """Módulo Impresora: registro de activos, etiqueta DYMO «ACT 0000» con QR y consulta con el celular."""
    return _serve_file(settings.STATIC_DIR / "impresora.html")


_VER_ESTATICO = re.compile(r"""(/static/[\w./-]+\.(?:js|css))(?:\?v=[\w.]*)?(?=["'])""")


def _serve_file(file_path: Path, fallback_path: Path = None):
    """v1.4.27: cada página sale con `?v=<versión>` en sus JS/CSS. Antes el `?v=` se subía a mano y se quedaba viejo
    (p. ej. sec_inventario.js?v=1352): Cloudflare o el navegador seguían sirviendo el JS anterior tras desplegar."""
    target = file_path if file_path.exists() else fallback_path
    if not (target and target.exists()):
        target = settings.STATIC_DIR / "index.html"
    if target.suffix != ".html":
        return FileResponse(target, headers={"Cache-Control": "no-cache"})
    html = _VER_ESTATICO.sub(lambda m: m.group(1) + "?v=" + settings.APP_VERSION, target.read_text(encoding="utf-8")).replace("__VERSION__", settings.APP_VERSION)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


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
    html = _VER_ESTATICO.sub(lambda m: m.group(1) + "?v=" + settings.APP_VERSION, html)
    resp = HTMLResponse(html)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/login", include_in_schema=False)
async def serve_login(request: Request):
    """Pantalla de acceso (correo y contraseña). Es la única página pública."""
    html = (settings.STATIC_DIR / "login.html").read_text(encoding="utf-8").replace("__VERSION__", settings.APP_VERSION)
    html = _VER_ESTATICO.sub(lambda m: m.group(1) + "?v=" + settings.APP_VERSION, html)
    resp = HTMLResponse(html)   # la versión se inyecta aquí para que la pantalla de acceso siempre muestre la que corre
    resp.headers["Cache-Control"] = "no-store"
    if not request.cookies.get("tqt_cid"):   # marca anónima de este equipo, para el límite de intentos fallidos
        resp.set_cookie("tqt_cid", secrets.token_hex(12), max_age=31536000, httponly=True, secure=True, samesite="strict", path="/")
    return resp


@app.get("/api/modulos", tags=["Config"])
async def modulos(request: Request):
    """Lista pública (solo lectura) de módulos para el portal; con sesión dice a cuáles puede entrar la cuenta (v1.4.11)."""
    try:
        u = await run_in_threadpool(usuarios.validar_sesion, request.cookies.get(usuarios.COOKIE))
    except usuarios.SesionInvalidaError:
        u = None
    yo = {"email": u["email"], "rol": u["rol"], "modulos": u["modulos"]} if u else None
    return {"version": settings.APP_VERSION, "sesion": yo, "modulos": modulos_cat.para_portal(u)}


@app.get("/inicio", include_in_schema=False)
async def serve_inicio(request: Request):
    """Portal de módulos (público): Escáner TQT es un módulo más de la plataforma."""
    html = (settings.STATIC_DIR / "inicio.html").read_text(encoding="utf-8").replace("__VERSION__", settings.APP_VERSION)
    html = _VER_ESTATICO.sub(lambda m: m.group(1) + "?v=" + settings.APP_VERSION, html)
    resp = HTMLResponse(html, headers={"Cache-Control": "no-store"})
    if not request.cookies.get("tqt_cid"):   # v1.4.13: el núcleo I+D tiene ingreso propio; misma marca anónima que /login para el límite de intentos
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
