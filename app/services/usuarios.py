"""Cuentas de usuario y sesiones de la app (inicio de sesión con correo y contraseña).

* Tabla `usuarios` (correo, hash PBKDF2-SHA256 con sal, activo). Las cuentas iniciales se siembran al arrancar el servidor
  con la contraseña inicial (TQT_USER_SEED_PASSWORD) y NUNCA se pisan: si alguien ya cambió la suya, se respeta.
* Sesión = cookie firmada (HMAC-SHA256) con correo, caducidad y la huella del hash de la contraseña: al cambiar la
  contraseña o desactivar la cuenta, todas las sesiones de esa cuenta dejan de valer.
* Límite de intentos por equipo y por correo, retardo uniforme y mensaje único para correo desconocido o clave
  incorrecta (no se puede averiguar qué correos existen).
Reutiliza el hash y el limitador del área de administración (admin_auth)."""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import db
from app.services import admin_auth as aa

COOKIE = "tqt_sesion"
CUENTAS_INICIALES = ("developer@skyguardian.mx", "developer4@skyguardian.mx", "developer5@skyguardian.mx", "developer6@skyguardian.mx")
# Sin valor por defecto: si no se define, no se crean cuentas (nunca una clave conocida en el código).
CLAVE_INICIAL = os.getenv("TQT_USER_SEED_PASSWORD", "")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,}$")
MENSAJE_CREDENCIALES = "Correo o contraseña incorrectos."
limitador = aa.LimitadorIntentos()
_DUMMY = None


class SesionInvalidaError(ValueError):
    pass


def normalizar(email: Optional[str]) -> str:
    return str(email or "").strip().lower()


def _asegurar_tabla(c) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS usuarios (email TEXT PRIMARY KEY, hash TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 1, "
              "debe_cambiar INTEGER NOT NULL DEFAULT 1, creado TEXT NOT NULL DEFAULT (datetime('now','localtime')), ultimo_acceso TEXT)")


def sembrar(db_path: Optional[Path] = None, iteraciones: Optional[int] = None) -> int:
    """Crea las cuentas iniciales que falten (idempotente). Devuelve cuántas creó."""
    creadas = 0
    with db.transaction(db_path) as c:
        _asegurar_tabla(c)
        if not CLAVE_INICIAL:
            return 0
        for e in CUENTAS_INICIALES:
            if not c.execute("SELECT 1 FROM usuarios WHERE email = ?", (e,)).fetchone():
                c.execute("INSERT INTO usuarios (email, hash, debe_cambiar) VALUES (?, ?, 1)", (e, aa.hash_clave(CLAVE_INICIAL, iteraciones)))
                creadas += 1
    return creadas


def listar(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    with db.get_db(db_path) as c:
        _asegurar_tabla(c)
        return [dict(r) for r in c.execute("SELECT email, activo, debe_cambiar, creado, ultimo_acceso FROM usuarios ORDER BY email")]


# ---------------------------------------------------------------- sesión firmada
def _secreto(db_path: Optional[Path]) -> bytes:
    with aa._lock, db.transaction(db_path) as c:
        v = aa._get(c, "user_secret")
        if not v:
            v = aa._b64(secrets.token_bytes(32))
            aa._set(c, "user_secret", v)
    return aa._unb64(v)


def _huella(guardado: str) -> str:
    return hashlib.sha256(guardado.encode("utf-8")).hexdigest()[:12]


def _emitir(email: str, guardado: str, db_path: Optional[Path], ahora: Optional[float] = None) -> str:
    t = int(ahora if ahora is not None else time.time())
    cuerpo = aa._b64(json.dumps({"e": email, "exp": t + settings.SESION_HORAS * 3600, "iat": t, "v": _huella(guardado), "n": secrets.token_hex(4)},
                                separators=(",", ":")).encode())
    firma = aa._b64(hmac.new(_secreto(db_path), cuerpo.encode("ascii"), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def emitir_sesion(email: str, db_path: Optional[Path] = None) -> str:
    """Sesión para una cuenta existente y activa (uso interno y pruebas)."""
    email = normalizar(email)
    with db.get_db(db_path) as c:
        _asegurar_tabla(c)
        r = c.execute("SELECT hash FROM usuarios WHERE email = ? AND activo = 1", (email,)).fetchone()
    if not r:
        raise SesionInvalidaError("Cuenta inexistente o desactivada.")
    return _emitir(email, r["hash"], db_path)


def validar_sesion(token: Optional[str], db_path: Optional[Path] = None, ahora: Optional[float] = None) -> Dict[str, Any]:
    """Devuelve {'email', 'debe_cambiar'} o lanza SesionInvalidaError (falla cerrado ante cualquier anomalía)."""
    if not token or token.count(".") != 1 or len(token) > 600:
        raise SesionInvalidaError("Sin sesión.")
    cuerpo, firma = token.split(".")
    try:
        esperada = aa._b64(hmac.new(_secreto(db_path), cuerpo.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(esperada.encode("ascii"), firma.encode("ascii")):
            raise SesionInvalidaError("Sesión inválida.")
        datos = json.loads(aa._unb64(cuerpo))
        if int(datos.get("exp", 0)) < int(ahora if ahora is not None else time.time()):
            raise SesionInvalidaError("La sesión caducó.")
        email = normalizar(datos.get("e"))
    except SesionInvalidaError:
        raise
    except Exception:  # noqa: BLE001  (base64/JSON/ascii corruptos)
        raise SesionInvalidaError("Sesión inválida.")
    with db.get_db(db_path) as c:
        _asegurar_tabla(c)
        r = c.execute("SELECT hash, activo, debe_cambiar FROM usuarios WHERE email = ?", (email,)).fetchone()
    if not r or not r["activo"] or not hmac.compare_digest(_huella(r["hash"]).encode(), str(datos.get("v", "")).encode()):
        raise SesionInvalidaError("La sesión ya no es válida: inicia sesión de nuevo.")
    return {"email": email, "debe_cambiar": bool(r["debe_cambiar"])}


# ---------------------------------------------------------------- inicio de sesión y cambio de clave
def iniciar_sesion(email: str, password: str, cliente: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Valida correo y contraseña. Lanza aa.BloqueadoError (demasiados fallos) o PermissionError (credenciales)."""
    global _DUMMY
    inicio = time.monotonic()
    email = normalizar(email)
    claves = (f"c:{cliente}", f"e:{email}")
    espera = max(limitador.restante(k) for k in claves)
    if espera:
        aa.retardo_uniforme(inicio)
        raise aa.BloqueadoError(espera)
    r = None
    if _EMAIL.match(email):
        with db.get_db(db_path) as c:
            _asegurar_tabla(c)
            r = c.execute("SELECT hash, activo, debe_cambiar FROM usuarios WHERE email = ?", (email,)).fetchone()
    if _DUMMY is None:
        _DUMMY = aa.hash_clave(secrets.token_hex(8))
    ok = aa.verificar_clave(password or "", r["hash"] if r else _DUMMY) and bool(r) and bool(r["activo"])
    if ok:
        for k in claves:
            limitador.exito(k)
        with db.transaction(db_path) as c:
            c.execute("UPDATE usuarios SET ultimo_acceso = datetime('now','localtime') WHERE email = ?", (email,))
        aa.retardo_uniforme(inicio)
        return {"token": _emitir(email, r["hash"], db_path), "email": email, "debe_cambiar": bool(r["debe_cambiar"])}
    bloqueo = max(limitador.fallo(k) for k in claves)
    aa.retardo_uniforme(inicio)
    if bloqueo:
        raise aa.BloqueadoError(bloqueo)
    raise PermissionError(MENSAJE_CREDENCIALES)


def cambiar_clave(email: str, actual: str, nueva: str, db_path: Optional[Path] = None) -> str:
    """Cambia la contraseña (invalida las demás sesiones de la cuenta) y devuelve una sesión nueva."""
    email = normalizar(email)
    if len(nueva or "") < settings.USER_MIN_CLAVE:
        raise ValueError(f"La nueva contraseña debe tener al menos {settings.USER_MIN_CLAVE} caracteres.")
    with db.get_db(db_path) as c:
        _asegurar_tabla(c)
        r = c.execute("SELECT hash FROM usuarios WHERE email = ? AND activo = 1", (email,)).fetchone()
    if not r or not aa.verificar_clave(actual or "", r["hash"]):
        raise PermissionError("La contraseña actual no es correcta.")
    if hmac.compare_digest((actual or "").encode(), nueva.encode()):
        raise ValueError("La nueva contraseña debe ser distinta de la actual.")
    nuevo = aa.hash_clave(nueva)
    with aa._lock, db.transaction(db_path) as c:
        c.execute("UPDATE usuarios SET hash = ?, debe_cambiar = 0 WHERE email = ?", (nuevo, email))
    return _emitir(email, nuevo, db_path)


# ---------------------------------------------------------------- olvidé mi contraseña (aprobación de otra cuenta)
# Flujo: 1) quien olvidó pide el restablecimiento (queda una solicitud pendiente y recibe un `ticket` secreto);
# 2) otra cuenta con sesión abierta la aprueba y ve un código de 6 dígitos (se lo dice de viva voz);
# 3) quien olvidó escribe el código y su contraseña nueva. Nadie teclea la clave de otra persona.
RESET_VIGENCIA_SOLICITUD = 15 * 60
RESET_VIGENCIA_CODIGO = 10 * 60
RESET_MAX_INTENTOS = 5
RESET_MAX_SOLICITUDES = 5          # por equipo, cada 10 minutos
_sol_por_cliente: Dict[str, List[float]] = {}
_sol_lock = threading.Lock()


def _asegurar_tabla_reset(c) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS usuarios_reset (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, "
              "ticket_hash TEXT NOT NULL UNIQUE, creado REAL NOT NULL, estado TEXT NOT NULL DEFAULT 'pendiente', "
              "aprobado_por TEXT, codigo_hash TEXT, expira REAL, intentos INTEGER NOT NULL DEFAULT 0)")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def solicitar_restablecimiento(email: str, cliente: str, db_path: Optional[Path] = None, ahora: Optional[float] = None) -> Dict[str, Any]:
    """Registra la solicitud (si la cuenta existe y está activa) y devuelve SIEMPRE un ticket con el mismo formato:
    no se puede averiguar qué correos existen. Lanza aa.BloqueadoError si el equipo pide demasiadas veces."""
    t = ahora if ahora is not None else time.time()
    with _sol_lock:
        recientes = [x for x in _sol_por_cliente.get(cliente, []) if t - x < 600]
        if len(recientes) >= RESET_MAX_SOLICITUDES:
            raise aa.BloqueadoError(int(600 - (t - recientes[0])) + 1)
        recientes.append(t)
        _sol_por_cliente[cliente] = recientes
    ticket = secrets.token_urlsafe(24)
    email = normalizar(email)
    registrada = False
    if _EMAIL.match(email):
        with db.transaction(db_path) as c:
            _asegurar_tabla(c)
            _asegurar_tabla_reset(c)
            c.execute("DELETE FROM usuarios_reset WHERE creado < ?", (t - 86400,))
            if c.execute("SELECT 1 FROM usuarios WHERE email = ? AND activo = 1", (email,)).fetchone():
                c.execute("UPDATE usuarios_reset SET estado = 'cancelada' WHERE email = ? AND estado IN ('pendiente', 'aprobada')", (email,))
                c.execute("INSERT INTO usuarios_reset (email, ticket_hash, creado) VALUES (?, ?, ?)", (email, _sha(ticket), t))
                registrada = True
    return {"ticket": ticket, "vigencia_seg": RESET_VIGENCIA_SOLICITUD, "registrada": registrada, "email": email}


def estado_solicitud(ticket: str, db_path: Optional[Path] = None, ahora: Optional[float] = None) -> str:
    """pendiente | aprobada | usada | cancelada | expirada. Un ticket desconocido se ve como 'pendiente' (no revela nada)."""
    t = ahora if ahora is not None else time.time()
    with db.get_db(db_path) as c:
        _asegurar_tabla_reset(c)
        r = c.execute("SELECT estado, creado, expira FROM usuarios_reset WHERE ticket_hash = ?", (_sha(ticket or ""),)).fetchone()
    if not r:
        return "pendiente"
    if r["estado"] == "pendiente" and t - r["creado"] > RESET_VIGENCIA_SOLICITUD:
        return "expirada"
    if r["estado"] == "aprobada" and (r["expira"] or 0) < t:
        return "expirada"
    return r["estado"]


def solicitudes_pendientes(ayudante: str, db_path: Optional[Path] = None, ahora: Optional[float] = None) -> List[Dict[str, Any]]:
    t = ahora if ahora is not None else time.time()
    with db.get_db(db_path) as c:
        _asegurar_tabla_reset(c)
        filas = c.execute("SELECT id, email, creado FROM usuarios_reset WHERE estado = 'pendiente' AND creado > ? AND email != ? ORDER BY id",
                          (t - RESET_VIGENCIA_SOLICITUD, normalizar(ayudante))).fetchall()
    return [{"id": r["id"], "email": r["email"], "hace_seg": int(t - r["creado"]), "vence_seg": int(RESET_VIGENCIA_SOLICITUD - (t - r["creado"]))} for r in filas]


def _solicitud_abierta(c, sid: int, ayudante: str, t: float):
    r = c.execute("SELECT id, email, creado FROM usuarios_reset WHERE id = ? AND estado = 'pendiente'", (int(sid),)).fetchone()
    if not r or t - r["creado"] > RESET_VIGENCIA_SOLICITUD:
        raise LookupError("La solicitud ya no está disponible.")
    if normalizar(ayudante) == r["email"]:
        raise PermissionError("No puedes aprobar tu propia solicitud: pide a otra persona.")
    return r


def aprobar_solicitud(sid: int, ayudante: str, db_path: Optional[Path] = None, ahora: Optional[float] = None) -> Dict[str, Any]:
    """Aprueba la solicitud con la sesión de OTRA cuenta y devuelve el código de 6 dígitos (solo se muestra esta vez)."""
    t = ahora if ahora is not None else time.time()
    codigo = f"{secrets.randbelow(10 ** 6):06d}"
    with db.transaction(db_path) as c:
        _asegurar_tabla_reset(c)
        r = _solicitud_abierta(c, sid, ayudante, t)
        c.execute("UPDATE usuarios_reset SET estado = 'aprobada', aprobado_por = ?, codigo_hash = ?, expira = ?, intentos = 0 WHERE id = ?",
                  (normalizar(ayudante), _sha(f"{r['id']}:{codigo}"), t + RESET_VIGENCIA_CODIGO, r["id"]))
    return {"codigo": codigo, "email": r["email"], "vigencia_seg": RESET_VIGENCIA_CODIGO}


def rechazar_solicitud(sid: int, ayudante: str, db_path: Optional[Path] = None, ahora: Optional[float] = None) -> str:
    t = ahora if ahora is not None else time.time()
    with db.transaction(db_path) as c:
        _asegurar_tabla_reset(c)
        r = _solicitud_abierta(c, sid, ayudante, t)
        c.execute("UPDATE usuarios_reset SET estado = 'cancelada' WHERE id = ?", (r["id"],))
    return r["email"]


def restablecer_clave(ticket: str, codigo: str, nueva: str, cliente: str, db_path: Optional[Path] = None, ahora: Optional[float] = None) -> str:
    """Cambia la contraseña con el código aprobado y devuelve el correo. Invalida las sesiones de esa cuenta (cambia el hash).
    PermissionError (mensaje único) si ticket o código no valen; ValueError si la clave nueva no cumple; BloqueadoError por intentos."""
    t = ahora if ahora is not None else time.time()
    k = f"r:{cliente}"
    espera = limitador.restante(k)
    if espera:
        raise aa.BloqueadoError(espera)
    invalido = PermissionError("El código no es válido o ya venció. Pide otra aprobación.")
    if len(nueva or "") < settings.USER_MIN_CLAVE:
        raise ValueError(f"La contraseña nueva debe tener al menos {settings.USER_MIN_CLAVE} caracteres.")
    fallo = False
    with aa._lock, db.transaction(db_path) as c:
        _asegurar_tabla(c)
        _asegurar_tabla_reset(c)
        r = c.execute("SELECT id, email, aprobado_por, codigo_hash, expira, intentos FROM usuarios_reset WHERE ticket_hash = ? AND estado = 'aprobada'",
                      (_sha(ticket or ""),)).fetchone()
        if not r or (r["expira"] or 0) < t:
            fallo = True
        else:
            ayudante_ok = c.execute("SELECT 1 FROM usuarios WHERE email = ? AND activo = 1", (r["aprobado_por"],)).fetchone()
            if not ayudante_ok or not hmac.compare_digest(_sha(f"{r['id']}:{(codigo or '').strip()}").encode(), (r["codigo_hash"] or "").encode()):
                intentos = r["intentos"] + 1
                cancelar = intentos >= RESET_MAX_INTENTOS or not ayudante_ok
                c.execute("UPDATE usuarios_reset SET intentos = ?, estado = ? WHERE id = ?", (intentos, "cancelada" if cancelar else "aprobada", r["id"]))
                fallo = True   # se lanza FUERA de la transacción: si no, el contador de intentos se revertiría
            else:
                c.execute("UPDATE usuarios SET hash = ?, debe_cambiar = 0 WHERE email = ? AND activo = 1", (aa.hash_clave(nueva), r["email"]))
                c.execute("UPDATE usuarios_reset SET estado = 'usada', codigo_hash = NULL WHERE id = ?", (r["id"],))
                c.execute("UPDATE usuarios_reset SET estado = 'cancelada' WHERE email = ? AND estado IN ('pendiente', 'aprobada') AND id != ?", (r["email"], r["id"]))
    if fallo:
        limitador.fallo(k)
        raise invalido
    limitador.exito(k)
    return r["email"]
