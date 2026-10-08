"""Modelos Pydantic, constantes de dominio, reglas puras y esquema SQLite para Escaner TQT.

Vocabulario canónico (el mismo de la plantilla Excel):
  * Etapa de prueba : PENDIENTE | OK | FALLA | RETRABAJO | NO APLICA
  * Estado general  : PENDIENTE | EN PROCESO | RETRABAJO | DETENIDO | LIBERADO   (derivado, nunca capturado)
  * Estado PCB      : PENDIENTE | FUNCIONAL | FALLA                               (derivado de 'Prueba PCB')
"""
import re
import unicodedata
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field, field_validator


# ==========================================
# Constantes de dominio
# ==========================================
MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# (clave de columna en SQLite, etiqueta que usa el Excel)
ETAPAS = [
    ("soldadura", "Soldadura"),
    ("programacion", "Programación"),
    ("prueba_pcb", "Prueba PCB"),
    ("integracion", "Integración"),
    ("prueba_final", "Prueba Final"),
]
ETAPA_KEYS = tuple(k for k, _ in ETAPAS)
ETAPA_LABEL = dict(ETAPAS)
ETAPAS_PRUEBA = [label for _, label in ETAPAS]

ESTADOS_PRUEBA = ["PENDIENTE", "OK", "FALLA", "RETRABAJO", "NO APLICA"]
ESTADOS_GENERALES = ["PENDIENTE", "EN PROCESO", "RETRABAJO", "DETENIDO", "LIBERADO"]
ESTADOS_PCB = ["PENDIENTE", "FUNCIONAL", "FALLA"]
VERSION_DEFAULT = "30"
# Catálogos de firmware de la plantilla Excel (Producción!N = Principal/R1, Producción!P = Respaldo/R2)
FIRMWARE_CATALOGO_INICIAL = {"R1": ["2", "3.2", "3.3", "4.0", "4.1", "4.2"], "R2": ["2", "2.1"]}

# Inventario global de PCB (SPEC_v2)
TIPOS_PCB = ("R1", "R2", "R3")
TIPOS_CON_MAC = ("R1", "R2")            # la R3 no lleva MAC (se programa, pero solo tiene firmware)
ESTADOS_CICLO = ("RECIBIDA", "DISPONIBLE", "ASIGNADA", "FALLA", "BAJA")
ORIGENES_PCB = ("QR", "MANUAL")
RANURAS = ("R1", "R2", "R3")

# Límites de la plantilla Excel (fórmulas con rangos fijos)
EXCEL_MAX_TARJETAS = 100


# ==========================================
# Reglas de dominio puras (sin acceso a BD)
# ==========================================
def _sin_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


_ESTADO_ALIAS = {
    "PENDIENTE": "PENDIENTE", "": "PENDIENTE", "SIN PROBAR": "PENDIENTE",
    "OK": "OK", "APROBADO": "OK", "PASO": "OK", "FUNCIONAL": "OK",
    "FALLA": "FALLA", "DEFECTUOSO": "FALLA", "DEFECTUOSA": "FALLA", "ERROR": "FALLA", "NO FUNCIONAL": "FALLA",
    "RETRABAJO": "RETRABAJO", "REPROCESO": "RETRABAJO", "EN_REVISION": "RETRABAJO", "REPARACION": "RETRABAJO",
    "NO APLICA": "NO APLICA", "NO_APLICA": "NO APLICA", "NO-APLICA": "NO APLICA", "N/A": "NO APLICA", "NA": "NO APLICA",
}


def normalizar_estado_prueba(valor: Optional[str], default: Optional[str] = None) -> str:
    """Convierte cualquier estado (incluidos los heredados APROBADO/DEFECTUOSO...) al vocabulario canónico.
    Si no se reconoce: devuelve `default` o lanza ValueError cuando default es None."""
    clave = re.sub(r"\s+", " ", _sin_acentos(str(valor if valor is not None else "")).strip().upper())
    if clave in _ESTADO_ALIAS:
        return _ESTADO_ALIAS[clave]
    if default is not None:
        return default
    raise ValueError(
        f"Estado de prueba inválido: '{valor}'. Valores permitidos: {', '.join(ESTADOS_PRUEBA)}."
    )


def normalizar_etapa(valor: Optional[str]) -> str:
    """Acepta clave ('prueba_pcb'), etiqueta ('Prueba PCB') o variantes sin acento; devuelve la clave."""
    limpio = re.sub(r"[\s\-]+", "_", _sin_acentos(str(valor or "")).strip().lower())
    for clave, etiqueta in ETAPAS:
        if limpio in (clave, _sin_acentos(etiqueta).lower().replace(" ", "_")):
            return clave
    raise ValueError(f"Etapa inválida: '{valor}'. Etapas permitidas: {', '.join(ETAPA_KEYS)}.")


def derivar_estado_general(estados: Iterable[Optional[str]]) -> str:
    """Misma lógica que la fórmula de la columna G de la hoja 'Pruebas'."""
    lista = [normalizar_estado_prueba(e, default="PENDIENTE") for e in estados]
    if "FALLA" in lista:
        return "DETENIDO"
    if "RETRABAJO" in lista:
        return "RETRABAJO"
    if lista and all(e in ("OK", "NO APLICA") for e in lista):
        return "LIBERADO"
    if lista and all(e == "PENDIENTE" for e in lista):
        return "PENDIENTE"
    return "EN PROCESO"


def estado_pcb_desde_prueba(prueba_pcb: Optional[str]) -> str:
    """FUNCIONAL si la etapa 'Prueba PCB' está OK, FALLA si falló, PENDIENTE en cualquier otro caso."""
    e = normalizar_estado_prueba(prueba_pcb, default="PENDIENTE")
    return {"OK": "FUNCIONAL", "FALLA": "FALLA"}.get(e, "PENDIENTE")


# --- MAC ---------------------------------------------------------------------
MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
MAC_RAW_REGEX = re.compile(r"^[0-9A-Fa-f]{12}$")
# MAC dentro de un texto más largo: AA:BB.., AA-BB.., AABB.CCDD.EEFF o 12 hex seguidos.
# Las guardas impiden aceptar un tramo de una cadena más larga (p. ej. EUI-64 de 8 octetos).
_MAC_EN_TEXTO = re.compile(
    r"(?<![0-9A-Fa-f])(?<![0-9A-Fa-f]{2}[:\-.])"
    r"(?:[0-9A-Fa-f]{2}[:\-.]?){5}[0-9A-Fa-f]{2}"
    r"(?![0-9A-Fa-f])(?![:\-.][0-9A-Fa-f]{2})"
)
_ETIQUETA_MAC = re.compile(r"\bMAC\b", re.I)  # 'MAC:' contiene letras hexadecimales (A, C)


def normalize_mac(mac: str) -> str:
    """Normaliza cualquier formato MAC válido a XX:XX:XX:XX:XX:XX en mayúsculas."""
    cleaned = mac.strip().upper()
    if MAC_REGEX.match(cleaned):
        return cleaned.replace("-", ":")
    if MAC_RAW_REGEX.match(cleaned):
        return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))
    return cleaned


def is_valid_mac(mac: str) -> bool:
    """Verifica si el string (completo) tiene formato MAC válido."""
    cleaned = mac.strip()
    return bool(MAC_REGEX.match(cleaned) or MAC_RAW_REGEX.match(cleaned))


def extract_mac(texto: Optional[str]) -> Optional[str]:
    """Extrae y normaliza una MAC aunque venga con prefijo/sufijo de texto.
    Rechaza 00:00:00:00:00:00 y FF:FF:FF:FF:FF:FF."""
    m = _MAC_EN_TEXTO.search(_ETIQUETA_MAC.sub(" ", texto or ""))
    if not m:
        return None
    hexa = re.sub(r"[^0-9A-Fa-f]", "", m.group(0)).upper()
    if hexa in ("0" * 12, "F" * 12):
        return None
    return ":".join(hexa[i:i + 2] for i in range(0, 12, 2))


# --- Nombre de tarjeta ------------------------------------------------------
# v1.3.46: también 'PCB_TQT_R3_V2_0_TIMER_0073' (versión con decimal "2_0" = V20 y palabras entre versión y número)
_TARJETA_REGEX = re.compile(r"TQT[\s_\-]*R([123])[\s_\-]*V(\d{1,3}(?:[._]\d(?=[\s_\-]))?)(?:[\s_\-]+[A-Za-z][A-Za-z0-9]*)*[\s_\-]+(\d{1,4})(?!\d)",
                            re.I | re.A)
_SOLO_NUMERO = re.compile(r"^\d{1,4}$", re.A)


def parse_tarjeta_code(texto: Optional[str], tipo_esperado: Optional[str] = None,
                       version_ref: str = VERSION_DEFAULT) -> Optional[Dict[str, str]]:
    """Interpreta 'TQT-R1-V30-0011' (tolera espacios, guiones bajos y minúsculas).
    Para respaldo (tipo_esperado='R2') acepta además solo el número asignado ('11').
    Devuelve {tipo, version, numero, nombre} canónicos o None si no es una tarjeta TQT."""
    raw = (texto or "").strip()
    m = _TARJETA_REGEX.search(raw)
    if m:
        tipo, version, numero = f"R{m.group(1)}", re.sub(r"\D", "", m.group(2)), m.group(3)
    elif tipo_esperado == "R2" and _SOLO_NUMERO.match(raw):
        tipo, version, numero = "R2", version_ref, raw
    else:
        return None
    numero = numero.zfill(4)
    return {"tipo": tipo, "version": version, "numero": numero, "nombre": f"TQT-{tipo}-V{version}-{numero}"}


# ==========================================
# Esquema SQL (SQLite WAL)
#   SCHEMA_LEGACY : esquema v0/v1 (par R1+R2 con MAC obligatoria). Solo se ejecuta sobre bases
#                   ya existentes para poder migrarlas a v2 (ver db._migrar_v2).
#   SCHEMA        : esquema v2 (inventario global de PCB + tarjetas con ranuras R1/R2/R3).
# ==========================================
SCHEMA_LEGACY = """
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 10000;
PRAGMA foreign_keys = ON;

-- 1. Lotes mensuales
CREATE TABLE IF NOT EXISTS lotes_mensuales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_lote TEXT NOT NULL UNIQUE,       -- ej. "2026-09"
    mes INTEGER NOT NULL,                   -- 1 - 12
    anio INTEGER NOT NULL,                  -- ej. 2026
    ruta_excel TEXT,                        -- ruta al Excel mensual
    activo INTEGER NOT NULL DEFAULT 0,      -- 1 = activo, 0 = inactivo
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tarjetas de producción (par R1 + R2)
CREATE TABLE IF NOT EXISTS tarjetas_produccion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    id_tarjeta_num TEXT NOT NULL,           -- ej. '0011'
    nombre_r1 TEXT NOT NULL,                -- ej. 'TQT-R1-V30-0011'
    mac_r1 TEXT NOT NULL,                   -- ej. 'AA:BB:CC:11:22:33' ('' si aún no se conoce)
    firmware_r1 TEXT,
    nombre_r2 TEXT NOT NULL,                -- ej. 'TQT-R2-V30-0011'
    mac_r2 TEXT NOT NULL,
    firmware_r2 TEXT,
    semana_produccion INTEGER,              -- ej. 38
    fecha_proyectada TEXT,                  -- 'YYYY-MM-DD'
    fecha_real TEXT,                        -- 'YYYY-MM-DD' (entrega real; NO es la fecha de escaneo)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_lote_tarjeta UNIQUE (lote_id, id_tarjeta_num)
);

CREATE INDEX IF NOT EXISTS idx_tarjetas_lote ON tarjetas_produccion(lote_id);
CREATE INDEX IF NOT EXISTS idx_tarjetas_mac_r1 ON tarjetas_produccion(mac_r1);
CREATE INDEX IF NOT EXISTS idx_tarjetas_mac_r2 ON tarjetas_produccion(mac_r2);
CREATE INDEX IF NOT EXISTS idx_tarjetas_num ON tarjetas_produccion(id_tarjeta_num);

-- 3. Catálogo de PCB individuales
CREATE TABLE IF NOT EXISTS catalogo_pcb (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    tipo_pcb TEXT NOT NULL CHECK(tipo_pcb IN ('R1', 'R2')),
    nombre_pcb TEXT NOT NULL,
    mac_address TEXT,
    estado_pcb TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK(estado_pcb IN ('FUNCIONAL', 'DEFECTUOSA', 'EN_REVISION', 'PENDIENTE', 'FALLA')),
    asignada_a_id INTEGER REFERENCES tarjetas_produccion(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pcb_lote ON catalogo_pcb(lote_id);
CREATE INDEX IF NOT EXISTS idx_pcb_mac ON catalogo_pcb(mac_address);
CREATE INDEX IF NOT EXISTS idx_pcb_nombre ON catalogo_pcb(nombre_pcb);

-- 4. Pruebas de calidad (una fila por tarjeta, una columna por etapa)
CREATE TABLE IF NOT EXISTS pruebas_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarjeta_id INTEGER NOT NULL UNIQUE REFERENCES tarjetas_produccion(id) ON DELETE CASCADE,
    soldadura TEXT NOT NULL DEFAULT 'PENDIENTE',
    programacion TEXT NOT NULL DEFAULT 'PENDIENTE',
    prueba_pcb TEXT NOT NULL DEFAULT 'PENDIENTE',
    integracion TEXT NOT NULL DEFAULT 'PENDIENTE',
    prueba_final TEXT NOT NULL DEFAULT 'PENDIENTE',
    estado_general TEXT NOT NULL DEFAULT 'PENDIENTE',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pruebas_tarjeta ON pruebas_historial(tarjeta_id);

-- Bitácora de escaneos, emparejamientos y cambios de pruebas (auditoría)
CREATE TABLE IF NOT EXISTS escaneos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id   INTEGER REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    evento    TEXT NOT NULL,
    paso      INTEGER,
    valor     TEXT,
    detalle   TEXT,
    operador  TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_escaneos_lote ON escaneos(lote_id, id DESC);
"""



def ddl_tarjetas(nombre: str = "tarjetas_produccion") -> str:
    """DDL de la tabla de tarjetas v2 (también se usa con otro nombre al reconstruir la v1)."""
    return f"""
CREATE TABLE {nombre} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    id_tarjeta_num TEXT NOT NULL,                 -- ej. '0011' (por defecto = serie de su R1)
    pcb_r1_id INTEGER REFERENCES pcb_inventario(id) ON DELETE SET NULL,
    pcb_r2_id INTEGER REFERENCES pcb_inventario(id) ON DELETE SET NULL,
    pcb_r3_id INTEGER REFERENCES pcb_inventario(id) ON DELETE SET NULL,
    firmware_r1 TEXT,                             -- heredado: hoy el firmware vive en cada PCB (pcb_inventario.firmware)
    firmware_r2 TEXT,
    semana_produccion INTEGER,
    fecha_proyectada TEXT,
    fecha_real TEXT,                              -- entrega real; NO es la fecha de escaneo
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_lote_tarjeta UNIQUE (lote_id, id_tarjeta_num)
)"""


DDL_PCB_INVENTARIO = """
CREATE TABLE IF NOT EXISTS pcb_inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('R1','R2','R3')),
    version TEXT NOT NULL,                        -- '30' (editable)
    serie TEXT NOT NULL,                          -- '0084'
    nombre TEXT NOT NULL,                         -- 'TQT-R3-V30-0084' (derivado de tipo+version+serie)
    mac TEXT,                                     -- solo R1/R2, 'AA:BB:CC:DD:EE:FF'
    firmware TEXT,                                -- versión de firmware con la que se programó (solo R1/R2)
    estado_ciclo TEXT NOT NULL DEFAULT 'RECIBIDA'
        CHECK (estado_ciclo IN ('RECIBIDA','DISPONIBLE','ASIGNADA','FALLA','BAJA')),
    estado_pcb TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado_pcb IN ('PENDIENTE','FUNCIONAL','FALLA')),
    origen TEXT NOT NULL DEFAULT 'QR' CHECK (origen IN ('QR','MANUAL')),
    operador TEXT,
    sesion TEXT,                                  -- marca anónima del equipo que la recibió (borrador propio)
    nota TEXT,
    recibida_en TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    confirmada_en TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (tipo, version, serie)
)"""

SCHEMA = f"""
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 10000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lotes_mensuales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_lote TEXT NOT NULL UNIQUE,       -- ej. "2026-09"
    mes INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    ruta_excel TEXT,
    activo INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_lote TEXT NOT NULL DEFAULT 'mes',  -- 'mes' | 'semana' | 'dia' (v1.3.44)
    fecha_inicio TEXT                       -- 'YYYY-MM-DD' (mes: día 1; semana: lunes)
);

{DDL_PCB_INVENTARIO};
CREATE TABLE IF NOT EXISTS firmware_catalogo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rol TEXT NOT NULL CHECK (rol IN ('R1','R2','R3')),   -- R1 = Principal, R2 = Respaldo (como el Excel), R3 = firmware de la R3
    version TEXT NOT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    UNIQUE (rol, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pcbinv_mac ON pcb_inventario(mac) WHERE mac IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pcbinv_ciclo ON pcb_inventario(estado_ciclo, tipo);
CREATE INDEX IF NOT EXISTS idx_pcbinv_serie ON pcb_inventario(serie);

{ddl_tarjetas().replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)};
CREATE UNIQUE INDEX IF NOT EXISTS ux_tarjetas_pcb_r1 ON tarjetas_produccion(pcb_r1_id) WHERE pcb_r1_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_tarjetas_pcb_r2 ON tarjetas_produccion(pcb_r2_id) WHERE pcb_r2_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_tarjetas_pcb_r3 ON tarjetas_produccion(pcb_r3_id) WHERE pcb_r3_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tarjetas_lote ON tarjetas_produccion(lote_id);
CREATE INDEX IF NOT EXISTS idx_tarjetas_num ON tarjetas_produccion(id_tarjeta_num);

CREATE TABLE IF NOT EXISTS pruebas_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarjeta_id INTEGER NOT NULL UNIQUE REFERENCES tarjetas_produccion(id) ON DELETE CASCADE,
    soldadura TEXT NOT NULL DEFAULT 'PENDIENTE',
    programacion TEXT NOT NULL DEFAULT 'PENDIENTE',
    prueba_pcb TEXT NOT NULL DEFAULT 'PENDIENTE',
    integracion TEXT NOT NULL DEFAULT 'PENDIENTE',
    prueba_final TEXT NOT NULL DEFAULT 'PENDIENTE',
    estado_general TEXT NOT NULL DEFAULT 'PENDIENTE',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pruebas_tarjeta ON pruebas_historial(tarjeta_id);

-- Bitácora de altas, ediciones, fallas, reemplazos, MAC, emparejamientos y pruebas (auditoría)
CREATE TABLE IF NOT EXISTS escaneos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id   INTEGER REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    evento    TEXT NOT NULL,
    paso      INTEGER,
    valor     TEXT,
    detalle   TEXT,
    operador  TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_escaneos_lote ON escaneos(lote_id, id DESC);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


# ==========================================
# Modelos Pydantic para Lotes
# ==========================================
class LoteBase(BaseModel):
    codigo_lote: str = Field(..., min_length=1, max_length=40, description="Identificador único del lote, ej. '2026-09'")
    mes: int = Field(..., ge=1, le=12, description="Mes del lote (1 a 12)")
    anio: int = Field(..., ge=2020, le=2100, description="Año del lote, ej. 2026")
    ruta_excel: Optional[str] = Field(None, max_length=500, description="Ruta al archivo Excel asociado")


class LoteCreate(BaseModel):
    """v1.3.44: lote de mes (mes+anio), semana o día (fecha_inicio). Sin `codigo_lote` el servidor lo genera
    (2026-09, 2026-S40, 2026-09-15)."""
    tipo_lote: str = Field("mes", pattern="^(mes|semana|dia)$", description="mes | semana | dia")
    fecha_inicio: Optional[str] = Field(None, max_length=10, description="YYYY-MM-DD (semana: cualquier día de ella; se usa su lunes)")
    codigo_lote: Optional[str] = Field(None, min_length=1, max_length=40, description="Identificador único; por defecto se genera")
    mes: Optional[int] = Field(None, ge=1, le=12, description="Mes del lote (1 a 12) si es de tipo mes")
    anio: Optional[int] = Field(None, ge=2020, le=2100, description="Año del lote si es de tipo mes")
    ruta_excel: Optional[str] = Field(None, max_length=500, description="Ruta al archivo Excel asociado")
    activo: bool = Field(True, description="Indica si debe marcarse como activo de inmediato")
    crear_excel: bool = Field(True, description="Crea Control_Produccion_TQT_[Mes]_[Año].xlsx desde la plantilla")


class LoteResponse(LoteBase):
    id: int
    activo: bool
    created_at: str

    model_config = {"from_attributes": True}


# ==========================================
# Modelos Pydantic del inventario de PCB (SPEC_v2 §3)
# ==========================================
class EscanearPCB(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=300, description="Contenido del QR, p. ej. TQT-R3-V30-0084")
    operador: Optional[str] = Field(None, max_length=60)
    tipo_forzado: Optional[str] = Field(None, max_length=2, description="R1|R2|R3: solo para códigos que traen únicamente el número")
    version: Optional[str] = Field(None, max_length=5, description="Versión para códigos sin versión (por defecto la versión por defecto)")


class ConfirmarRecepcion(BaseModel):
    ids: Optional[List[int]] = Field(None, max_length=2000, description="Vacío = todo el borrador (RECIBIDA)")
    nota: Optional[str] = Field(None, max_length=200)
    operador: Optional[str] = Field(None, max_length=60)


class PCBManual(BaseModel):
    tipo: str = Field(..., max_length=2)
    version: Optional[str] = Field(None, max_length=5)
    serie: Optional[str] = Field(None, max_length=6, description="Vacío = siguiente serie libre del tipo")
    cantidad: int = Field(1, ge=1, le=200)
    operador: Optional[str] = Field(None, max_length=60)


class PCBEditar(BaseModel):
    tipo: Optional[str] = Field(None, max_length=2)
    version: Optional[str] = Field(None, max_length=5)
    serie: Optional[str] = Field(None, max_length=6)
    liberar: bool = False  # cambiar el tipo de una placa montada: primero se saca de su tarjeta
    operador: Optional[str] = Field(None, max_length=60)


class VersionMasiva(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=2000)
    version: str = Field(..., max_length=5)
    operador: Optional[str] = Field(None, max_length=60)


class AjustesUpdate(BaseModel):
    version_defecto: str = Field(..., max_length=5)


class ProgramacionUpdate(BaseModel):
    """Lo que entrega la programación de una R1/R2: su MAC y (opcional) la versión de firmware grabada."""
    mac: str = Field(..., min_length=1, max_length=60, description="Cualquier formato")
    firmware: Optional[str] = Field(None, max_length=40, description="Versión de firmware con la que se programó (ej. 4.1)")
    operador: Optional[str] = Field(None, max_length=60)


class FirmwareCompilarRequest(BaseModel):
    """Compilar el firmware ESP32 de una R1/R2 para flashearla por USB desde el navegador (no toca la BD)."""
    tipo: str = Field(..., min_length=2, max_length=2, description="R1 o R2 (el firmware de la R3 no se compila aquí)")
    numero: Optional[str] = Field(None, max_length=10, description="Número de la tarjeta; obligatorio para R2 (se graba en el nombre BLE)")


class ProgramacionLoteItem(BaseModel):
    """Una placa por `pcb_id` o por `nombre` (TQT-R1-V30-0021, tolera espacios/minúsculas) con su MAC y firmware."""
    pcb_id: Optional[int] = Field(None, ge=1, le=2**31)
    nombre: Optional[str] = Field(None, max_length=60)
    mac: str = Field(..., min_length=1, max_length=60)
    firmware: Optional[str] = Field(None, max_length=40)


class ProgramacionLote(BaseModel):
    items: List[ProgramacionLoteItem] = Field(..., min_length=1, max_length=500)
    simular: bool = Field(False, description="True: valida todo y responde el resultado por fila SIN guardar nada")
    operador: Optional[str] = Field(None, max_length=60)


class FirmwareUpdate(BaseModel):
    firmware: Optional[str] = Field(None, max_length=40, description="null o cadena vacía borra el firmware")
    operador: Optional[str] = Field(None, max_length=60)


class FirmwareCatalogoIn(BaseModel):
    rol: str = Field(..., max_length=2, description="R1 (Principal), R2 (Respaldo) o R3")
    version: str = Field(..., min_length=1, max_length=40)


class MACUpdate(BaseModel):
    mac: Optional[str] = Field(None, max_length=60, description="Cualquier formato; null borra la MAC")
    operador: Optional[str] = Field(None, max_length=60)


class FallaPCB(BaseModel):
    motivo: Optional[str] = Field(None, max_length=200)
    reemplazo_id: Optional[int] = None
    conservar_pruebas: bool = False
    operador: Optional[str] = Field(None, max_length=60)


class EmparejarAuto(BaseModel):
    lote_id: Optional[int] = None
    series: Optional[List[str]] = Field(None, max_length=500)
    r3: str = Field("manual", pattern="^(manual|auto)$")  # manual (por defecto): la R3 se asigna a mano; auto: par e impar por número
    operador: Optional[str] = Field(None, max_length=60)


class DisolverMasivo(BaseModel):
    ids: Optional[List[int]] = Field(None, max_length=2000)  # tarjetas elegidas
    todas: bool = False  # o todas las del lote (lote_id, por defecto el activo)
    lote_id: Optional[int] = None
    forzar: bool = False  # incluir las que ya tienen pruebas registradas
    operador: Optional[str] = Field(None, max_length=60)


class TarjetaNueva(BaseModel):
    lote_id: Optional[int] = None
    id_tarjeta_num: Optional[str] = Field(None, max_length=6)
    r1_id: Optional[int] = None
    r2_id: Optional[int] = None
    r3_id: Optional[int] = None
    operador: Optional[str] = Field(None, max_length=60)


class TarjetaDatos(BaseModel):
    """Datos de captura de una tarjeta que el Excel guarda a mano (Producción D, G, H, I, J). Solo cambia lo que se envía."""
    firmware_r1: Optional[str] = Field(None, max_length=40)
    firmware_r2: Optional[str] = Field(None, max_length=40)
    semana_produccion: Optional[int] = Field(None, ge=1, le=53)
    fecha_proyectada: Optional[str] = Field(None, max_length=10, description="YYYY-MM-DD; cadena vacía la borra")
    fecha_real: Optional[str] = Field(None, max_length=10, description="Entrega real, YYYY-MM-DD; cadena vacía la borra")
    fecha_llegada: Optional[str] = Field(None, max_length=10, description="Llegada de las placas, YYYY-MM-DD; cadena vacía la borra")
    fecha_finalizado: Optional[str] = Field(None, max_length=10, description="Tarjeta completa, YYYY-MM-DD; cadena vacía la borra")
    gabinete: Optional[str] = Field(None, max_length=12, description="Quintalock o Translock; cadena vacía la borra")
    operador: Optional[str] = Field(None, max_length=60)


class AsignarPCB(BaseModel):
    ranura: str = Field(..., max_length=2)
    pcb_id: Optional[int] = None
    marcar_falla: bool = False
    conservar_pruebas: bool = False
    operador: Optional[str] = Field(None, max_length=60)


# ==========================================
# Modelos Pydantic para Pruebas
# ==========================================
class PruebasHistorialResponse(BaseModel):
    id: int
    tarjeta_id: int
    soldadura: str
    programacion: str
    prueba_pcb: str
    integracion: str
    prueba_final: str
    estado_general: str
    updated_at: str

    model_config = {"from_attributes": True}


class PruebaUpdate(BaseModel):
    etapa: str = Field(..., min_length=1, max_length=30, description="soldadura|programacion|prueba_pcb|integracion|prueba_final")
    estado: str = Field(..., min_length=1, max_length=20, description="OK|FALLA|RETRABAJO|NO APLICA|PENDIENTE")
    operador: Optional[str] = Field(None, max_length=60)


class PruebaLoteUpdate(BaseModel):
    lote_id: Optional[int] = None
    ids: List[str] = Field(..., min_length=1, max_length=500, description="Números de tarjeta (id_tarjeta_num)")
    etapa: str = Field(..., min_length=1, max_length=30)
    estado: str = Field(..., min_length=1, max_length=20)
    operador: Optional[str] = Field(None, max_length=60)




# ==========================================
# Estadísticas y Monitor
# ==========================================
class StatsResponse(BaseModel):
    lote_id: Optional[int]
    codigo_lote: Optional[str]
    total_tarjetas: int
    funcionales: int      # LIBERADO
    defectuosas: int      # DETENIDO
    en_revision: int      # RETRABAJO
    pendientes: int       # PENDIENTE
    en_proceso: int = 0   # EN PROCESO
    porcentaje_aprobacion: float
    total_r1_escaneados: int
    total_r2_escaneados: int
    total_r3_escaneados: int = 0
    incompletas: int = 0                       # tarjetas sin R1 o sin R2
    inventario: Dict[str, int] = {}            # PCB DISPONIBLES por tipo (globales, no del lote)
