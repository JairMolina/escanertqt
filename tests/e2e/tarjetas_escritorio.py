"""Consola de PC > Tarjetas: vista «Por emparejar», emparejar, asignar R3 a mano y armar a mano. Chrome real, servidor aislado :8464."""
import os, sys
from pathlib import Path
os.environ["TQT_BASE"] = "https://127.0.0.1:8464"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import escritorio_armazon as E  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from util import lanzar  # noqa: E402

ok_total = True
def check(n, ok, d=""):
    global ok_total; ok_total &= bool(ok); print(("  ok   " if ok else "  FALLA"), n, "" if ok else d, flush=True)

proc, tmp = E.arrancar()
try:
    def man(t, s): E.api("POST", "/api/pcb/manual", {"tipo": t, "version": "30", "serie": s, "cantidad": 1})
    for s in ("0011", "0012", "0013"): man("R1", s); man("R2", s)
    man("R1", "0021"); man("R2", "0030")                          # impar
    for s in ("0011", "0040", "0041"): man("R3", s)
    E.api("POST", "/api/recepcion/confirmar", {})
    with sync_playwright() as p:
        br, ctx = lanzar(p, viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(E.BASE + "/monitor#/tarjetas", wait_until="networkidle"); pg.wait_for_timeout(1200)
        filas = pg.locator("#sugT").locator("xpath=ancestor::section").locator("tr[data-k]").count()
        check("Por emparejar muestra 3 parejas + 1 impar", filas == 4, str(filas))
        pg.screenshot(path=str(tmp / "tar1.png"))
        pg.get_by_role("button", name="Emparejar completas").click(); pg.wait_for_timeout(1500)
        check("se crearon 4 tarjetas (R3 manual: sin R3)", len(E.api("GET", "/api/tarjetas")["items"]) == 4)
        check("la tabla de tarjetas ya las muestra", pg.locator("tr[data-k]").count() >= 4)
        pg.locator("tr[data-k]", has_text="0011").first.click(); pg.wait_for_timeout(500)
        pg.locator(".esc-panel").get_by_role("button", name="Asignar R3").click(); pg.wait_for_timeout(1000)
        check("el selector lista 3 R3 sueltas", pg.locator(".sheet .btn-ghost.btn").filter(has_text="R3-V30").count() == 3)
        pg.locator(".sheet").get_by_role("button", name="TQT-R3-V30-0040").click(); pg.wait_for_timeout(1200)
        t11 = [t for t in E.api("GET", "/api/tarjetas")["items"] if t["id_tarjeta_num"] == "0011"][0]
        check("R3 0040 asignada a la tarjeta 0011", t11["nombre_r3"] == "TQT-R3-V30-0040", str(t11.get("nombre_r3")))
        pg.screenshot(path=str(tmp / "tar2.png"))
        check("sin errores de JS", not errs, str(errs))
        br.close()
finally:
    E.parar(proc)
print("RESULTADO:", "OK" if ok_total else "FALLA"); sys.exit(0 if ok_total else 1)
