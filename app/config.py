"""Configuración general del sistema Escaner TQT."""
import os
import socket
from pathlib import Path
from typing import Optional


def get_local_ip() -> str:
    """
    Detecta automáticamente la IP de red local primaria del host.
    Utiliza una conexión UDP dummy para determinar la interfaz enrutada.
    Fallback a hostname y finalmente a 127.0.0.1.
    """
    # Permitir sobreescritura por variable de entorno si se requiere
    env_ip = os.getenv("TQT_HOST_IP")
    if env_ip:
        return env_ip

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No envía paquetes reales, solo resuelve la interfaz hacia afuera
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"


class Settings:
    """Configuración centralizada de la aplicación."""

    # Nombre y versión
    APP_NAME: str = "Escaner TQT"
    APP_VERSION: str = "1.3.21"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Rutas base
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    APP_DIR: Path = BASE_DIR / "app"
    CERTS_DIR: Path = BASE_DIR / "certs"
    CERT_FILE: Path = CERTS_DIR / "cert.pem"
    KEY_FILE: Path = CERTS_DIR / "key.pem"

    # Base de datos SQLite
    DB_NAME: str = "tqt_produccion.db"
    # TQT_DB_PATH permite aislar la BD (tests, ambientes de prueba) sin tocar la de producción
    DB_PATH: Path = Path(os.getenv("TQT_DB_PATH")) if os.getenv("TQT_DB_PATH") else BASE_DIR / DB_NAME

    # Carpeta donde se crean los Excel mensuales (Control_Produccion_TQT_[Mes]_[Año].xlsx)
    EXCEL_DIR: Path = Path(os.getenv("TQT_EXCEL_DIR")) if os.getenv("TQT_EXCEL_DIR") else BASE_DIR / "excel_mensual"
    EXPORTS_DIR: Path = Path(os.getenv("TQT_EXPORTS_DIR")) if os.getenv("TQT_EXPORTS_DIR") else BASE_DIR / "exports"
    # Respaldos automáticos de la BD antes de cualquier acción destructiva del admin (en Docker: /backups)
    BACKUP_DIR: Path = Path(os.getenv("TQT_BACKUP_DIR")) if os.getenv("TQT_BACKUP_DIR") else BASE_DIR / "respaldos"
    SQLITE_TIMEOUT: float = 10.0  # segundos de timeout para busy_timeout

    # Administración: la contraseña SOLO viene de la variable de entorno (nunca hay una por defecto)
    ADMIN_TOKEN_TTL: int = int(os.getenv("TQT_ADMIN_TOKEN_TTL", "1800"))            # 30 min
    ADMIN_MAX_FALLOS: int = int(os.getenv("TQT_ADMIN_MAX_FALLOS", "5"))
    ADMIN_BLOQUEO_SEG: int = int(os.getenv("TQT_ADMIN_BLOQUEO_SEG", "300"))         # 5 min
    ADMIN_RETARDO_MS: int = int(os.getenv("TQT_ADMIN_RETARDO_MS", "400"))           # tiempo mínimo de cada login
    # Cuentas de usuario (inicio de sesión de toda la app)
    SESION_HORAS: int = int(os.getenv("TQT_SESION_HORAS", "12"))
    USER_MIN_CLAVE: int = int(os.getenv("TQT_USER_MIN_CLAVE", "10"))
    ADMIN_PBKDF2_ITER: int = int(os.getenv("TQT_ADMIN_PBKDF2_ITER", "600000"))

    @property
    def admin_password(self) -> str:
        """Contraseña inicial del admin (se lee en cada uso: cambiarla en el entorno y reiniciar la restablece)."""
        return os.getenv("TQT_ADMIN_PASSWORD", "")

    # Directorios estáticos y plantillas
    STATIC_DIR: Path = APP_DIR / "static"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    PLANTILLAS_DIR: Path = BASE_DIR / "plantillas"

    # Red y Servidor
    HOST: str = "0.0.0.0"
    HTTPS_PORT: int = int(os.getenv("HTTPS_PORT", "8443"))
    HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8000"))

    # IP Local detectada dinámicamente
    LOCAL_IP: str = get_local_ip()

    @property
    def https_url(self) -> str:
        return f"https://{self.LOCAL_IP}:{self.HTTPS_PORT}"

    @property
    def monitor_url(self) -> str:
        return f"{self.https_url}/monitor"

    @property
    def ws_url(self) -> str:
        return f"wss://{self.LOCAL_IP}:{self.HTTPS_PORT}/ws"

    def refresh_ip(self) -> str:
        self.LOCAL_IP = get_local_ip()
        return self.LOCAL_IP


settings = Settings()
