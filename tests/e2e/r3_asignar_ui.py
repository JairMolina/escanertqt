"""Celular (/emparejar): al asignar la R3 de una tarjeta deben aparecer las R3 sueltas. Servidor aislado :8464."""
import os, sys
from pathlib import Path
os.environ["TQT_BASE"] = "https://127.0.0.1:8464"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import escritorio_armazon as E  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from util import lanzar  # noqa: E402

proc, tmp = E.arrancar(); ok = True
try:
    for s in ("0011", "0012"):
        for t in ("R1", "R2"):
            E.api("POST", "/api/pcb/manual", {"tipo": t, "version": "30", "serie": s, "cantidad": 1})
    for s in ("0011", "0012", "0013", "0014"):
        E.api("POST", "/api/pcb/manual", {"tipo": "R3", "version": "30", "serie": s, "cantidad": 1})
    E.api("POST", "/api/recepcion/confirmar", {})
    E.api("POST", "/api/emparejar/auto", {"series": ["0011"]})   # 0011 con su R3; 0012 se empareja sin R3 a propósito
    E.api("POST", "/api/tarjetas", {"id_tarjeta_num": "0012", "r1_id": E.api("GET", "/api/pcb?q=R1-V30-0012")["items"][0]["id"],
                                    "r2_id": E.api("GET", "/api/pcb?q=R2-V30-0012")["items"][0]["id"]})
    with sync_playwright() as p:
        br, ctx = lanzar(p, viewport={"width": 390, "height": 800}); pg = ctx.new_page(); logs = []
        pg.on("pageerror", lambda e: logs.append("ERR " + str(e)))
        pg.goto(E.BASE + "/emparejar", wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.locator("#tar .item", has_text="0012").first.click(); pg.wait_for_timeout(800)
        pg.locator(".slot").nth(2).get_by_role("button", name="Asignar").click(); pg.wait_for_timeout(1200)
        n = pg.locator(".sheet .list .item").count()
        print("R3 en la lista:", n, "(esperado 4: 0011 a 0014, R3 manual)", logs)
        ok = n == 4 and not logs
        # selector de R3: manual por defecto; "Automático" se recuerda y monta las R3 del mismo número
        pg.goto(E.BASE + "/emparejar", wait_until="networkidle"); pg.wait_for_timeout(600)
        man = pg.locator('#segR3 button[data-v="manual"]').get_attribute("aria-pressed") == "true"
        pg.locator('#segR3 button[data-v="auto"]').click(); pg.wait_for_timeout(800)
        pg.reload(wait_until="networkidle"); pg.wait_for_timeout(600)
        rec = pg.locator('#segR3 button[data-v="auto"]').get_attribute("aria-pressed") == "true"
        pg.locator("#btnAuto").click(); pg.wait_for_timeout(1200)
        montada = [t for t in E.api("GET", "/api/tarjetas")["items"] if t["id_tarjeta_num"] == "0012"][0]["r3"] is not None
        print("manual por defecto:", man, "| recuerda auto:", rec, "| R3 0012 montada en auto:", montada)
        ok = ok and man and rec and montada
        pg.screenshot(path=str(tmp / "r3.png")); br.close()
finally:
    E.parar(proc)
print("RESULTADO:", "OK" if ok else "FALLA"); sys.exit(0 if ok else 1)
