"""Chrome real: una cámara guardada que ya no existe / no abre NO deja el escáner atascado, y la consola y /admin piden clave donde toca.
Uso: python tests/e2e/camara_atascada.py   (servidor aislado en 8467)"""
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
PUERTO = "8467"
BASE = f"https://127.0.0.1:{PUERTO}"
tmp = Path(tempfile.mkdtemp(prefix="tqt_cam_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"),
           TQT_BACKUP_DIR=str(tmp / "bk"), TQT_ADMIN_PASSWORD="ClaveDePrueba-123", HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
fallos = []


def check(n, c, d=""):
    print(("OK   " if c else "FALLA"), n, "" if c else d)
    if not c:
        fallos.append(n)


try:
    ctx_ssl = ssl._create_unverified_context()
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/config", context=ctx_ssl, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        # 1) cámara guardada inexistente (como cambiar a "trasera/frontal" que la PC no tiene): debe arrancar con la predeterminada
        c = b.new_context(ignore_https_errors=True, viewport={"width": 390, "height": 844}, permissions=["camera"])
        pg = c.new_page()
        pg.goto(BASE + "/", wait_until="domcontentloaded")
        pg.evaluate("localStorage.setItem('tqt.camera', 'id-de-camara-que-no-existe')")
        pg.reload(wait_until="networkidle")
        time.sleep(2.5)
        texto = pg.inner_text("#visorHost")
        check("con una cámara guardada inexistente NO sale 'La cámara está ocupada'", "ocupada" not in texto.lower() and "no se pudo" not in texto.lower(), texto[:120])
        check("el video está corriendo con la cámara predeterminada", pg.evaluate("(document.querySelector('#visorHost video')||{}).videoWidth > 0"))
        check("la elección rota se olvidó", pg.evaluate("localStorage.getItem('tqt.camera')") in ("", None))
        # 2) la consola de PC abre sin contraseña; /admin sí la pide
        d = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}).new_page()
        d.goto(BASE + "/monitor", wait_until="networkidle")
        check("la consola de PC abre sin contraseña", "/monitor" in d.url and "/admin" not in d.url and d.query_selector(".esc-lat") is not None, d.url)
        a = b.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 800}).new_page()
        a.goto(BASE + "/admin", wait_until="networkidle")
        check("/admin muestra el login", a.query_selector("#pass") is not None and a.is_visible("#pass"))
        r = a.request.get(BASE + "/api/admin/resumen")
        check("/api/admin/* sin sesión = 401", r.status == 401, str(r.status))
        b.close()
finally:
    srv.terminate()
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s)")
sys.exit(1 if fallos else 0)
