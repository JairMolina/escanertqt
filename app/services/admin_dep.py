"""Dependencias FastAPI para exigir sesión de administrador desde cualquier router.

Import diferido de `admin_requerido` para evitar la importación circular
(app.routers.admin importa app.routers.excel_dymo).
"""
from typing import Any, Dict, Optional

from fastapi import Cookie, Header


def admin_token(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
                tqt_admin: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    """Falla cerrado: sin clave configurada => 503; sin sesión válida => 401."""
    from app.routers.admin import admin_requerido
    return admin_requerido(x_admin_token, tqt_admin)


def admin_si_habilitado(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
                        tqt_admin: Optional[str] = Cookie(None)) -> Optional[Dict[str, Any]]:
    """Crear/activar lote y sincronizar Excel YA NO piden contraseña: la clave de supervisor solo protege la zona de
    administración (/admin y /api/admin/*, donde se borran tarjetas) y el acceso masivo a datos (`admin_token`)."""
    return None
