"""v1.4.10: módulos de la plataforma I+D. Agregar un módulo = agregar una entrada (el portal /inicio se arma solo).

estado: disponible | proximamente | mantenimiento. `url` solo se usa si está disponible.
Acceso (v1.4.11): los administradores entran a todos; las demás cuentas solo a los módulos que tengan asignados
(columna `usuarios.modulos`). Escáner TQT es el único módulo con aplicación por ahora.
"""
from typing import Any, Dict, List, Optional

ESCANER_TQT = "escaner-tqt"

MODULOS: List[Dict[str, Any]] = [
    {"id": ESCANER_TQT, "nombre": "Escáner TQT", "descripcion": "Recepción, emparejado, programación y entrega de tarjetas TQT.",
     "icono": "chip", "url": "/", "estado": "disponible", "acento": "#D9A441"},
    {"id": "speedlocker", "nombre": "SpeedLocker", "descripcion": "Control y seguimiento de equipos SpeedLocker.",
     "icono": "candado", "url": "", "estado": "proximamente", "acento": "#4FB3BF"},
    {"id": "skudo-antijammer", "nombre": "Skudo AntiJammer", "descripcion": "Producción y pruebas de equipos Skudo AntiJammer.",
     "icono": "escudo", "url": "", "estado": "proximamente", "acento": "#8FBF6A"},
    {"id": "tpms", "nombre": "TPMS", "descripcion": "Sensores de presión de llantas: alta, pruebas y seguimiento.",
     "icono": "llanta", "url": "", "estado": "proximamente", "acento": "#E07A5F"},
    {"id": "skudo-sigfox", "nombre": "Skudo Sigfox", "descripcion": "Equipos Skudo con red Sigfox: alta y validación.",
     "icono": "antena", "url": "", "estado": "proximamente", "acento": "#C98BD9"},
    {"id": "caiquen", "nombre": "Caiquen", "descripcion": "Producción y control de equipos Caiquen.",
     "icono": "ave", "url": "", "estado": "proximamente", "acento": "#6C9BD9"},
    {"id": "impresora", "nombre": "Impresora", "descripcion": "Impresión de etiquetas y documentos de producción.",
     "icono": "impresora", "url": "", "estado": "proximamente", "acento": "#B8B8C8"},
]

IDS = tuple(m["id"] for m in MODULOS)


def normalizar_lista(valor: Any) -> List[str]:
    """Texto guardado ('a,b') o lista → ids válidos, sin repetir y en el orden del catálogo. Ids desconocidos: ValueError."""
    if valor is None:
        return []
    partes = valor.split(",") if isinstance(valor, str) else list(valor)
    pedidos = {str(p).strip() for p in partes if str(p).strip()}
    malos = pedidos - set(IDS)
    if malos:
        raise ValueError("Módulo desconocido: " + ", ".join(sorted(malos)))
    return [i for i in IDS if i in pedidos]


def puede(usuario: Optional[Dict[str, Any]], modulo_id: str) -> bool:
    if not usuario:
        return False
    return usuario.get("rol") == "administrador" or modulo_id in (usuario.get("modulos") or [])


def para_portal(usuario: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Catálogo con `permitido` por módulo: None sin sesión (el login decide), True/False con sesión."""
    return [dict(m, permitido=(puede(usuario, m["id"]) if usuario else None)) for m in MODULOS]
