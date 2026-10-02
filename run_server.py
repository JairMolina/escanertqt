"""Punto de entrada único: HTTPS local (uvicorn) + certificado autofirmado + URLs para los celulares.

Funciona igual en Windows y en Docker. La IP que se imprime y la que lleva el certificado (SAN) es la del HOST:
`TQT_HOST_IP` (obligatoria dentro de un contenedor, donde la red interna no es la de la WiFi de planta).
Toda la salida es ASCII puro: no depende de la codificación de la consola (nada de sys.stdout.reconfigure).
"""
import os
from pathlib import Path

import uvicorn

from app.config import settings
from app.ssl_cert import ensure_ssl_certificates


def _p(texto: str = "") -> None:
    """print() que nunca falla por la codificación de la consola."""
    try:
        print(texto, flush=True)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"), flush=True)


def en_contenedor() -> bool:
    return Path("/.dockerenv").exists() or os.getenv("TQT_EN_CONTENEDOR") == "1"


def qr_ascii(url: str) -> str:
    """QR en ASCII puro pensado para terminal oscura: los módulos oscuros son espacios y el fondo claro es '##'."""
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    return "\n".join("".join("  " if modulo else "##" for modulo in fila) for fila in qr.get_matrix())


def urls() -> dict:
    base = settings.https_url
    return {
        "Operador (celular)": f"{base}/",
        "Emparejar": f"{base}/emparejar",
        "Programar (MAC)": f"{base}/programar",
        "Pruebas": f"{base}/pruebas",
        "Monitor (PC)": f"{base}/monitor",
        "Etiquetas DYMO": f"{base}/dymo",
        "Certificado (celulares)": f"{base}/cert",
        "API (Swagger)": f"{base}/docs",
    }


def avisos() -> list:
    lista = []
    if en_contenedor() and not os.getenv("TQT_HOST_IP"):
        lista.append("TQT_HOST_IP no esta definida: dentro del contenedor la IP detectada NO es la de la red WiFi "
                     f"({settings.LOCAL_IP}). Los celulares no podran usar las URLs de arriba. Define TQT_HOST_IP con la IP de la PC.")
    if not settings.admin_password:
        lista.append("TQT_ADMIN_PASSWORD no esta definida: el area de administracion queda DESHABILITADA.")
    return lista


def print_banner(cert_file: Path) -> None:
    linea, sep = "=" * 70, "-" * 70
    _p("\n" + linea)
    _p("   ESCANER TQT - Control de produccion TQT Mobile")
    _p(linea)
    _p(f" * IP del host        : {settings.LOCAL_IP}" + ("  (TQT_HOST_IP)" if os.getenv("TQT_HOST_IP") else ""))
    _p(f" * Puerto HTTPS       : {settings.HTTPS_PORT}")
    _p(f" * Base de datos      : {settings.DB_PATH} (SQLite, modo WAL)")
    _p(f" * Certificado SSL    : {cert_file.name} (SAN: {settings.LOCAL_IP}, 127.0.0.1, localhost)")
    _p(f" * Respaldos          : {settings.BACKUP_DIR}")
    _p(sep)
    for nombre, url in urls().items():
        _p(f" {nombre:<24} -> {url}")
    _p(sep)
    _p(" Abre la URL del operador en el celular (misma WiFi):")
    try:
        _p(qr_ascii(settings.https_url))
    except Exception as e:  # noqa: BLE001 - el QR es un extra; jamas debe impedir el arranque
        _p(f"  [QR no disponible: {e}]")
    _p(sep)
    _p(" Primera vez en el celular: acepta el aviso del certificado, o instala el certificado desde /cert.")
    _p(" Concede el permiso de camara cuando el navegador lo pida.")
    for aviso in avisos():
        _p(f" [AVISO] {aviso}")
    _p(linea + "\n")


def main() -> None:
    cert_path, key_path = ensure_ssl_certificates()
    print_banner(cert_path)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.HTTPS_PORT,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
