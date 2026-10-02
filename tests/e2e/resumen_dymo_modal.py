"""Prueba real en Chrome (v1.2.15): Resumen cuenta "Con MAC"/"Sin MAC" aunque falte la R3 y se actualiza en vivo al guardar una MAC,
y el modal "Imprimir lote en DYMO" permite elegir tarjetas con casillas. NO imprime nada (cancela el modal).
Uso: python tests/e2e/resumen_dymo_modal.py   (arranca su propio servidor aislado en el puerto 8462)"""
import json, os, ssl, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
PUERTO = "8462"; BASE = f"https://127.0.0.1:{PUERTO}"; CLAVE = "ClaveDePrueba-123"
tmp = Path(tempfile.mkdtemp(prefix="tqt_res_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"),
           TQT_BACKUP_DIR=str(tmp / "bk"), TQT_ADMIN_PASSWORD=CLAVE, HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CTX = ssl._create_unverified_context(); fallos = []
IMG = RAIZ / "docs" / "qa"


def check(n, c, d=""):
    print(("OK   " if c else "FALLA"), n, "" if c else d)
    if not c: fallos.append(n)


def api(m, r, b=None):
    req = urllib.request.Request(BASE + r, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=15) as x:
            d = x.read(); return x.status, (json.loads(d) if d else None)
    except urllib.error.HTTPError as e:
        return e.code, None


try:
    for _ in range(60):
        try: urllib.request.urlopen(BASE + "/api/config", context=CTX, timeout=2); break
        except Exception: time.sleep(0.5)
    for n in range(21, 27):
        for t in ("R1", "R2"): api("POST", "/api/pcb/escanear", {"codigo": f"TQT-{t}-V30-{n:04d}"})
    api("POST", "/api/recepcion/confirmar", {})
    ids = {p["nombre"]: p["id"] for p in api("GET", "/api/pcb?limit=100")[1]["items"]}
    for n in range(21, 27):   # tarjetas SIN R3
        s, _ = api("POST", "/api/tarjetas", {"r1_id": ids[f"TQT-R1-V30-{n:04d}"], "r2_id": ids[f"TQT-R2-V30-{n:04d}"]}); assert s == 201
    mac = lambda i: f"704bca5b{i:02x}00"
    for i, n in enumerate((21, 22, 23)):   # 3 tarjetas con MAC en R1 y R2
        api("PUT", f"/api/pcb/{ids[f'TQT-R1-V30-{n:04d}']}/mac", {"mac": mac(i * 2)}); api("PUT", f"/api/pcb/{ids[f'TQT-R2-V30-{n:04d}']}/mac", {"mac": mac(i * 2 + 1)})

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errores = []
        pg.on("console", lambda m: errores.append(m.text[:160]) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errores.append(str(e)[:160]))
        r = ctx.request.post(BASE + "/api/admin/login", data={"password": CLAVE}); check("login admin", r.ok)
        pg.goto(BASE + "/monitor#/resumen", wait_until="networkidle")
        pg.wait_for_selector(".esc-kpi", timeout=15000)
        kp = lambda: {k.query_selector(".l").inner_text().strip().lower(): k.query_selector(".v").inner_text().strip() for k in pg.query_selector_all(".esc-kpi")}
        k = kp(); print("KPIs:", k)
        check("Resumen: Tarjetas = 6", k.get("tarjetas") == "6", str(k)); check("Resumen: Con MAC = 3", k.get("con mac") == "3", str(k))
        check("Resumen: Sin MAC = 3 (no 0)", k.get("sin mac") == "3", str(k)); check("Resumen: Falta placa = 6", k.get("falta placa") == "6", str(k))
        pg.screenshot(path=str(IMG / "resumen_v1215.png"))
        # actualización en vivo: otra "PC/celular" guarda la MAC de la tarjeta 24
        api("PUT", f"/api/pcb/{ids['TQT-R1-V30-0024']}/mac", {"mac": "704bca5bf000"}); api("PUT", f"/api/pcb/{ids['TQT-R2-V30-0024']}/mac", {"mac": "704bca5bf001"})
        for _ in range(20):
            time.sleep(0.5)
            if kp().get("Con MAC") == "4": break
        k = kp(); check("Resumen se actualiza SOLO al guardar una MAC (Con MAC 4, Sin MAC 2)", k.get("con mac") == "4" and k.get("sin mac") == "2", str(k))
        # Tarjetas: filtro "Sin MAC" ya no queda vacío
        pg.goto(BASE + "/monitor#/tarjetas?estado=sin_mac", wait_until="networkidle"); pg.wait_for_timeout(1200)
        filas = pg.query_selector_all("table tbody tr"); check("Tarjetas -> Sin MAC lista 2 filas", len(filas) == 2, str(len(filas)))

        # DYMO: modal de selección
        pg.goto(BASE + "/dymo", wait_until="networkidle"); pg.wait_for_timeout(2500)
        btn = pg.query_selector("#btnPrintAll"); check("botón 'Imprimir lote' habilitado", btn and not btn.is_disabled(), "DYMO no detectada en esta PC")
        if btn and not btn.is_disabled():
            btn.click(); pg.wait_for_selector(".sheet input[type=checkbox]", timeout=5000)
            cajas = pg.query_selector_all(".sheet input[type=checkbox]"); marc = [c.is_checked() for c in cajas]
            check("modal: una casilla por tarjeta (6)", len(cajas) == 6, str(len(cajas))); check("modal: vienen marcadas las 4 con MAC", sum(marc) == 4, str(marc))
            cajas[0].click(); pg.wait_for_timeout(100)
            check("modal: desmarcar una baja el contador a 3", "3 de 6" in pg.inner_text(".sheet"), pg.inner_text(".sheet")[:200])
            pg.fill(".sheet input[type=search]", "25"); pg.wait_for_timeout(200)
            check("modal: el filtro '25' deja 1 tarjeta", len(pg.query_selector_all(".sheet input[type=checkbox]")) == 1)
            pg.fill(".sheet input[type=search]", "")
            pg.screenshot(path=str(IMG / "dymo_modal_v1215.png"))
            pg.click(".sheet .actions .btn:has-text('Cancelar')"); pg.wait_for_timeout(200)
            check("modal: Cancelar cierra sin imprimir", pg.query_selector(".sheet") is None)
        errores = [e for e in errores if "ERR_CONNECTION_REFUSED" not in e]   # el framework DYMO sondea los puertos 41952-41960
        check("sin errores de consola/JS", not errores, str(errores[:4]))
        b.close()
finally:
    srv.terminate()
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} FALLAS: {fallos}")
sys.exit(1 if fallos else 0)
