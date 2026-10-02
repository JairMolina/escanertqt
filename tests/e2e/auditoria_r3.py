"""Auditoria real en Chrome (v1.2.15): recorre las pantallas con una tarjeta completa, una sin MAC y una R3 suelta, y verifica que ninguna pida MAC para una R3. Puerto 8463.
import json, os, re, ssl, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
RAIZ = Path(__file__).resolve().parents[2]; PUERTO = "8463"; BASE = f"https://127.0.0.1:{PUERTO}"; CLAVE = "ClaveDePrueba-123"
tmp = Path(tempfile.mkdtemp(prefix="tqt_r3_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"), TQT_BACKUP_DIR=str(tmp / "bk"),
           TQT_ADMIN_PASSWORD=CLAVE, HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CTX = ssl._create_unverified_context()
def api(m, r, b=None):
    req = urllib.request.Request(BASE + r, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=15) as x: d = x.read(); return x.status, (json.loads(d) if d else None)
    except urllib.error.HTTPError as e: return e.code, None
hallazgos = []
try:
    for _ in range(60):
        try: urllib.request.urlopen(BASE + "/api/config", context=CTX, timeout=2); break
        except Exception: time.sleep(0.5)
    for n in ("0021", "0022", "0023"):
        for t in ("R1", "R2", "R3"): api("POST", "/api/pcb/escanear", {"codigo": f"TQT-{t}-V30-{n}"})
    api("POST", "/api/pcb/escanear", {"codigo": "TQT-R3-V30-0099"})   # R3 suelta
    api("POST", "/api/recepcion/confirmar", {})
    ids = {p["nombre"]: p["id"] for p in api("GET", "/api/pcb?limit=100")[1]["items"]}
    for n in ("0021", "0022"):   # 0021 completa con MAC; 0022 con R3 pero SIN MAC; 0023 sin tarjeta
        s, tj = api("POST", "/api/tarjetas", {"r1_id": ids[f"TQT-R1-V30-{n}"], "r2_id": ids[f"TQT-R2-V30-{n}"], "r3_id": ids[f"TQT-R3-V30-{n}"]})
    api("PUT", f"/api/pcb/{ids['TQT-R1-V30-0021']}/mac", {"mac": "704bca5b0001"}); api("PUT", f"/api/pcb/{ids['TQT-R2-V30-0021']}/mac", {"mac": "704bca5b0002"})
    s, _ = api("PUT", f"/api/pcb/{ids['TQT-R3-V30-0021']}/mac", {"mac": "704bca5b0003"}); print("API: MAC a una R3 ->", s, "(debe ser 4xx)")
    s, d = api("GET", "/api/pcb?sin_mac=1&limit=100"); print("API sin_mac=1 incluye R3:", any(p["tipo"] == "R3" for p in d["items"]))

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}); ctx.request.post(BASE + "/api/admin/login", data={"password": CLAVE})
        pg = ctx.new_page()
        def volcado(titulo):
            t = pg.evaluate("""()=>{const o=[];document.querySelectorAll('.sheet,aside,[role=dialog],.esc-panel,.esc-det,.esc-detalle,main').forEach(e=>o.push((e.innerText||'').replace(/\s+/g,' ').slice(0,1500)));return o.join(' || ')}""")
            hit = [m.group(0) for m in re.finditer(r".{0,60}R3.{0,100}", t) if re.search(r"mac", m.group(0), re.I)]
            print(f"[{titulo}]", "R3+MAC:", hit[:5])
        pg.goto(BASE + "/monitor#/tarjetas", wait_until="networkidle"); pg.wait_for_timeout(1000)
        for etq in ("Ficha", "Etiqueta"):
            bt = pg.query_selector_all(f"button:has-text('{etq}'), a:has-text('{etq}')")
            if bt:
                bt[1 if len(bt) > 1 else 0].click(); pg.wait_for_timeout(800); volcado("tarjetas > " + etq)
                pg.keyboard.press("Escape"); pg.goto(BASE + "/monitor#/tarjetas", wait_until="networkidle"); pg.wait_for_timeout(600)
        # fila -> panel lateral
        fila = pg.query_selector_all("table tbody tr")
        if fila: fila[1].click(); pg.wait_for_timeout(900); volcado("tarjetas > panel de la fila 0022")
        pg.screenshot(path=str(RAIZ / "docs" / "qa" / "auditoria_r3_tarjetas.png"))
        for ruta in ("/monitor#/macs", "/monitor#/programacion"):
            pg.goto(BASE + ruta, wait_until="networkidle"); pg.wait_for_timeout(1200)
            t = pg.inner_text("body"); print(ruta, "menciona R3-0099/0021..:", [l for l in t.splitlines() if "R3" in l][:6])
        pg.goto(BASE + "/emparejar", wait_until="networkidle"); b.close()
finally:
    srv.terminate()
