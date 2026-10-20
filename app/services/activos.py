"""v1.4.14: módulo Impresora. Registro de activos con etiqueta DYMO «ACT 0000» y QR.

Cada activo tiene un `numero` único (ACT-0001) y una bitácora propia (`activos_eventos`). La etiqueta lleva un QR con la
URL `<base>/impresora?activo=ACT-0001`, que el celular abre para consultar el activo.
Las tablas se crean de forma idempotente al usarse (`_asegurar`); no se toca el esquema del resto de la aplicación.
"""
import json
import logging
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

from app.database import db
from app.services.dymo_service import DymoService

log = logging.getLogger(__name__)

NUMERO_MAX = 99999
ESTADOS = (
    {"id": "activo", "nombre": "Activo"},
    {"id": "resguardo", "nombre": "En resguardo"},
    {"id": "reparacion", "nombre": "En reparación"},
    {"id": "baja", "nombre": "Baja"},
)
IDS_ESTADO = tuple(e["id"] for e in ESTADOS)
# Campos de texto editables y su largo máximo (el nombre es obligatorio).
TEXTOS = {"nombre": 120, "categoria": 80, "departamento": 80, "marca": 80, "modelo": 80, "serie": 80, "ubicacion": 120, "responsable": 120, "notas": 2000}
EDITABLES = ("numero",) + tuple(TEXTOS) + ("estado", "fecha_adquisicion", "valor", "caracteristicas")
MAX_CARACTERISTICAS = 40
LIMITE_DEFECTO = 2000   # cubre todo el inventario: el frontend filtra en el cliente
LIMITE_MAXIMO = 5000

_RE_URL = re.compile(r"activo=([^&#\s]+)", re.IGNORECASE)
_RE_CODIGO = re.compile(r"^(?:ACT)?[\s\-_]*(\d{1,6})$", re.IGNORECASE)


class ActivoNoEncontrado(LookupError):
    """El código o número pedido no corresponde a ningún activo (HTTP 404)."""


class ActivoDuplicado(ValueError):
    """El número de activo ya está en uso (HTTP 409)."""


def _asegurar() -> None:
    """Crea las tablas si faltan (idempotente, no altera una BD existente)."""
    with db.get_db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS activos(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              numero INTEGER NOT NULL UNIQUE,
              nombre TEXT NOT NULL,
              categoria TEXT NOT NULL DEFAULT '',
              departamento TEXT NOT NULL DEFAULT '',
              caracteristicas TEXT NOT NULL DEFAULT '',
              marca TEXT NOT NULL DEFAULT '',
              modelo TEXT NOT NULL DEFAULT '',
              serie TEXT NOT NULL DEFAULT '',
              ubicacion TEXT NOT NULL DEFAULT '',
              responsable TEXT NOT NULL DEFAULT '',
              estado TEXT NOT NULL DEFAULT 'activo',
              fecha_adquisicion TEXT,
              valor REAL,
              notas TEXT NOT NULL DEFAULT '',
              creado_por TEXT NOT NULL DEFAULT '',
              creado_en TEXT NOT NULL,
              actualizado_en TEXT NOT NULL,
              impresiones INTEGER NOT NULL DEFAULT 0,
              ultima_impresion TEXT
            );
            CREATE TABLE IF NOT EXISTS activos_eventos(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              activo_id INTEGER NOT NULL REFERENCES activos(id),
              evento TEXT NOT NULL,
              detalle TEXT NOT NULL DEFAULT '',
              por TEXT NOT NULL DEFAULT '',
              creado_en TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS activos_eventos_activo ON activos_eventos(activo_id, id);
            """
        )
        # v1.4.15: columnas nuevas en una tabla creada por v1.4.14 (migración idempotente)
        existentes = {r["name"] for r in c.execute("PRAGMA table_info(activos)")}
        for col in ("departamento", "caracteristicas"):
            if col not in existentes:
                c.execute(f"ALTER TABLE activos ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ códigos
def codigo_de(numero: int) -> str:
    return f"ACT-{int(numero):04d}"


def etiqueta_de(numero: int) -> str:
    return f"ACT {int(numero):04d}"


def numero_de(texto: Any) -> int:
    """Número de activo desde «ACT-0001», «ACT 0001», «act0001», «1» o una URL con `activo=ACT-0001`. ValueError si no se reconoce."""
    t = str(texto or "").strip()
    m = _RE_URL.search(t)
    if m:
        t = unquote(m.group(1)).strip()
    m = _RE_CODIGO.match(t)
    if not m or not 1 <= int(m.group(1)) <= NUMERO_MAX:
        raise ValueError(f"Código de activo no reconocido: «{str(texto or '')[:60]}».")
    return int(m.group(1))


def url_activo(base: str, numero: int) -> str:
    return f"{base.rstrip('/')}/impresora?activo={codigo_de(numero)}"


# ------------------------------------------------------------------ validación
def _caracteristicas_json(v: Any) -> str:
    """Características (lista [{etiqueta, valor}] o dict etiqueta→valor) → JSON objeto ordenado; vacías se descartan."""
    pares = v.items() if isinstance(v, dict) else [(x.get("etiqueta"), x.get("valor")) for x in (v or []) if isinstance(x, dict)]
    out: Dict[str, str] = {}
    for e, val in pares:
        e, val = " ".join(str(e or "").split()), str(val if val is not None else "").strip()
        if not e or not val:
            continue
        if len(e) > 60 or len(val) > 500:
            raise ValueError("Cada característica admite etiqueta de hasta 60 y valor de hasta 500 caracteres.")
        out[e] = val
    if len(out) > MAX_CARACTERISTICAS:
        raise ValueError(f"Máximo {MAX_CARACTERISTICAS} características por activo.")
    return json.dumps(out, ensure_ascii=False) if out else ""


def _caracteristicas_dict(texto: Optional[str]) -> Dict[str, str]:
    try:
        d = json.loads(texto) if texto else {}
    except ValueError:
        log.warning("Activo con características ilegibles; se omiten.")
        return {}
    return {k: str(x) for k, x in d.items()} if isinstance(d, dict) else {}


def _caracteristicas_lista(texto: Optional[str]) -> List[Dict[str, str]]:
    return [{"etiqueta": k, "valor": x} for k, x in _caracteristicas_dict(texto).items()]


def _limpiar(datos: Dict[str, Any], parcial: bool) -> Dict[str, Any]:
    """Normaliza y valida los campos recibidos (solo los presentes si `parcial`). ValueError con mensaje legible."""
    out: Dict[str, Any] = {}
    for k in EDITABLES:
        if k not in datos:
            continue
        v = datos[k]
        if k == "numero":
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= NUMERO_MAX:
                raise ValueError(f"El número debe estar entre 1 y {NUMERO_MAX}.")
            out[k] = v
        elif k in TEXTOS:
            s = " ".join(str(v or "").split()) if k != "notas" else str(v or "").strip()
            if k == "nombre" and not s:
                raise ValueError("El nombre del activo es obligatorio.")
            if len(s) > TEXTOS[k]:
                raise ValueError(f"«{k}» admite hasta {TEXTOS[k]} caracteres.")
            out[k] = s
        elif k == "caracteristicas":
            out[k] = _caracteristicas_json(v)
        elif k == "estado":
            s = str(v or "activo").strip().lower()
            if s not in IDS_ESTADO:
                raise ValueError(f"Estado inválido. Usa: {', '.join(IDS_ESTADO)}.")
            out[k] = s
        elif k == "fecha_adquisicion":
            s = str(v or "").strip()
            if s:
                try:
                    datetime.strptime(s, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("La fecha de adquisición debe ser AAAA-MM-DD.")
            out[k] = s or None
        elif k == "valor":
            if v in (None, ""):
                out[k] = None
            else:
                try:
                    n = float(v)
                except (TypeError, ValueError):
                    raise ValueError("El valor debe ser un número.")
                if not 0 <= n <= 1e12 or n != n:
                    raise ValueError("El valor debe estar entre 0 y 1,000,000,000,000.")
                out[k] = round(n, 2)
    if not parcial and not out.get("nombre"):
        raise ValueError("El nombre del activo es obligatorio.")
    return out


# ------------------------------------------------------------------ lectura
def _activo(r: sqlite3.Row, base: str) -> Dict[str, Any]:
    d = dict(r)
    d["codigo"] = codigo_de(d["numero"])
    d["etiqueta"] = etiqueta_de(d["numero"])
    d["qr"] = url_activo(base, d["numero"])
    d["caracteristicas"] = _caracteristicas_lista(d.get("caracteristicas"))
    return {k: d[k] for k in ("id", "numero", "codigo", "etiqueta", "nombre", "categoria", "departamento", "caracteristicas", "marca", "modelo", "serie", "ubicacion",
                              "responsable", "estado", "fecha_adquisicion", "valor", "notas", "creado_por", "creado_en",
                              "actualizado_en", "impresiones", "ultima_impresion", "qr")}


def _fila_por_numero(c: sqlite3.Connection, numero: int) -> sqlite3.Row:
    r = c.execute("SELECT * FROM activos WHERE numero=?", (numero,)).fetchone()
    if not r:
        raise ActivoNoEncontrado(f"El activo {codigo_de(numero)} no existe.")
    return r


def _siguiente(c: sqlite3.Connection) -> int:
    return (c.execute("SELECT COALESCE(MAX(numero),0) n FROM activos").fetchone()["n"] or 0) + 1


def siguiente() -> Dict[str, Any]:
    _asegurar()
    with db.get_db() as c:
        n = _siguiente(c)
    return {"numero": n, "codigo": codigo_de(n), "etiqueta": etiqueta_de(n)}


def _evento(c: sqlite3.Connection, activo_id: int, evento: str, detalle: str, por: str) -> None:
    c.execute("INSERT INTO activos_eventos(activo_id,evento,detalle,por,creado_en) VALUES(?,?,?,?,?)",
              (activo_id, evento, (detalle or "")[:500], por or "", _ahora()))


def _fecha_filtro(v: Optional[str], nombre: str) -> str:
    s = (v or "").strip()
    if s:
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"«{nombre}» debe ser AAAA-MM-DD.")
    return s


def _filtros(q: str = "", estado: str = "", categoria: str = "", departamento: str = "", desde: str = "", hasta: str = "",
             impresa: Optional[int] = None, codigos: Optional[List[Any]] = None) -> Tuple[str, List[Any]]:
    """Cláusula WHERE y argumentos de los filtros del listado y de los lotes. `desde`/`hasta` son la fecha de alta
    (`creado_en`, hora local) inclusive; con solo `desde` es ese día. `impresa`: 0 = nunca impresa, 1 = ya impresa."""
    donde: List[str] = []
    args: List[Any] = []
    q = (q or "").strip()
    if q:
        variantes = [q] + ([q.replace(" ", "-")] if " " in q else [])
        campos = ("'ACT-' || printf('%04d', numero)", "nombre", "serie", "marca", "modelo", "ubicacion", "responsable", "departamento",
                  "caracteristicas")
        partes = []
        for v in variantes:
            patron = "%" + v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            for campo in campos:
                partes.append(f"{campo} LIKE ? ESCAPE '\\'")
                args.append(patron)
        donde.append("(" + " OR ".join(partes) + ")")
    if estado:
        if estado not in IDS_ESTADO:
            raise ValueError(f"Estado inválido. Usa: {', '.join(IDS_ESTADO)}.")
        donde.append("estado=?")
        args.append(estado)
    if categoria:
        donde.append("categoria=?")
        args.append(categoria)
    if departamento:
        donde.append("departamento=?")
        args.append(departamento)
    desde, hasta = _fecha_filtro(desde, "desde"), _fecha_filtro(hasta, "hasta")
    if desde and hasta:
        if hasta < desde:
            raise ValueError("«hasta» no puede ser anterior a «desde».")
        donde.append("substr(creado_en,1,10) BETWEEN ? AND ?")
        args += [desde, hasta]
    elif desde:
        donde.append("substr(creado_en,1,10)=?")
        args.append(desde)
    elif hasta:
        donde.append("substr(creado_en,1,10)<=?")
        args.append(hasta)
    if impresa is not None:
        if impresa not in (0, 1):
            raise ValueError("«impresa» debe ser 0 o 1.")
        donde.append("impresiones=0" if impresa == 0 else "impresiones>0")
    if codigos is not None:
        nums = []
        for cod in codigos:
            try:
                nums.append(numero_de(cod))
            except ValueError:
                continue   # un código irreconocible simplemente no coincide con nada
        if not nums:
            donde.append("0")
        else:
            donde.append(f"numero IN ({','.join('?' * len(nums))})")
            args += sorted(set(nums))
    return ((" WHERE " + " AND ".join(donde)) if donde else ""), args


def listar(base: str, q: str = "", estado: str = "", categoria: str = "", limite: int = LIMITE_DEFECTO, departamento: str = "",
           desde: str = "", hasta: str = "", impresa: Optional[int] = None, codigos: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Activos filtrados (numero descendente), el total que coincide y el siguiente número libre."""
    _asegurar()
    limite = max(1, min(int(limite or LIMITE_DEFECTO), LIMITE_MAXIMO))
    clausula, args = _filtros(q, estado, categoria, departamento, desde, hasta, impresa, codigos)
    with db.get_db() as c:
        total = c.execute(f"SELECT COUNT(*) n FROM activos{clausula}", args).fetchone()["n"]
        filas = c.execute(f"SELECT * FROM activos{clausula} ORDER BY numero DESC LIMIT ?", args + [limite]).fetchall()
        sig = _siguiente(c)
    return {"items": [_activo(r, base) for r in filas], "total": total, "siguiente": {"numero": sig, "codigo": codigo_de(sig)}}


def resolver_lote(maximo: int, codigos: Optional[List[Any]] = None, **filtros: Any) -> List[Dict[str, Any]]:
    """Activos de un lote de impresión, por códigos o por filtros (q, estado, categoria, departamento, desde, hasta, impresa),
    en orden de número ascendente. ValueError si no hay ningún criterio, no coincide nada o se excede `maximo`."""
    hay_filtro = any(v not in (None, "") for v in filtros.values())
    if codigos is None and not hay_filtro:
        raise ValueError("Indica los códigos o al menos un filtro para armar el lote.")
    if codigos is not None and len(codigos) > maximo:
        raise ValueError(f"Un lote admite hasta {maximo} etiquetas (pediste {len(codigos)}).")
    _asegurar()
    clausula, args = _filtros(codigos=codigos, **filtros)
    with db.get_db() as c:
        total = c.execute(f"SELECT COUNT(*) n FROM activos{clausula}", args).fetchone()["n"]
        if total > maximo:
            raise ValueError(f"El lote tiene {total} activos y el máximo es {maximo}; acota el filtro.")
        filas = c.execute(f"SELECT numero,nombre FROM activos{clausula} ORDER BY numero", args).fetchall()
    if not filas:
        raise ActivoNoEncontrado("Ningún activo coincide con el lote pedido.")
    return [{"numero": r["numero"], "codigo": codigo_de(r["numero"]), "etiqueta": etiqueta_de(r["numero"]), "nombre": r["nombre"]} for r in filas]


def catalogos() -> Dict[str, Any]:
    """Valores distintos ya usados (para autocompletar) y los estados disponibles."""
    _asegurar()
    with db.get_db() as c:
        def distintos(col: str) -> List[str]:
            return [r[0] for r in c.execute(f"SELECT DISTINCT {col} FROM activos WHERE {col}<>'' ORDER BY {col} COLLATE NOCASE")]
        return {"categorias": distintos("categoria"), "ubicaciones": distintos("ubicacion"),
                "responsables": distintos("responsable"), "departamentos": distintos("departamento"),
                "estados": [dict(e) for e in ESTADOS]}


def obtener(codigo: Any, base: str) -> Dict[str, Any]:
    """Activo con su bitácora (`eventos`, el más reciente primero). ValueError si el código no se reconoce; ActivoNoEncontrado si no existe."""
    n = numero_de(codigo)
    _asegurar()
    with db.get_db() as c:
        r = _fila_por_numero(c, n)
        ev = [dict(e) for e in c.execute(
            "SELECT evento,detalle,por,creado_en FROM activos_eventos WHERE activo_id=? ORDER BY id DESC LIMIT 100", (r["id"],))]
    return dict(_activo(r, base), eventos=ev)


# ------------------------------------------------------------------ escritura
def _insertar(c: sqlite3.Connection, numero: int, v: Dict[str, Any], por: str, evento: str, detalle: str) -> int:
    """INSERT de un activo ya validado dentro de la transacción `c`, con su evento. Devuelve el id."""
    ahora = _ahora()
    cur = c.execute(
        "INSERT INTO activos(numero,nombre,categoria,departamento,caracteristicas,marca,modelo,serie,ubicacion,responsable,estado,"
        "fecha_adquisicion,valor,notas,creado_por,creado_en,actualizado_en) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (numero, v["nombre"], v.get("categoria", ""), v.get("departamento", ""), v.get("caracteristicas", ""), v.get("marca", ""),
         v.get("modelo", ""), v.get("serie", ""), v.get("ubicacion", ""), v.get("responsable", ""), v.get("estado", "activo"),
         v.get("fecha_adquisicion"), v.get("valor"), v.get("notas", ""), por or "", ahora, ahora))
    _evento(c, cur.lastrowid, evento, detalle, por)
    return cur.lastrowid


def _modificar(c: sqlite3.Connection, r: sqlite3.Row, v: Dict[str, Any], por: str, evento: str, prefijo: str = "") -> Dict[str, Any]:
    """UPDATE de los campos que realmente cambian (dentro de `c`) y su evento. Devuelve {campo: nuevo valor}."""
    reales = {k: val for k, val in v.items() if r[k] != val}
    if not reales:
        return {}
    if "numero" in reales and c.execute("SELECT 1 FROM activos WHERE numero=?", (reales["numero"],)).fetchone():
        raise ActivoDuplicado(f"El número {codigo_de(reales['numero'])} ya está registrado.")
    sets = ",".join(f"{k}=?" for k in reales)
    c.execute(f"UPDATE activos SET {sets},actualizado_en=? WHERE id=?", [*reales.values(), _ahora(), r["id"]])
    partes = ["características actualizadas" if k == "caracteristicas" else
              f"{k}: {'' if r[k] is None else r[k]} → {'' if val is None else val}" for k, val in reales.items()]
    _evento(c, r["id"], evento, prefijo + "; ".join(partes), por)
    return reales


def crear(datos: Dict[str, Any], por: str, base: str) -> Dict[str, Any]:
    """Alta. Sin `numero` toma el siguiente libre (max+1). ActivoDuplicado si el número ya existe."""
    v = _limpiar(datos, parcial=False)
    _asegurar()
    try:
        with db.transaction() as c:
            numero = v.get("numero") or _siguiente(c)
            if c.execute("SELECT 1 FROM activos WHERE numero=?", (numero,)).fetchone():
                raise ActivoDuplicado(f"El número {codigo_de(numero)} ya está registrado.")
            _insertar(c, numero, v, por, "ALTA", f"Alta de {codigo_de(numero)}: {v['nombre']}")
    except sqlite3.IntegrityError as e:   # carrera: otro operador tomó el número entre la lectura y el INSERT
        log.warning("Activo: número duplicado al crear (%s)", e)
        raise ActivoDuplicado(f"El número {codigo_de(v.get('numero') or 0)} ya está registrado.")
    db.log_evento("ACTIVO_ALTA", valor=codigo_de(numero), detalle=v["nombre"], operador=por)
    return obtener(numero, base)


def actualizar(codigo: Any, cambios: Dict[str, Any], por: str, base: str) -> Dict[str, Any]:
    """Edición parcial. Registra el evento EDICION con los campos que cambiaron; ActivoDuplicado si el nuevo número choca."""
    n = numero_de(codigo)
    v = _limpiar(cambios, parcial=True)
    _asegurar()
    try:
        with db.transaction() as c:
            reales = _modificar(c, _fila_por_numero(c, n), v, por, "EDICION")
    except sqlite3.IntegrityError:
        raise ActivoDuplicado(f"El número {codigo_de(v.get('numero') or 0)} ya está registrado.")
    if v.get("numero"):
        n = v["numero"]
    if reales:
        db.log_evento("ACTIVO_EDICION", valor=codigo_de(n), detalle=", ".join(reales), operador=por)
    return obtener(n, base)


def registrar_impresion(codigo: Any, por: str, detalle: str = "") -> None:
    """Suma una impresión, guarda la fecha de la última y deja el evento IMPRESION."""
    n = numero_de(codigo)
    _asegurar()
    with db.transaction() as c:
        r = _fila_por_numero(c, n)
        ahora = _ahora()
        c.execute("UPDATE activos SET impresiones=impresiones+1,ultima_impresion=? WHERE id=?", (ahora, r["id"]))
        _evento(c, r["id"], "IMPRESION", detalle, por)


# ------------------------------------------------------------------ etiqueta
def _datos_etiqueta(codigo: Any, base: str) -> Tuple[str, str]:
    """(url del QR, texto «ACT 0001») del activo; falla con ActivoNoEncontrado si no existe."""
    n = numero_de(codigo)
    _asegurar()
    with db.get_db() as c:
        _fila_por_numero(c, n)
    return url_activo(base, n), etiqueta_de(n)


def svg_etiqueta(codigo: Any, base: str, formato: Optional[str] = None, borde: bool = False) -> str:
    return DymoService.generate_activo_svg(*_datos_etiqueta(codigo, base), formato, borde)


def xml_etiqueta(codigo: Any, base: str, tipo: str = "dymo", formato: Optional[str] = None) -> str:
    """XML para DYMO Connect (`dymo`, DCD) o DYMO Label v8 (`label`)."""
    d = _datos_etiqueta(codigo, base)
    return DymoService.generate_activo_dcd_xml(*d, formato) if tipo == "dymo" else DymoService.generate_activo_xml(*d, formato)


def archivo_etiqueta(codigo: Any, base: str, tipo: str = "dymo", formato: Optional[str] = None) -> Tuple[bytes, str]:
    return DymoService.archivo_activo(*_datos_etiqueta(codigo, base), formato, tipo)


def zip_etiquetas(codigos: List[Any], base: str, tipo: str = "dymo") -> bytes:
    """ZIP con un `.dymo`/`.label` por activo (los códigos que no existen se omiten)."""
    import io
    import zipfile
    buf = io.BytesIO()
    hubo = False
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for cod in codigos:
            try:
                datos, nombre = archivo_etiqueta(cod, base, tipo)
            except (ActivoNoEncontrado, ValueError):
                log.warning("zip_etiquetas: %r omitido (no existe)", cod)
                continue
            z.writestr(nombre, datos)
            hubo = True
    if not hubo:
        raise ActivoNoEncontrado("Ninguno de los activos pedidos existe.")
    return buf.getvalue()
