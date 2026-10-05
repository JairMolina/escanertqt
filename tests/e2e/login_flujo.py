"""Prueba real en Chrome (v1.3.16): sin sesión todo lleva a /login; clave mala; entrada; cambio de clave sugerido; salir.
Uso: python tests/e2e/login_flujo.py   (servidor aislado en el puerto 8464)"""
import json, os, ssl, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
PUERTO = "8464"; BASE = f"https://127.0.0.1:{PUERTO}"; EMAIL = "developer@skyguardian.mx"; CLAVE = __import__("os").environ["TQT_USER_SEED_PASSWORD"]
tmp = Path(tempfile.mkdtemp(prefix="tqt_login_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"), TQT_BACKUP_DIR=str(tmp / "bk"),
           HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
fallos = []


def check(n, c, d=""):
    print(("OK   " if c else "FALLA"), n, "" if c else d)
    if not c: fallos.append(n)


try:
    for _ in range(80):
        try: urllib.request.urlopen(BASE + "/api/health", context=ssl._create_unverified_context(), timeout=2); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 800}); pg = ctx.new_page()
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)[:150]))
        for ruta in ("/monitor", "/", "/dymo", "/emparejar"):
            pg.goto(BASE + ruta, wait_until="load")
            check(f"sin sesión {ruta} -> /login", "/login" in pg.url and "next=" in pg.url, pg.url)
        check("API sin sesión: 401", pg.evaluate("fetch('/api/pcb').then(r=>r.status)") == 401)
        # clave incorrecta
        pg.goto(BASE + "/login?next=%2Fmonitor", wait_until="load")
        pg.fill("#email", EMAIL); pg.fill("#pass", "clave-equivocada-1"); pg.click("#entrar"); pg.wait_for_timeout(1200)
        check("clave mala: mensaje y sigue en login", "incorrectos" in pg.inner_text("#msg") and "/login" in pg.url, pg.inner_text("#msg"))
        pg.screenshot(path=str(RAIZ / "docs" / "qa" / "login_error_v1316.png"))
        # entrada buena -> ofrece cambiar la clave inicial
        pg.fill("#pass", CLAVE); pg.click("#entrar"); pg.wait_for_selector("#fClave:not([hidden])", timeout=8000)
        check("clave inicial: ofrece cambiarla", "inicial" in pg.inner_text("#avisoClave").lower())
        pg.screenshot(path=str(RAIZ / "docs" / "qa" / "login_cambiar_v1316.png"))
        pg.click("#luego"); pg.wait_for_url("**/monitor", timeout=8000); pg.wait_for_selector(".esc-kpi", timeout=15000)
        check("'Más tarde' entra a la consola con datos", "/monitor" in pg.url)
        # open redirect: next externo se ignora
        pg.goto(BASE + "/login?next=https%3A%2F%2Fevil.example%2F", wait_until="load"); pg.wait_for_timeout(1000)
        check("con sesión y next externo -> se queda en el sitio", pg.url.startswith(BASE), pg.url)
        # cerrar sesión desde la consola
        pg.goto(BASE + "/monitor", wait_until="load"); pg.click("button[aria-label='Cerrar sesión']"); pg.wait_for_url("**/login**", timeout=8000)
        check("cerrar sesión -> /login", "/login" in pg.url)
        pg.goto(BASE + "/monitor", wait_until="load")
        check("después de salir /monitor vuelve a pedir login", "/login" in pg.url, pg.url)
        check("sin errores JS", not errores, str(errores[:3]))
        b.close()
finally:
    srv.terminate()
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} FALLAS: {fallos}")
sys.exit(1 if fallos else 0)
