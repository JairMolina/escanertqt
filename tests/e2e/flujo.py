"""Recorrido completo del operador (Recibir -> ... -> /admin) con Chrome real. Requiere servidor aislado en TQT_BASE."""
import json, sys, time
from playwright.sync_api import sync_playwright, expect
from util import *

SP = os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots"))
os.makedirs(SP, exist_ok=True)
hall = []
def hallazgo(x): hall.append(x); print("HALLAZGO:", x, flush=True)
def shot(page, n): page.screenshot(path=f"{SP}/{n}.png")
def api(page, path, **kw):
    return page.evaluate("async ([p,o])=>{const r=await fetch(p,o);let d=null;try{d=await r.json()}catch(e){};return {s:r.status,d}}", [path, kw or {}])

with sync_playwright() as p:
    # ---- 1a) QR real invertido (foto de referencia) con cámara falsa de Chrome
    mj = Path(SP).resolve() / "qr.mjpeg"
    mj.write_bytes(FIXTURE_QR.read_bytes() * 30)
    br, ctx = lanzar(p, extra=["--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={mj}"], viewport={"width": 390, "height": 844})
    pg = ctx.new_page(); v = Vigia(pg)
    pg.goto(BASE + "/"); pg.wait_for_load_state("networkidle")
    try:
        expect(pg.locator("#roName")).to_have_text("TQT-R3-V30-0084", timeout=15000)
        print("OK foto real: leido", pg.locator("#roName").inner_text(), "|", pg.locator("#roMsg").inner_text())
    except Exception as e:
        hallazgo(f"foto real invertida no se leyó con cámara falsa: {pg.locator('#roName').inner_text()}")
    time.sleep(1.5); shot(pg, "01_foto_real")
    br.close()

    # ---- 1b) resto con cámara canvas
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844})
    ctx.add_init_script(CAM_JS)
    pg = ctx.new_page(); v = Vigia(pg)
    pg.goto(BASE + "/"); pg.wait_for_load_state("networkidle")
    for s in ("0001", "0002", "0003"):
        pg.evaluate("([t])=>__showQR(t,true)", [f"TQT-R3-V30-{s}"])
        pg.wait_for_function("(t)=>document.getElementById('roName').textContent===t", arg=f"TQT-R3-V30-{s}", timeout=6000)
        pg.wait_for_function("()=>!document.querySelector('.item[data-pending=\"1\"]')", timeout=5000)
        pg.evaluate("__clearQR()"); time.sleep(0.3)
    print("R3 por camara:", pg.locator("#cR3").inner_text(), "total", pg.locator("#cT").inner_text())
    # manuales R1 y R2 (4 c/u)
    for t in ("R1", "R2"):
        pg.click("#btnManual"); pg.click(f".sheet .seg button:text-is('{t}')")
        pg.fill("#mnQty", "4"); pg.click(".sheet .actions button:has-text('Agregar')")
        pg.wait_for_selector(".toast:has-text('agregadas')"); pg.wait_for_selector(".sheet", state="detached")
    time.sleep(0.6)
    print("contadores", [pg.locator(i).inner_text() for i in ("#cR1", "#cR2", "#cR3", "#cT")], "CTA", pg.locator("#ctaCount").inner_text())
    print("avisos:", pg.locator("#avisos").inner_text().replace("\n", " | "))
    shot(pg, "02_recibir_12")
    pg.click("#btnConfirm"); shot(pg, "03_confirmar_hoja")
    print("hoja:", pg.locator(".sheet").inner_text().replace("\n", " | "))
    pg.click(".sheet .actions button:has-text('Confirmar lote')")
    pg.wait_for_selector(".toast:has-text('confirmadas')")
    time.sleep(0.5)
    print("tras confirmar: total", pg.locator("#cT").inner_text(), "| lista:", pg.locator("#lista").inner_text().replace("\n", " ")[:80])
    print("inventario", api(pg, "/api/stats")["d"]["inventario"])

    # ---- 2) Emparejar
    pg.goto(BASE + "/emparejar"); pg.wait_for_load_state("networkidle")
    print("emparejar: comp", pg.locator("#nComp").inner_text(), "inc", pg.locator("#nInc").inner_text(), "sueltas", pg.locator("#nSue").inner_text(), "| auto", pg.locator("#autoCount").inner_text())
    shot(pg, "04_emparejar_antes")
    pg.click("#btnAuto"); pg.wait_for_selector(".toast:has-text('tarjeta')")
    time.sleep(0.8); shot(pg, "05_emparejar_despues")
    print("tras auto: tarjetas", pg.locator("#nTar").inner_text(), "comp", pg.locator("#nComp").inner_text(), "inc", pg.locator("#nInc").inner_text(), "sueltas", pg.locator("#nSue").inner_text())
    print("tarjetas API:", [(t["id_tarjeta_num"], t["nombre_r1"], t["nombre_r2"], t["nombre_r3"]) for t in api(pg, "/api/tarjetas?limit=50")["d"]["items"]])
    print("sugerencias:", json.dumps({k: (v if k != "sueltas" else {t: [x["nombre"] for x in l] for t, l in v.items()}) for k, v in api(pg, "/api/emparejar/sugerencias")["d"].items() if k in ("completas", "incompletas", "sueltas")})[:600])
    print("vigia consola:", v.consola, "http:", v.http, "ext:", v.externas)
    br.close()
