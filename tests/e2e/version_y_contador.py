"""Chrome real: la versión (v1.1.4) se lee en móvil, consola y administración, y "Guardadas hoy" suma lo de otros operarios.
Uso: python tests/e2e/version_y_contador.py   (arranca su propio servidor aislado en 8466)"""
import json
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
PUERTO = "8466"
BASE = f"https://127.0.0.1:{PUERTO}"
CLAVE = "ClaveDePrueba-123"
tmp = Path(tempfile.mkdtemp(prefix="tqt_ver_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"),
           TQT_BACKUP_DIR=str(tmp / "bk"), TQT_ADMIN_PASSWORD=CLAVE, HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CTX = ssl._create_unverified_context()
fallos = []


def check(nombre, cond, detalle=""):
    print(("OK   " if cond else "FALLA"), nombre, ("" if cond else detalle))
    if not cond:
        fallos.append(nombre)


def api(metodo, ruta, cuerpo=None):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
            b = r.read()
            return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        return e.code, None


try:
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/config", context=CTX, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    for n in ("0001", "0002", "0003"):
        api("POST", "/api/pcb/escanear", {"codigo": f"TQT-R1-V30-{n}"})
    api("POST", "/api/recepcion/confirmar", {})
    ids = {p["nombre"]: p["id"] for p in api("GET", "/api/pcb?limit=50")[1]["items"]}

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        # 1) móvil: pie de página
        m = b.new_context(ignore_https_errors=True, viewport={"width": 390, "height": 844}, permissions=["camera"]).new_page()
        for ruta in ("/consultar", "/programar", "/emparejar"):
            m.goto(BASE + ruta, wait_until="networkidle")
            try:
                m.wait_for_function("document.querySelector('.verpie b') && document.querySelector('.verpie b').textContent.startsWith('v')", timeout=8000)
            except Exception:
                pass
            t = m.inner_text(".verpie") if m.query_selector(".verpie") else ""
            check(f"móvil {ruta}: pie con la versión", "v1.1.4" in t, repr(t))
        m.screenshot(path=str(RAIZ / "docs" / "qa" / "version_movil_390.png"))

        # 2) consola de escritorio: barra lateral + contador de todos los operarios
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        ctx.request.post(BASE + "/api/admin/login", data={"password": CLAVE})
        d = ctx.new_page()
        d.goto(BASE + "/monitor#/macs", wait_until="networkidle")
        try:
            d.wait_for_function("document.querySelector('.esc-ver b') && document.querySelector('.esc-ver b').textContent.startsWith('v')", timeout=8000)
        except Exception:
            pass
        check("consola: la barra lateral muestra la versión", "v1.1.4" in d.inner_text(".esc-ver"), d.inner_text(".esc-ver") if d.query_selector(".esc-ver") else "sin .esc-ver")
        d.wait_for_selector(".macs-counter", timeout=10000)
        d.wait_for_function("document.querySelector('.macs-counter .ok b') !== null", timeout=5000)
        hoy0 = int(d.inner_text(".macs-counter .ok b"))
        # otro operario (otro equipo) guarda dos MAC por la API: el contador de esta pantalla las suma sin recargar
        api("PUT", f"/api/pcb/{ids['TQT-R1-V30-0001']}/programacion", {"mac": "02:11:22:33:44:01", "operador": "Ana"})
        api("PUT", f"/api/pcb/{ids['TQT-R1-V30-0002']}/mac", {"mac": "02:11:22:33:44:02", "operador": "Luis"})
        try:
            d.wait_for_function(f"parseInt(document.querySelector('.macs-counter .ok b').textContent) === {hoy0 + 2}", timeout=8000)
        except Exception:
            pass
        hoy1 = int(d.inner_text(".macs-counter .ok b"))
        check("'Guardadas hoy' suma lo que guardan otros operarios (en vivo)", hoy1 == hoy0 + 2, f"{hoy0} -> {hoy1}")
        d.reload(wait_until="networkidle")
        d.wait_for_selector(".macs-counter .ok b", timeout=10000)
        time.sleep(1)
        check("tras recargar el contador sigue igual (viene del servidor, no del navegador)", int(d.inner_text(".macs-counter .ok b")) == hoy0 + 2, d.inner_text(".macs-counter"))
        d2 = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        d2.request.post(BASE + "/api/admin/login", data={"password": CLAVE})
        e = d2.new_page()
        e.goto(BASE + "/monitor#/macs", wait_until="networkidle")
        e.wait_for_selector(".macs-counter .ok b", timeout=10000)
        time.sleep(1)
        check("otro equipo/navegador ve el mismo contador", int(e.inner_text(".macs-counter .ok b")) == hoy0 + 2, e.inner_text(".macs-counter"))
        d.screenshot(path=str(RAIZ / "docs" / "qa" / "version_consola_1440.png"))

        # 3) administración y DYMO
        a = ctx.new_page()
        a.goto(BASE + "/admin", wait_until="networkidle")
        try:
            a.wait_for_function("[...document.querySelectorAll('[data-version]')].some(e => e.textContent === 'v1.1.4')", timeout=8000)
        except Exception:
            pass
        check("administración muestra la versión", any("v1.1.4" in (x.text_content() or "") for x in a.query_selector_all("[data-version]")))
        y = ctx.new_page()
        y.goto(BASE + "/dymo", wait_until="networkidle")
        try:
            y.wait_for_function("[...document.querySelectorAll('[data-version]')].some(e => e.textContent === 'v1.1.4')", timeout=8000)
        except Exception:
            pass
        check("etiquetas DYMO muestra la versión", any("v1.1.4" in (x.text_content() or "") for x in y.query_selector_all("[data-version]")))
        b.close()
finally:
    srv.terminate()
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
