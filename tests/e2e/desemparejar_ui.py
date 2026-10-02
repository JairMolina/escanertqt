"""Consola de PC: cambiar el tipo de una placa emparejada, emparejar completas y desemparejar (una y todas). Chrome real, servidor aislado :8464."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import escritorio_armazon as E  # noqa: E402  (reutiliza servidor aislado/api; no ejecuta el recorrido)
from playwright.sync_api import sync_playwright  # noqa: E402
from util import lanzar  # noqa: E402

ok_total = True
def check(n, ok, d=""):
    global ok_total; ok_total &= bool(ok); print(("  ok   " if ok else "  FALLA"), n, "" if ok else d, flush=True)

proc, tmp = E.arrancar()
try:
    for s in ("0011", "0012", "0013"):
        for t in ("R1", "R2", "R3"):
            E.api("POST", "/api/pcb/manual", {"tipo": t, "version": "30", "serie": s, "cantidad": 1})
    E.api("POST", "/api/recepcion/confirmar", {})
    with sync_playwright() as p:
        br, ctx = lanzar(p, viewport={"width": 1280, "height": 800})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(E.BASE + "/monitor#/tarjetas", wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.get_by_role("button", name="Emparejar completas").click(); pg.wait_for_timeout(1200)
        check("emparejar completas crea 3 tarjetas", len(E.api("GET", "/api/tarjetas")["items"]) == 3)
        # editar una placa asignada: R2 debe estar habilitado
        pg.goto(E.BASE + "/monitor#/inventario?q=0011", wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.get_by_role("button", name="Editar TQT-R1-V30-0011").click(); pg.wait_for_timeout(400)
        seg = pg.locator('.sheet .seg button')
        check("botones R2/R3 habilitados en placa asignada", seg.nth(1).is_enabled() and seg.nth(2).is_enabled())
        seg.nth(1).click(); pg.fill("#eSer", "0099"); pg.wait_for_timeout(200)
        check("aviso de salida de la tarjeta visible", pg.locator(".sheet .hint:not(.err)").filter(has_text="sale de la tarjeta").is_visible())
        pg.get_by_role("button", name="Guardar").click(); pg.wait_for_timeout(1000)
        p2 = E.api("GET", "/api/pcb?q=0099")["items"]
        check("placa quedó R2 0099 suelta", p2 and p2[0]["tipo"] == "R2" and p2[0]["estado_ciclo"] == "DISPONIBLE", str(p2))
        # desemparejar una desde el panel
        pg.goto(E.BASE + "/monitor#/tarjetas", wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.locator("tr[data-k]").first.click(); pg.wait_for_timeout(400)
        pg.locator(".esc-panel").get_by_role("button", name="Desemparejar").click(); pg.wait_for_timeout(300)
        pg.locator(".sheet").get_by_role("button", name="Desemparejar 1").click(); pg.wait_for_timeout(1000)
        check("desemparejar una: quedan 2", len(E.api("GET", "/api/tarjetas")["items"]) == 2)
        # desemparejar todas
        pg.get_by_role("button", name="Desemparejar todas").click(); pg.wait_for_timeout(300)
        pg.locator(".sheet").get_by_role("button", name="Desemparejar 2").click(); pg.wait_for_timeout(1000)
        check("desemparejar todas: quedan 0", len(E.api("GET", "/api/tarjetas")["items"]) == 0)
        pg.screenshot(path=str(tmp / "des.png"))
        check("sin errores de JS", not errs, str(errs))
        br.close()
finally:
    E.parar(proc)
print("RESULTADO:", "OK" if ok_total else "FALLA"); sys.exit(0 if ok_total else 1)
