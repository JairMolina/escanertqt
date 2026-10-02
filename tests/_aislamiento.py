"""Aislamiento de los tests: BD, Excel mensuales y exports viven en una carpeta temporal.

DEBE importarse ANTES que cualquier módulo `app.*` (app.config lee las variables de entorno al importarse):

    import _aislamiento  # noqa: F401  (primera línea de cada test)

Así ningún test puede tocar `tqt_produccion.db` ni crear archivos en el proyecto.
"""
import atexit
import itertools
import os
import shutil
import sys
import tempfile
import threading
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*Data Validation extension.*")

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

if "app.config" in sys.modules:  # ya se importó sin aislamiento: abortar antes de escribir en la BD real
    _cfg = sys.modules["app.config"].settings
    if "tqt_tests_" not in str(_cfg.DB_PATH):
        raise RuntimeError(f"Los tests apuntan a una BD real ({_cfg.DB_PATH}). Importa `_aislamiento` primero.")

TMP = Path(tempfile.mkdtemp(prefix="tqt_tests_"))
os.environ["TQT_DB_PATH"] = str(TMP / "tqt_test.db")
os.environ["TQT_EXCEL_DIR"] = str(TMP / "excel_mensual")
os.environ["TQT_EXPORTS_DIR"] = str(TMP / "exports")
os.environ["TQT_BACKUP_DIR"] = str(TMP / "respaldos")
os.environ.pop("TQT_ADMIN_PASSWORD", None)  # el admin solo se habilita dentro de los tests que lo piden
atexit.register(lambda: shutil.rmtree(TMP, ignore_errors=True))

_lock = threading.Lock()
_macs = itertools.count(1)
_lotes = itertools.count(1)
_nums = itertools.count(1000)


def verificar_aislamiento() -> None:
    """Falla si la configuración activa no es la temporal."""
    from app.config import settings
    if Path(settings.DB_PATH).resolve() != (TMP / "tqt_test.db").resolve():
        raise RuntimeError(f"Tests sin aislamiento: DB_PATH={settings.DB_PATH}")


def mac_unica() -> str:
    """MAC unicast administrada localmente, única en todo el proceso de tests."""
    with _lock:
        n = next(_macs)
    return "02:" + ":".join(f"{b:02X}" for b in n.to_bytes(5, "big"))


def num_unico() -> str:
    """Número de tarjeta de 4 dígitos (1000-9999)."""
    with _lock:
        return f"{next(_nums):04d}"


def nuevo_lote(activar: bool = True, mes: int = 9, anio: int = 2026) -> dict:
    """Crea un lote con código único en la BD de pruebas."""
    from app.database import db
    verificar_aislamiento()
    db.init_db()
    with _lock:
        n = next(_lotes)
    return db.create_lote(f"T-{os.getpid()}-{n}", mes, anio, activo=activar)


def crear_par(lote_id=None, num=None, r3=False, macs=True, path=None, version="30") -> dict:
    """Arma una tarjeta v2 completa con el flujo real: PCB recibidas -> confirmadas -> emparejadas -> MAC tecleadas.
    `path`: BD alterna (por defecto la de pruebas). Sin `num` toma la siguiente serie libre (salta las que otros tests
    ya ocuparon con altas automáticas). Devuelve la tarjeta (dict de db.get_tarjeta_by_id)."""
    from app.database import db, inventario as inv
    from app.database.db import ConflictoError
    tipos = ("R1", "R2", "R3") if r3 else ("R1", "R2")
    while True:
        serie = num or num_unico()
        try:
            with db.transaction(path) as c:
                ids = {t: inv.registrar_manual(t, version, serie, conn=c)["pcbs"][0]["id"] for t in tipos}
                inv.confirmar_recepcion(list(ids.values()), conn=c)
                tarjeta = inv.crear_tarjeta(lote_id, serie, ids["R1"], ids["R2"], ids.get("R3"), conn=c)
                if macs:
                    for t in ("R1", "R2"):
                        inv.set_mac(ids[t], mac_unica(), conn=c)
                return db.get_tarjeta_by_id(tarjeta["id"], c)
        except ConflictoError:
            if num:
                raise  # un número pedido explícitamente que ya existe es un error del test


def recibir_ws(ws, timeout: float = 5.0, evento: str = None) -> dict:
    """Siguiente mensaje JSON del WebSocket (opcionalmente el primero con ese `evento`), con timeout.
    Un ws.receive_text() sin timeout deja la suite colgada para siempre si el evento nunca llega."""
    import json
    import threading
    import time
    limite = time.monotonic() + timeout
    while True:
        caja = {}

        def leer():
            try:
                caja["m"] = ws.receive_text()
            except Exception as e:  # noqa: BLE001
                caja["e"] = e

        hilo = threading.Thread(target=leer, daemon=True)
        hilo.start()
        hilo.join(max(0.05, limite - time.monotonic()))
        if hilo.is_alive():
            raise AssertionError(f"El WebSocket no entregó {evento or 'ningún mensaje'} en {timeout}s")
        if "e" in caja:
            raise caja["e"]
        msg = json.loads(caja["m"])
        if evento is None or msg.get("evento") == evento:
            return msg


# ---------------------------------------------------------------- inicio de sesión automático (v1.3.16)
# Toda la app exige sesión: los TestClient de la suite se presentan siempre con una sesión válida de la primera cuenta
# inicial EN LA BD ACTIVA en ese momento (algunas clases de prueba cambian settings.DB_PATH). Las pruebas de seguridad usan
# `cliente_sin_sesion()` para comprobar justo lo contrario.
_sesiones = {}


def _token_pruebas() -> str:
    from app.config import settings
    from app.database import db
    from app.services import usuarios
    clave = str(settings.DB_PATH)
    with _lock:
        t = _sesiones.get(clave)
        if t is not None:
            try:
                usuarios.validar_sesion(t)
                return t
            except usuarios.SesionInvalidaError:
                pass
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        t = _sesiones[clave] = usuarios.emitir_sesion(usuarios.CUENTAS_INICIALES[0])
        return t


def _instalar_autologin() -> None:
    from starlette.testclient import TestClient
    if getattr(TestClient, "_tqt_autologin", False):
        return
    request_original, ws_original = TestClient.request, TestClient.websocket_connect

    def _con_sesion(self):
        if not getattr(self, "_sin_sesion", False):
            from app.services import usuarios
            self.cookies.set(usuarios.COOKIE, _token_pruebas())

    def request(self, *args, **kwargs):
        _con_sesion(self)
        return request_original(self, *args, **kwargs)

    def websocket_connect(self, *args, **kwargs):
        _con_sesion(self)
        return ws_original(self, *args, **kwargs)

    TestClient.request, TestClient.websocket_connect = request, websocket_connect
    TestClient._tqt_autologin = True


def cliente_sin_sesion(app, https: bool = True):
    """TestClient SIN sesión (https para que la cookie Secure de /api/auth/login viaje de vuelta)."""
    from starlette.testclient import TestClient
    c = TestClient(app, base_url="https://testserver" if https else "http://testserver")
    c._sin_sesion = True
    c.cookies.clear()
    return c


_instalar_autologin()
