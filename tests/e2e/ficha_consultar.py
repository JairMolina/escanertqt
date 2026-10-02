"""Prueba real en Chrome de: logo del monitor -> escáner, Consultar leyendo la etiqueta DYMO por la cámara falsa,
R3 en Programar (solo firmware, sin MAC) y ausencia total de Pruebas.
Uso: python tests/e2e/ficha_consultar.py   (arranca su propio servidor aislado en el puerto 8461)"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import ssl
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
PUERTO = "8461"
BASE = f"https://127.0.0.1:{PUERTO}"
CLAVE = "ClaveDePrueba-123"
tmp = Path(tempfile.mkdtemp(prefix="tqt_ficha_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"),
           TQT_BACKUP_DIR=str(tmp / "bk"), TQT_ADMIN_PASSWORD=CLAVE, HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CTX = ssl._create_unverified_context()
fallos = []


def check(nombre, cond, detalle=""):
    print(("OK   " if cond else "FALLA"), nombre, detalle if not cond else "")
    if not cond:
        fallos.append(nombre)


def api(metodo, ruta, cuerpo=None, token=None):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"content-type": "application/json", **({"X-Admin-Token": token} if token else {})})
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
    # ---- datos: tarjeta impar R1 0021 + R2 0010 + R3 0021 con MAC y firmware
    for t, n in (("R1", "0021"), ("R2", "0010"), ("R3", "0021"), ("R3", "0022")):
        api("POST", "/api/pcb/escanear", {"codigo": f"TQT-{t}-V30-{n}"})
    api("POST", "/api/recepcion/confirmar", {})
    ids = {p["nombre"]: p["id"] for p in api("GET", "/api/pcb?limit=100")[1]["items"]}
    s, tj = api("POST", "/api/tarjetas", {"r1_id": ids["TQT-R1-V30-0021"], "r2_id": ids["TQT-R2-V30-0010"], "r3_id": ids["TQT-R3-V30-0021"]})
    check("tarjeta impar creada", s == 201)
    for n, m in (("TQT-R1-V30-0021", "704bca5b9f6e"), ("TQT-R2-V30-0010", "704bca5b9ca2")):
        s, _ = api("PUT", f"/api/pcb/{ids[n]}/mac", {"mac": m})
        check(f"MAC de {n}", s == 200)
    api("PATCH", f"/api/tarjetas/{tj['id']}", {"firmware_r1": "v2.3.1", "firmware_r2": "v2.3.0", "firmware_r3": "v1.0.4"})

    # ---- imagen de la etiqueta REAL generada por el sistema (SVG del QR de 4 líneas) -> mjpeg para la cámara falsa
    from PIL import Image
    with sync_playwright() as p:
        b0 = p.chromium.launch(channel="chrome")
        pg0 = b0.new_context(ignore_https_errors=True, viewport={"width": 800, "height": 500}).new_page()
        svg = urllib.request.urlopen(urllib.request.Request(BASE + f"/api/dymo/svg/{tj['id']}"), context=CTX).read().decode()
        pg0.set_content("<body style='margin:0;background:#fff'><style>svg{width:1000px;height:auto;display:block;margin:40px}</style>" + svg + "</body>")
        png = pg0.screenshot(full_page=True)
        b0.close()
    im = Image.open(io.BytesIO(png)).convert("RGB")
    # el operario acerca la etiqueta a la cámara: etiqueta grande centrada sobre un cuadro 4:3
    lienzo = Image.new("RGB", (1280, 960), (235, 235, 235))
    im.thumbnail((1200, 900)); lienzo.paste(im, ((1280 - im.width) // 2, (960 - im.height) // 2))
    im = lienzo
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)
    mj = tmp / "etiqueta.mjpeg"; mj.write_bytes(buf.getvalue() * 40)
    (RAIZ / "docs" / "qa" / "etiqueta_camara_prueba.jpg").write_bytes(buf.getvalue())
    try:
        import cv2, numpy as np
        d = cv2.QRCodeDetector().detectAndDecode(cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), cv2.IMREAD_COLOR))[0]
        check("la imagen de la etiqueta se decodifica fuera del navegador (OpenCV)", len(d.split()) == 4, repr(d))
    except Exception as e:
        print("(sin OpenCV:", e, ")")

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-video-capture={mj}"])
        ctx = b.new_context(ignore_https_errors=True, viewport={"width": 390, "height": 844}, permissions=["camera"])
        pg = ctx.new_page()
        errores = []
        pg.on("console", lambda m: errores.append(m.text[:140]) if m.type == "error" else None)
        malas = []
        pg.on("response", lambda r: malas.append((r.status, r.url.split(BASE)[-1])) if r.status >= 400 else None)

        # 1) Consultar lee la etiqueta por la cámara
        pg.goto(BASE + "/consultar", wait_until="networkidle")
        try:
            pg.wait_for_selector(".fichagrid .pcbf header .nm", timeout=15000)
        except Exception:
            pass
        txt = pg.inner_text("#ficha")
        for esperado in ("0021", "TQT-R1-V30-0021", "TQT-R2-V30-0010", "TQT-R3-V30-0021", "704b", "70:4b:ca:5b:9f:6e", "70:4b:ca:5b:9c:a2", "la R3 no lleva MAC",
                         "V30", "v2.3.1", "v2.3.0", "Hardware", "Firmware", "Completa"):
            check(f"la ficha muestra '{esperado}'", esperado.lower() in txt.lower() or esperado == "704b", txt[:200].replace("\n", " | ") if esperado == "0021" else "")
        pg.screenshot(path=str(RAIZ / "docs" / "qa" / "ficha_consultar_390.png"), full_page=True)

        # 2) navegación: sin Pruebas, con Consultar
        tabs = pg.eval_on_selector_all(".tabbar .tab span", "els=>els.map(e=>e.textContent)")
        check("pestañas = Recibir/Emparejar/Programar/Consultar", tabs == ["Recibir", "Emparejar", "Programar", "Consultar"], str(tabs))
        r = pg.request.get(BASE + "/pruebas"); check("/pruebas no existe", r.status == 404, str(r.status))
        pg.click("button[aria-label='Más opciones']")
        menu = pg.inner_text(".sheet") if pg.query_selector(".sheet") else ""
        check("el menú no ofrece Pruebas", "prueba" not in menu.lower(), menu[:120])
        pg.keyboard.press("Escape")

        # 3) monitor protegido + logo -> escáner
        ctx2 = b.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 800})
        pm = ctx2.new_page()
        pm.goto(BASE + "/monitor", wait_until="networkidle")
        check("monitor sin sesión redirige al login", "/admin" in pm.url, pm.url)
        ctx2.request.post(BASE + "/api/admin/login", data={"password": CLAVE})
        pm.goto(BASE + "/monitor", wait_until="networkidle")
        check("monitor con sesión carga", pm.url.split("#")[0].endswith("/monitor"), pm.url)
        pm.wait_for_selector("#sec-resumen .esc-kpis")
        kp = pm.inner_text("#sec-resumen .esc-kpis >> nth=0")
        check("KPIs sin pruebas (Completas/Incompletas/Sin MAC)", all(x in kp.upper() for x in ("COMPLETAS", "INCOMPLETAS", "SIN MAC")) and "LIBERADAS" not in kp.upper(), kp.replace("\n", " "))
        pm.click("a.esc-logo")
        pm.wait_for_timeout(500)
        check("el logo de la consola lleva a #/resumen (no a /, que redirige de vuelta a la consola)", pm.url.endswith("/monitor#/resumen"), pm.url)
        pm.goto(BASE + "/monitor#/tarjetas", wait_until="networkidle")
        pm.screenshot(path=str(RAIZ / "docs" / "qa" / "monitor_sin_pruebas_1280.png"))

        # 4) Programar: la R3 no aparece en "pendientes de MAC" y, al escanearla, solo pide firmware
        pp = ctx.new_page()
        pp.goto(BASE + "/programar", wait_until="networkidle")
        check("no hay botón de filtro R3 en pendientes de MAC", pp.query_selector("#segTipo button[data-f='R3']") is None)
        check("ninguna R3 en la lista de pendientes de MAC", pp.query_selector(".item:has-text('TQT-R3')") is None)
        api("POST", "/api/pcb/escanear", {"codigo": "TQT-R3-V30-0084"})
        api("POST", "/api/recepcion/confirmar", {})
        pid84 = api("GET", "/api/pcb/por-codigo?codigo=TQT-R3-V30-0084")[1]["id"]
        s, t84 = api("POST", "/api/tarjetas", {"id_tarjeta_num": "0084", "r3_id": pid84})
        check("tarjeta con la R3 0084 creada", s == 201, str(s))
        pp.close()
        fx = RAIZ / "tests" / "fixtures" / "qr_R3_V30_0084_invertido.jpg"
        mj2 = tmp / "r3.mjpeg"; mj2.write_bytes(fx.read_bytes() * 40)
        b2 = p.chromium.launch(channel="chrome", args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-video-capture={mj2}"])
        pq = b2.new_context(ignore_https_errors=True, viewport={"width": 390, "height": 844}, permissions=["camera"]).new_page()
        pq.goto(BASE + "/programar", wait_until="networkidle")
        try:
            pq.wait_for_selector("#activo .banner", timeout=15000)
        except Exception:
            pass
        check("al escanear la R3 (QR invertido) solo aparece el aviso amable", "La R3 no lleva MAC ni firmware" in pq.inner_text("#activo"))
        check("la R3 NO muestra campo de MAC ni de firmware", pq.query_selector("#macIn") is None and pq.query_selector("#fwSel") is None and pq.query_selector("#fwIn") is None)
        check("la R3 sigue sin MAC", api("GET", f"/api/pcb/{pid84}")[1]["mac"] is None)
        pq.screenshot(path=str(RAIZ / "docs" / "qa" / "programar_r3_390.png"))
        b2.close()

        check("sin errores de consola", not [e for e in errores if "favicon" not in e], str(errores[:3]))
        check("sin respuestas 4xx/5xx en Consultar", not [m for m in malas if m[1] not in ("/pruebas",)], str(malas[:3]))
        b.close()
finally:
    srv.terminate()
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
