"""Diseño de /consultar, firmware en Programar, hoja de lotes del encabezado y rótulos Hardware/Firmware, en Chrome real.
Arranca su propio servidor aislado en el puerto 8462 (primero CON clave de admin y luego SIN ella).
Uso:  TQT_AXE=<ruta a axe.min.js, fuera del repo> TQT_SHOTS=<carpeta de capturas> python tests/e2e/diseno_consultar.py
Las capturas van a TQT_SHOTS (por defecto docs/qa/capturas_consultar)."""
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PUERTO = "8462"
os.environ["TQT_BASE"] = f"https://127.0.0.1:{PUERTO}"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from util import BASE, CAM_JS, RAIZ, Vigia, lanzar  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

CLAVE = "ClaveQA-12345"
SHOTS = Path(os.environ.get("TQT_SHOTS", str(RAIZ / "docs" / "qa" / "capturas_consultar")))
SHOTS.mkdir(parents=True, exist_ok=True)
AXE = os.environ.get("TQT_AXE", "")
CTX = ssl._create_unverified_context()
fallos = []


def check(nombre, cond, detalle=""):
    print(("OK   " if cond else "FALLA"), nombre, ("" if cond else str(detalle)[:300]))
    if not cond:
        fallos.append(nombre)


def api(metodo, ruta, cuerpo=None):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=20) as r:
            b = r.read()
            return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        return e.code, None


class Servidor:
    def __init__(self, clave):
        self.tmp = Path(tempfile.mkdtemp(prefix="tqt_dis_"))
        env = {k: v for k, v in os.environ.items() if k != "TQT_ADMIN_PASSWORD"}
        env.update(TQT_DB_PATH=str(self.tmp / "x.db"), TQT_EXCEL_DIR=str(self.tmp / "xl"), TQT_EXPORTS_DIR=str(self.tmp / "ex"),
                   TQT_BACKUP_DIR=str(self.tmp / "bk"), HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
        if clave:
            env["TQT_ADMIN_PASSWORD"] = clave
        self.p = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                urllib.request.urlopen(BASE + "/api/config", context=CTX, timeout=2)
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("el servidor no arrancó")

    def parar(self):
        self.p.terminate()
        try:
            self.p.wait(10)
        except Exception:
            self.p.kill()


def sembrar():
    """Tarjeta impar R1 0021 + R2 0010 + R3 0021 (con MAC y firmware) y dos placas R1/R2 sin MAC para Programar."""
    for t, n in (("R1", "0021"), ("R2", "0010"), ("R3", "0021"), ("R1", "0030"), ("R2", "0031")):
        api("POST", "/api/pcb/escanear", {"codigo": f"TQT-{t}-V30-{n}"})
    api("POST", "/api/recepcion/confirmar", {})
    ids = {p["nombre"]: p["id"] for p in api("GET", "/api/pcb?limit=100")[1]["items"]}
    s, tj = api("POST", "/api/tarjetas", {"r1_id": ids["TQT-R1-V30-0021"], "r2_id": ids["TQT-R2-V30-0010"], "r3_id": ids["TQT-R3-V30-0021"]})
    check("tarjeta impar creada", s == 201, s)
    s1, r1 = api("PUT", f"/api/pcb/{ids['TQT-R1-V30-0021']}/programacion", {"mac": "704bca5b9f6e", "firmware": "4.1"})
    s2, _ = api("PUT", f"/api/pcb/{ids['TQT-R2-V30-0010']}/programacion", {"mac": "704bca5b9ca2", "firmware": "2.1"})
    check("programación MAC+firmware por API", s1 == 200 and s2 == 200 and r1.get("firmware") == "4.1", (s1, s2))
    return ids, tj


ETIQUETA = "TQT-R1-V30-0021\n70:4b:ca:5b:9f:6e\nTQT-R2-V30-0010\n70:4b:ca:5b:9c:a2"


def sin_scroll_h(pg, nombre):
    w = pg.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    check(f"sin scroll horizontal ({nombre})", w[0] <= w[1], w)


def axe(pg, nombre):
    if not AXE:
        return
    pg.add_script_tag(path=AXE)
    v = pg.evaluate("async () => (await axe.run(document, { resultTypes: ['violations'] })).violations.map(v => v.id + ' x' + v.nodes.length + ' ' + v.nodes.slice(0,2).map(n => n.target.join(' ')).join('|'))")
    check(f"axe 0 violaciones ({nombre})", not v, v)


def nuevo(p, **kw):
    br, ctx = lanzar(p, **kw)
    ctx.add_init_script(CAM_JS)   # nunca la cámara real del equipo
    return br, ctx


def fase_con_clave(p):
    srv = Servidor(CLAVE)
    try:
        ids, tj = sembrar()
        lotes = api("GET", "/api/lotes")[1]
        check("GET /api/lotes trae tarjetas", lotes and "tarjetas" in lotes[0], lotes)
        activo0 = next(l for l in lotes if l["activo"])
        for tema in ("dark", "light"):
            for (w, hh) in ((390, 844), (1280, 800)):
                tag = f"{tema}_{w}"
                br, ctx = nuevo(p, viewport={"width": w, "height": hh}, color_scheme=tema)
                ctx.add_init_script(f"try{{localStorage.setItem('tqt.tema','{tema}')}}catch(e){{}}")
                ctx.add_init_script(CAM_JS)
                pg = ctx.new_page(); v = Vigia(pg)
                pg.goto(BASE + "/consultar", wait_until="networkidle"); pg.wait_for_timeout(500)
                pg.screenshot(path=str(SHOTS / f"consultar_vacio_{tag}.png"))
                axe(pg, f"consultar vacío {tag}")
                visor_h0 = pg.evaluate("document.querySelector('.visor').getBoundingClientRect().height")
                # carga (esqueleto): se retrasa la respuesta para poder verlo
                pg.route("**/api/consulta*", lambda r: (time.sleep(1.2), r.continue_()))
                pg.evaluate("__showQR(%s, false, 380)" % json.dumps(ETIQUETA))
                pg.wait_for_selector(".skel-ficha", timeout=8000)
                pg.screenshot(path=str(SHOTS / f"consultar_cargando_{tag}.png"))
                pg.unroute("**/api/consulta*")
                pg.wait_for_selector(".fichagrid .pcbf .nm", timeout=15000); pg.wait_for_timeout(500)
                txt = pg.inner_text("#ficha")
                for esperado in ("0021", "TQT-R1-V30-0021", "TQT-R2-V30-0010", "TQT-R3-V30-0021", "70:4b:ca:5b:9f:6e", "70:4b:ca:5b:9c:a2",
                                 "Hardware", "V30", "Firmware", "4.1", "2.1", "La R3 no lleva MAC", "Etiqueta DYMO"):
                    check(f"[{tag}] la ficha muestra '{esperado}'", esperado.lower() in txt.lower(), txt[:160].replace("\n", " | "))
                r3 = pg.inner_text(".pcbf[data-t='R3']")
                check(f"[{tag}] la R3 no muestra el rótulo Firmware ni MAC como dato", "Firmware\n" not in r3 and "\nMAC\n" not in r3, r3)
                check(f"[{tag}] la R1 y la R2 muestran Firmware", pg.locator(".pcbf[data-t='R1'] dt:text-is('Firmware'), .pcbf[data-t='R2'] dt:text-is('Firmware')").count() == 2)
                sin_scroll_h(pg, f"ficha {tag}")
                if w == 390:
                    visor_h = pg.evaluate("document.querySelector('.visor').getBoundingClientRect().height")
                    check(f"[{tag}] el visor se reduce a franja con resultado", visor_h <= 64 and visor_h0 > 150, (visor_h0, visor_h))
                    num = pg.evaluate("(() => { const b = document.querySelector('.fichahead .num').getBoundingClientRect(); return [b.top, b.bottom, b.height]; })()")
                    check(f"[{tag}] el número de tarjeta es el héroe y se ve sin scroll", num[1] < 844 and num[2] >= 60, num)
                    mac1 = pg.evaluate("document.querySelector('.pcbf[data-t=\"R1\"] .macval').getBoundingClientRect().bottom")
                    check(f"[{tag}] la MAC de la R1 se ve sin scroll en 390x844", mac1 < 844 - 64, mac1)
                    pequenos = pg.evaluate("""[...document.querySelectorAll('#ficha button, #ficha a.btn, #formBuscar button, #formBuscar input')]
                        .filter(e => e.offsetParent).map(e => [e.textContent.trim().slice(0, 20), Math.round(e.getBoundingClientRect().height)]).filter(x => x[1] < 44)""")
                    check(f"[{tag}] objetivos táctiles >= 44 px", not pequenos, pequenos)
                else:
                    cols = pg.evaluate("[...document.querySelectorAll('.fichagrid .pcbf')].map(e => Math.round(e.getBoundingClientRect().left))")
                    check(f"[{tag}] escritorio: 3 columnas", len(set(cols)) == 3, cols)
                    vis = pg.evaluate("(() => { const a = document.querySelector('.visor').getBoundingClientRect(), b = document.querySelector('.pcbf').getBoundingClientRect(); return a.right <= b.left + 1; })()")
                    check(f"[{tag}] escritorio: visor a un lado", vis)
                pg.screenshot(path=str(SHOTS / f"consultar_ficha_{tag}.png"), full_page=(w == 390))
                axe(pg, f"consultar ficha {tag}")
                # Nueva consulta devuelve el visor
                pg.click("text=Nueva consulta"); pg.wait_for_timeout(600)
                if w == 390:
                    check(f"[{tag}] 'Nueva consulta' devuelve el visor", pg.evaluate("document.querySelector('.visor').getBoundingClientRect().height") > 150)
                # error: placa inexistente
                pg.fill("#q", "TQT-R1-V30-9999"); pg.click("#formBuscar button"); pg.wait_for_selector(".banner[data-k='bad']", timeout=8000)
                pg.wait_for_timeout(500); pg.screenshot(path=str(SHOTS / f"consultar_error_{tag}.png"))
                check(f"[{tag}] error 404 con texto claro", "no está registrada" in pg.inner_text("#ficha"), pg.inner_text("#ficha")[:100])
                axe(pg, f"consultar error {tag}")
                check(f"[{tag}] consola/red limpias en Consultar", all("404" in str(x) or "favicon" in str(x) for x in v.consola + v.http) and not v.externas, (v.consola, v.http, v.externas))
                br.close()
        for w in (320, 390, 1280):
            br, ctx = nuevo(p, viewport={"width": w, "height": 800})
            pg = ctx.new_page(); pg.goto(BASE + "/consultar?codigo=TQT-R1-V30-0021", wait_until="networkidle"); pg.wait_for_selector(".pcbf .nm")
            sin_scroll_h(pg, f"consultar ?codigo {w}"); br.close()

        # ---- Programar: MAC + firmware en una llamada, catálogo, último firmware recordado, R3 sin captura
        br, ctx = nuevo(p, viewport={"width": 390, "height": 844})
        ctx.add_init_script(CAM_JS)
        pg = ctx.new_page(); v = Vigia(pg)
        llamadas = []
        pg.on("request", lambda r: llamadas.append((r.method, r.url.split(BASE)[-1])) if "/api/pcb/" in r.url and r.method in ("PUT", "PATCH") else None)
        pg.goto(BASE + "/programar", wait_until="networkidle"); pg.wait_for_timeout(500)
        cat0 = api("GET", "/api/firmware")[1]
        pg.locator("#lista .item").first.click(); pg.wait_for_selector("#fwSel")
        opts = pg.eval_on_selector_all("#fwSel option", "els => els.map(e => e.textContent)")
        check("el selector de firmware trae el catálogo + 'Otra versión…'", "Otra versión…" in opts and all(x in opts for x in cat0["R1"]), opts)
        check("rótulo del firmware de la R1 = Principal", "principal" in pg.inner_text("#activo").lower(), pg.inner_text("#activo")[:200])
        pg.screenshot(path=str(SHOTS / "programar_firmware_390.png"))
        pg.fill("#macIn", "704bca5b9c11")
        pg.select_option("#fwSel", "__otra"); pg.wait_for_selector("#fwIn", state="visible")
        pg.click("button:has-text('Guardar MAC')"); pg.wait_for_timeout(300)
        check("Otra versión vacía no guarda y avisa", "escribe la versión" in pg.inner_text("#activo").lower())
        pg.fill("#fwIn", "9.9-QA"); pg.wait_for_timeout(500)
        pg.click("button:has-text('Guardar MAC')"); pg.wait_for_timeout(1200)
        prog = [x for x in llamadas if x[0] == "PUT"]
        check("se guarda con UNA llamada a /programacion", len(prog) == 1 and prog[0][1].endswith("/programacion"), llamadas)
        st, pcbs = api("GET", "/api/pcb?q=704bca5b9c11")
        check("la MAC y el firmware quedaron en la PCB", st == 200 and pcbs["items"][0]["firmware"] == "9.9-QA", pcbs)
        check("la versión nueva entró al catálogo", "9.9-QA" in api("GET", "/api/firmware")[1]["R1"])
        # siguiente pendiente (R2): rol Respaldo; su último firmware no existe aún => sin preselección
        pg.wait_for_selector("#fwSel")
        check("la siguiente placa (R2) usa el rótulo Respaldo", "respaldo" in pg.inner_text("#activo").lower())
        pg.reload(wait_until="networkidle"); pg.wait_for_timeout(400)
        pg.locator("#lista .item", has_text="R1").first.click() if pg.locator("#lista .item", has_text="TQT-R1").count() else None
        check("no hay R3 ni campo de firmware para R3 en Programar", pg.locator("#segTipo button[data-f='R3']").count() == 0)
        # R3 escaneada: solo aviso amable
        pg.evaluate("__showQR('TQT-R3-V30-0021', false, 380)"); pg.wait_for_timeout(2500)
        act = pg.inner_text("#activo")
        check("al escanear una R3: aviso 'La R3 no lleva MAC'", "La R3 no lleva MAC" in act, act[:200])
        check("la R3 no ofrece MAC ni firmware", pg.locator("#macIn, #fwSel, #fwIn").count() == 0)
        pg.screenshot(path=str(SHOTS / "programar_r3_390.png"))
        axe(pg, "programar R3")
        # firmware recordado por rol: al abrir otra R1 viene preseleccionada 9.9-QA
        api("POST", "/api/pcb/escanear", {"codigo": "TQT-R1-V30-0040"}); api("POST", "/api/recepcion/confirmar", {})
        pg.reload(wait_until="networkidle"); pg.wait_for_timeout(500)
        pg.locator("#lista .item", has_text="TQT-R1-V30-0040").click(); pg.wait_for_selector("#fwSel")
        check("el último firmware de la R1 viene preseleccionado", pg.eval_on_selector("#fwSel", "e => e.value") == "9.9-QA")
        pg.screenshot(path=str(SHOTS / "programar_recordado_390.png"))
        axe(pg, "programar R1")
        sin_scroll_h(pg, "programar 390")
        check("consola limpia en Programar", not [c for c in v.consola if "favicon" not in str(c)] and not v.externas, (v.consola, v.externas))
        br.close()

        # ---- Hoja de lotes con clave de admin
        br, ctx = nuevo(p, viewport={"width": 390, "height": 844})
        pg = ctx.new_page(); v = Vigia(pg)
        pg.goto(BASE + "/consultar", wait_until="networkidle"); pg.wait_for_timeout(400)
        check("el logo lleva a /", pg.get_attribute("a.brand", "href") == "/")
        sub0 = pg.inner_text(".brand-sub")
        check("el sub-título es un botón con el lote activo", pg.locator("button.brand-sub").count() == 1 and "lote" in sub0.lower(), sub0)
        pg.click("button.brand-sub"); pg.wait_for_selector(".sheet .lote"); pg.wait_for_timeout(300)
        hoja = pg.inner_text(".sheet")
        check("la hoja lista lotes con 'Activo' y nº de tarjetas", "activo" in hoja.lower() and "tarjeta" in hoja and "todos los celulares" in hoja, hoja[:300])
        check("el enlace 'Ver en el monitor' apunta a /monitor?lote=id", pg.get_attribute(f".sheet a:has-text('Ver en el monitor')", "href") == f"/monitor?lote={activo0['id']}")
        pg.screenshot(path=str(SHOTS / "lotes_hoja_390.png"))
        axe(pg, "hoja de lotes")
        pg.select_option("#nlMes", "10"); pg.fill("#nlAnio", "2026")
        pg.click("button:has-text('Crear y usar este lote')"); pg.wait_for_selector("#lotePass", timeout=8000)
        check("sin sesión (401) aparece el campo de contraseña del supervisor", "Estas acciones las hace el supervisor" in pg.inner_text(".sheet"))
        pg.fill("#lotePass", "mala"); pg.click("button:has-text('Entrar y continuar')"); pg.wait_for_selector("#lotePassErr:has-text('incorrecta')", timeout=8000)
        pg.screenshot(path=str(SHOTS / "lotes_clave_390.png"))
        axe(pg, "hoja de lotes con clave")
        pg.fill("#lotePass", CLAVE); pg.click("button:has-text('Entrar y continuar')")
        pg.wait_for_function("document.querySelector('.brand-sub') && document.querySelector('.brand-sub').textContent.includes('Octubre')", timeout=15000)
        st = api("GET", "/api/status")[1]["active_lote"]
        check("tras login se reintentó y el lote nuevo quedó activo", st["mes"] == 10 and st["anio"] == 2026, st)
        # reabrir y volver a usar el otro lote (ya hay cookie: sin pedir clave)
        pg.wait_for_timeout(1000)
        pg.click("button.brand-sub"); pg.wait_for_selector(".sheet .lote")
        pg.click(f".sheet .lote:not([data-activo='1']) button:has-text('Usar este lote')")
        pg.wait_for_function("document.querySelector('.brand-sub').textContent.includes('%s')" % ("Septiembre" if activo0["mes"] == 9 else "Lote"), timeout=15000)
        check("'Usar este lote' cambia el lote activo del servidor", api("GET", "/api/status")[1]["active_lote"]["id"] == activo0["id"])
        # monitor ?lote=
        lote_nuevo = next(l for l in api("GET", "/api/lotes")[1] if l["id"] != activo0["id"])
        pg.goto(BASE + f"/monitor?lote={lote_nuevo['id']}", wait_until="networkidle"); pg.wait_for_timeout(800)
        check("/monitor?lote=<id> abre ese lote", pg.inner_text("button.esc-lote .nm") == ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][lote_nuevo["mes"] - 1] + f" {lote_nuevo['anio']}", pg.inner_text("button.esc-lote .nm"))
        check("consola de lotes sin errores inesperados", not [c for c in v.consola if "401" not in str(c) and "favicon" not in str(c)], v.consola)
        br.close()
    finally:
        srv.parar()


def fase_sin_clave(p):
    srv = Servidor("")
    try:
        sembrar()
        br, ctx = nuevo(p, viewport={"width": 390, "height": 844})
        pg = ctx.new_page(); v = Vigia(pg)
        pg.goto(BASE + "/programar", wait_until="networkidle")
        pg.click("button.brand-sub"); pg.wait_for_selector(".sheet .lote")
        pg.select_option("#nlMes", "11"); pg.fill("#nlAnio", "2026")
        pg.click("button:has-text('Crear y usar este lote')")
        pg.wait_for_function("document.querySelector('.brand-sub').textContent.includes('Noviembre')", timeout=15000)
        check("sin clave configurada el lote se crea sin pedir contraseña", pg.locator("#lotePass").count() == 0)
        check("el lote nuevo es el activo", api("GET", "/api/status")[1]["active_lote"]["mes"] == 11)
        br.close()
    finally:
        srv.parar()


with sync_playwright() as pw:
    fase_con_clave(pw)
    fase_sin_clave(pw)
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
