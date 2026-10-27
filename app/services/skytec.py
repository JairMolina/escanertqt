"""v1.4.58: alta automática de candados en Skytec (Gestión de Translock > Candados) al imprimir etiquetas.

Por cada armado aprobado se registran 2 candados (R1 y R2): nombre = identificador = nombre completo
(TQT_R1_V30_0029), su MAC y la marca «TQT Nueva versión». Credenciales SOLO en .env (TQT_SKYTEC_*).
"""
import json
import os
import urllib.error
import urllib.request
from typing import Optional

TIMEOUT_S = 20
API_DEFAULT = "https://ws-skytec.skyguardian.mx"
MARCA_TQT = "8"   # get_marcas_candados: 8 = «TQT Nueva versión»


class SkytecNoConfigurado(RuntimeError):
    pass


class SkytecError(RuntimeError):
    pass


class TarjetaNoEncontrada(Exception):
    pass


def _cfg() -> dict:
    return {
        "api": os.getenv("TQT_SKYTEC_API", API_DEFAULT).rstrip("/"),
        "usuario": os.getenv("TQT_SKYTEC_USER", ""),
        "clave": os.getenv("TQT_SKYTEC_PASSWORD", ""),
        "marca": os.getenv("TQT_SKYTEC_MARCA", MARCA_TQT),
    }


def configurado() -> bool:
    c = _cfg()
    return bool(c["usuario"] and c["clave"])


def _post(ruta: str, cuerpo: dict) -> dict:
    req = urllib.request.Request(_cfg()["api"] + ruta, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise SkytecError(f"Skytec respondió HTTP {e.code} en {ruta}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SkytecError(f"Sin conexión con Skytec ({getattr(e, 'reason', e)}).") from e
    except ValueError as e:
        raise SkytecError(f"Skytec devolvió una respuesta no válida en {ruta}.") from e


def _login() -> dict:
    c = _cfg()
    if not configurado():
        raise SkytecNoConfigurado("El alta en Skytec no está configurada (variables TQT_SKYTEC_USER y TQT_SKYTEC_PASSWORD).")
    d = _post("/login_web", {"username": c["usuario"], "password": c["clave"]})
    if not isinstance(d, dict) or not d.get("token"):
        raise SkytecError("Skytec rechazó el inicio de sesión; revisa la cuenta configurada.")
    return d


def nombre_completo(slot: dict) -> str:
    """TQT-R1-V30-0029 → TQT_R1_V30_0029 (el nombre BLE que usa la tarjeta)."""
    return str(slot.get("nombre") or "").strip().upper().replace("-", "_")


def _norm_mac(mac: Optional[str]) -> str:
    return str(mac or "").strip().upper().replace("-", ":")


def registrar(tarjeta_id: int, items: list, operador: str = "") -> None:
    """v1.4.60: guarda los candados que quedaron en Skytec (creados o ya existentes) para marcar la tarjeta."""
    from app.database import db
    with db.get_db() as c:
        for i in items:
            if i.get("estado") in ("creado", "ya_existia"):
                c.execute("INSERT OR REPLACE INTO skytec_candados(tarjeta_id,slot,nombre,mac,estado,operador) VALUES(?,?,?,?,?,?)",
                          (tarjeta_id, i["slot"], i["nombre"], i["mac"], i["estado"], operador))


def alta_tarjeta(tarjeta_id: int, operador: str = "") -> dict:
    """Alta de R1/R2 de una tarjeta y registro local. Lanza SkytecNoConfigurado/SkytecError/TarjetaNoEncontrada."""
    from app.database import db
    tarjeta = db.get_tarjeta_by_id(tarjeta_id)
    if not tarjeta:
        raise TarjetaNoEncontrada("Tarjeta no encontrada.")
    items = alta_armado(tarjeta)
    registrar(tarjeta_id, items, operador)
    return {"ok": all(i["estado"] != "error" for i in items), "items": items}


def alta_armado(tarjeta: dict) -> list:
    """Registra R1 y R2 de la tarjeta. Devuelve [{slot, nombre, mac, estado, detalle}] con estado
    'creado' | 'ya_existia' | 'error'. Idempotente: si el identificador o la MAC ya existen, no duplica."""
    slots = []
    for k in ("r1", "r2"):
        s = tarjeta.get(k) or {}
        slots.append({"slot": k.upper(), "nombre": nombre_completo(s), "mac": _norm_mac(s.get("mac"))})
    faltan = [s["slot"] for s in slots if not s["nombre"] or not s["mac"]]
    if faltan:
        raise SkytecError("Falta nombre o MAC de " + " y ".join(faltan) + "; no se dio de alta en Skytec.")
    sesion = _login()
    token = sesion["token"]
    creado = (str(sesion.get("nombre") or "") + " " + str(sesion.get("apellido_p") or "")).strip() or "Escáner TQT"
    lista = _post("/get_candados", {"headers": {"Authorization": token}}).get("datos") or []
    for s in slots:
        dup = next((x for x in lista if str(x.get("identificador") or "").upper() == s["nombre"]
                    or _norm_mac(x.get("mac_address")) == s["mac"]), None)
        if dup:
            s.update(estado="ya_existia", detalle=f"Ya estaba registrado como «{dup.get('nombre')}» ({_norm_mac(dup.get('mac_address'))}).")
            continue
        form = {"id_candado": "0", "nombre": s["nombre"], "identificador": s["nombre"], "mac": s["mac"], "marca": _cfg()["marca"]}
        try:
            r = _post("/upd_candado", {"headers": {"Authorization": token}, "upd": 0, "creado": creado, "formDataJSON": form})
            ok = str(r.get("respuesta", "")).lower() == "success"
            s.update(estado="creado" if ok else "error",
                     detalle="Candado creado en Skytec correctamente." if ok else f"Skytec respondió: {r.get('respuesta') or r}")
        except SkytecError as e:
            s.update(estado="error", detalle=str(e))
    return slots
