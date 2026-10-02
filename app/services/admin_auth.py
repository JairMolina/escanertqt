"""Autenticación del área de administración.

* La contraseña inicial viene SIEMPRE de la variable de entorno `TQT_ADMIN_PASSWORD`; no existe contraseña por defecto.
  Sin la variable, el admin queda deshabilitado (503 con un mensaje claro).
* Se guarda como hash PBKDF2-SHA256 con sal aleatoria en la tabla `ajustes` (nunca en claro). Si el valor de la variable
  cambia (p. ej. el admin olvidó su clave: se cambia la variable y se reinicia), la clave guardada se restablece a la nueva;
  mientras la variable no cambie, una clave cambiada con /cambiar-clave se conserva entre reinicios.
* Login -> token firmado con HMAC-SHA256 (secreto persistente en `ajustes`) que caduca a los 30 minutos y se envía en la
  cabecera `X-Admin-Token`. Todas las comparaciones son en tiempo constante. Cambiar la clave invalida los tokens anteriores.
* Limitador de intentos fallidos por IP: 5 fallos -> bloqueo de 5 minutos. Cada login dura al menos `ADMIN_RETARDO_MS`
  (retardo uniforme, acierte o falle).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.config import settings
from app.database import db

MENSAJE_DESHABILITADO = (
    "El área de administración está deshabilitada: falta configurar la variable de entorno TQT_ADMIN_PASSWORD "
    "(mínimo 8 caracteres) y reiniciar el servidor."
)
MIN_LARGO_CLAVE = 8


class AdminDeshabilitadoError(RuntimeError):
    """No hay contraseña configurada."""


class TokenInvalidoError(ValueError):
    """Token ausente, manipulado o caducado."""


class BloqueadoError(RuntimeError):
    def __init__(self, restante: int):
        super().__init__(f"Demasiados intentos fallidos. Espera {restante} s antes de volver a intentar.")
        self.restante = restante


# ---------------------------------------------------------------- hash de contraseña
def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _unb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def hash_clave(clave: str, iteraciones: Optional[int] = None) -> str:
    """`pbkdf2_sha256$<iteraciones>$<sal>$<hash>` con sal aleatoria de 16 bytes."""
    it = iteraciones or settings.ADMIN_PBKDF2_ITER
    sal = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, it)
    return f"pbkdf2_sha256${it}${_b64(sal)}${_b64(h)}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        alg, it, sal, h = guardado.split("$")
        if alg != "pbkdf2_sha256":
            return False
        calculado = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), _unb64(sal), int(it))
        return hmac.compare_digest(calculado, _unb64(h))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- almacenamiento en `ajustes`
_lock = threading.Lock()


def _get(c, clave: str) -> Optional[str]:
    r = c.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
    return r["valor"] if r else None


def _set(c, clave: str, valor: str) -> None:
    c.execute("INSERT INTO ajustes (clave, valor, updated_at) VALUES (?, ?, datetime('now','localtime')) "
              "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, updated_at = excluded.updated_at", (clave, valor))


def habilitado() -> bool:
    return len(settings.admin_password) >= MIN_LARGO_CLAVE


def sincronizar(db_path: Optional[Path] = None) -> None:
    """Deja en `ajustes` el hash de la clave y el secreto del token. Idempotente y barata cuando no hay cambios."""
    if not habilitado():
        raise AdminDeshabilitadoError(MENSAJE_DESHABILITADO)
    env = settings.admin_password
    with _lock, db.transaction(db_path) as c:
        if not _get(c, "admin_secret"):
            _set(c, "admin_secret", _b64(secrets.token_bytes(32)))
        marca = _get(c, "admin_env_hash")
        if not marca or not verificar_clave(env, marca) or not _get(c, "admin_hash"):
            _set(c, "admin_hash", hash_clave(env))
            _set(c, "admin_env_hash", hash_clave(env))


def verificar_password(password: str, db_path: Optional[Path] = None) -> bool:
    sincronizar(db_path)
    with db.get_db(db_path) as c:
        guardado = _get(c, "admin_hash")
    return bool(guardado) and verificar_clave(password or "", guardado)


def cambiar_clave(actual: str, nueva: str, db_path: Optional[Path] = None) -> None:
    if len(nueva or "") < MIN_LARGO_CLAVE:
        raise ValueError(f"La nueva contraseña debe tener al menos {MIN_LARGO_CLAVE} caracteres.")
    if not verificar_password(actual, db_path):
        raise PermissionError("La contraseña actual no es correcta.")
    if hmac.compare_digest(actual.encode("utf-8"), nueva.encode("utf-8")):
        raise ValueError("La nueva contraseña debe ser distinta de la actual.")
    with _lock, db.transaction(db_path) as c:
        _set(c, "admin_hash", hash_clave(nueva))


# ---------------------------------------------------------------- tokens
def _material(db_path: Optional[Path]) -> Tuple[bytes, str]:
    """(secreto HMAC, huella de la clave vigente). La huella invalida los tokens al cambiar la clave."""
    sincronizar(db_path)
    with db.get_db(db_path) as c:
        secreto, guardado = _get(c, "admin_secret"), _get(c, "admin_hash")
    return _unb64(secreto), hashlib.sha256(guardado.encode("utf-8")).hexdigest()[:12]


def emitir_token(db_path: Optional[Path] = None, ahora: Optional[float] = None) -> Dict[str, object]:
    secreto, huella = _material(db_path)
    t = ahora if ahora is not None else time.time()
    exp = int(t) + settings.ADMIN_TOKEN_TTL
    cuerpo = _b64(json.dumps({"exp": exp, "iat": int(t), "v": huella, "n": secrets.token_hex(4)}, separators=(",", ":")).encode())
    firma = _b64(hmac.new(secreto, cuerpo.encode("ascii"), hashlib.sha256).digest())
    return {"token": f"{cuerpo}.{firma}", "expira_en": settings.ADMIN_TOKEN_TTL, "expira": exp}


def validar_token(token: Optional[str], db_path: Optional[Path] = None, ahora: Optional[float] = None) -> Dict[str, object]:
    if not habilitado():
        raise AdminDeshabilitadoError(MENSAJE_DESHABILITADO)
    if not token or token.count(".") != 1:
        raise TokenInvalidoError("Falta el token de administrador (cabecera X-Admin-Token).")
    cuerpo, firma = token.split(".")
    secreto, huella = _material(db_path)
    esperada = _b64(hmac.new(secreto, cuerpo.encode("ascii", "ignore"), hashlib.sha256).digest())
    if not hmac.compare_digest(esperada.encode("ascii"), firma.encode("ascii", "ignore")):
        raise TokenInvalidoError("Token de administrador inválido.")
    try:
        datos = json.loads(_unb64(cuerpo))
    except (ValueError, TypeError):
        raise TokenInvalidoError("Token de administrador inválido.")
    if not hmac.compare_digest(str(datos.get("v", "")).encode(), huella.encode()):
        raise TokenInvalidoError("La contraseña cambió: vuelve a iniciar sesión.")
    if int(datos.get("exp", 0)) < int(ahora if ahora is not None else time.time()):
        raise TokenInvalidoError("La sesión de administrador caducó: vuelve a iniciar sesión.")
    return datos


# ---------------------------------------------------------------- limitador de intentos por IP
class LimitadorIntentos:
    """Fallos de login por CLIENTE (IP + marca anónima del equipo) -> bloqueo de 5 minutos, y un TOPE GLOBAL de 6 veces ese
    número de fallos entre todos los clientes (quien cambie de marca para saltarse el límite lo agota igual).
    Dentro de Docker todos los equipos llegan con la misma IP, por eso la marca del equipo: que una persona se equivoque 5
    veces no bloquea a las demás. Hilo-seguro; el reloj es inyectable para las pruebas."""
    GLOBAL = "*"

    def __init__(self, reloj=time.monotonic):
        self._reloj = reloj
        self._lock = threading.Lock()
        self._estado: Dict[str, Dict[str, float]] = {}

    def _resto(self, clave: str) -> int:
        e = self._estado.get(clave)
        if not e:
            return 0
        resto = e.get("hasta", 0) - self._reloj()
        if resto <= 0 and e.get("hasta"):
            self._estado.pop(clave, None)  # el bloqueo terminó: empieza de cero
            return 0
        return max(0, int(resto + 0.999)) if resto > 0 else 0

    def restante(self, clave: str) -> int:
        with self._lock:
            return max(self._resto(clave), self._resto(self.GLOBAL))

    def _contar(self, clave: str, maximo: int) -> int:
        e = self._estado.setdefault(clave, {"fallos": 0})
        e["fallos"] += 1
        if e["fallos"] >= maximo:
            e["hasta"] = self._reloj() + settings.ADMIN_BLOQUEO_SEG
            e["fallos"] = 0
            return settings.ADMIN_BLOQUEO_SEG
        return 0

    def fallo(self, clave: str) -> int:
        """Registra un fallo; devuelve los segundos de bloqueo (0 si aún no se bloquea)."""
        with self._lock:
            propio = self._contar(clave, settings.ADMIN_MAX_FALLOS)
            total = self._contar(self.GLOBAL, settings.ADMIN_MAX_FALLOS * 6)
            return max(propio, total)

    def exito(self, clave: str) -> None:
        with self._lock:
            self._estado.pop(clave, None)

    def reiniciar(self) -> None:
        with self._lock:
            self._estado.clear()


limitador = LimitadorIntentos()


def retardo_uniforme(inicio: float) -> None:
    """Duerme lo que falte hasta completar `ADMIN_RETARDO_MS` desde `inicio` (time.monotonic)."""
    falta = settings.ADMIN_RETARDO_MS / 1000 - (time.monotonic() - inicio)
    if falta > 0:
        time.sleep(falta)


def iniciar_sesion(password: str, ip: str, db_path: Optional[Path] = None) -> Dict[str, object]:
    """Valida la clave con limitador y retardo uniforme. Lanza AdminDeshabilitadoError, BloqueadoError o PermissionError."""
    if not habilitado():
        raise AdminDeshabilitadoError(MENSAJE_DESHABILITADO)
    inicio = time.monotonic()
    espera = limitador.restante(ip)
    if espera:
        retardo_uniforme(inicio)
        raise BloqueadoError(espera)
    ok = verificar_password(password, db_path)
    if ok:
        limitador.exito(ip)
        retardo_uniforme(inicio)
        return emitir_token(db_path)
    bloqueo = limitador.fallo(ip)
    retardo_uniforme(inicio)
    if bloqueo:
        raise BloqueadoError(bloqueo)
    raise PermissionError("Contraseña incorrecta.")
