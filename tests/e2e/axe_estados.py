"""axe-core en estados interactivos (hojas abiertas, tarjeta abierta, teclado MAC, admin con sesión). Requiere datos (corre tras flujo.py).
TQT_AXE=<axe.min.js> python axe_estados.py"""
import os, time
from playwright.sync_api import sync_playwright
from util import *

AXE = os.environ["TQT_AXE"]
SP = Path(os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots")))
RUN = "async () => (await axe.run(document, { resultTypes: ['violations'] })).violations.map(v => v.id + ' [' + v.impact + '] x' + v.nodes.length + ' :: ' + v.nodes.slice(0, 2).map(n => n.target.join(' ') + ' ' + (n.failureSummary || '').split('\\n').slice(1, 2).join('')).join(' | '))"


def axe(pg, nombre):
    pg.add_script_tag(path=AXE)
    v = pg.evaluate(RUN)
    print(f"{nombre}: {'sin violaciones' if not v else ''}")
    for x in v:
        print("   ", x[:330])


with sync_playwright() as p:
    for tema in ("dark", "light"):
        for (w, h) in ((390, 844), (1280, 800)):
            br, ctx = lanzar(p, viewport={"width": w, "height": h}, color_scheme=tema)
            ctx.add_init_script(f"localStorage.setItem('tqt.tema','{tema}')"); ctx.add_init_script(CAM_JS)
            tag = f"[{tema} {w}] "
            pg = ctx.new_page(); pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(600)
            pg.click("#btnManual"); pg.wait_for_timeout(500); axe(pg, tag + "Recibir: hoja Agregar sin QR"); pg.keyboard.press("Escape")
            pg.click("#btnVersion"); pg.wait_for_timeout(400); axe(pg, tag + "Recibir: hoja Versión"); pg.keyboard.press("Escape")
            if pg.locator("#lista .item").count():
                pg.locator("#lista .item").first.click(); pg.wait_for_timeout(400); axe(pg, tag + "Recibir: hoja Editar placa"); pg.keyboard.press("Escape")
                pg.click("#btnConfirm"); pg.wait_for_timeout(400); axe(pg, tag + "Recibir: hoja Confirmar"); pg.keyboard.press("Escape")
            pg.evaluate("__showQR('TQT-R2-V30-%d', true)" % (9000 + w % 97 + (1 if tema == 'dark' else 2))); pg.wait_for_timeout(1500); axe(pg, tag + "Recibir: tras lectura (readout/lista/avisos)")
            pg = ctx.new_page(); pg.goto(BASE + "/emparejar", wait_until="networkidle"); pg.wait_for_timeout(600)
            if pg.locator("#tar .item").count():
                pg.locator("#tar .item").first.click(); pg.wait_for_timeout(500); axe(pg, tag + "Emparejar: hoja tarjeta")
                pg.locator(".sheet button:has-text('Cambiar')").first.click(); pg.wait_for_timeout(700); axe(pg, tag + "Emparejar: selector de placa")
                pg.keyboard.press("Escape"); pg.keyboard.press("Escape")
            pg.click("#btnArmar"); pg.wait_for_timeout(400); axe(pg, tag + "Emparejar: armar a mano"); pg.keyboard.press("Escape")
            pg = ctx.new_page(); pg.goto(BASE + "/programar", wait_until="networkidle"); pg.wait_for_timeout(600)
            if pg.locator("#lista .item").count():
                pg.locator("#lista .item").first.click(); pg.wait_for_timeout(400); pg.fill("#macIn", "704BCA5B"); axe(pg, tag + "Programar: MAC parcial + teclado")
            pg = ctx.new_page(); pg.goto(BASE + "/pruebas", wait_until="networkidle"); pg.wait_for_timeout(500)
            pg.fill("#q", "0001"); pg.wait_for_timeout(600)
            if pg.locator("button.item:has(span.mono)").count():
                pg.locator("button.item:has(span.mono)").first.click(); pg.wait_for_timeout(300)
                pg.locator("button[aria-expanded]").first.click(); pg.wait_for_timeout(300); axe(pg, tag + "Pruebas: tarjeta con etapa abierta")
            pg.click("#segModo button[data-m='etapa']"); pg.wait_for_timeout(400); axe(pg, tag + "Pruebas: por etapa")
            pg.click("#segModo button[data-m='masivo']"); pg.wait_for_timeout(400); axe(pg, tag + "Pruebas: masivo")
            if w >= 1000:
                pm = ctx.new_page(); pm.goto(BASE + "/monitor", wait_until="networkidle"); pm.wait_for_timeout(600)
                for v in ("inventario", "tarjetas"):
                    pm.evaluate(f"location.hash='#/{v}'"); pm.wait_for_timeout(700); axe(pm, tag + f"Monitor: {v}")
                pa = ctx.new_page(); pa.goto(BASE + "/admin", wait_until="networkidle")
                pa.fill("#pass", "ClaveQA-12345"); pa.click("#btnLogin"); pa.wait_for_timeout(1000); axe(pa, tag + "Admin: resumen")
                for tab in pa.locator(".desk-nav [role=tab], .desk-nav button").all():
                    nombre = tab.inner_text().strip()
                    tab.click(); pa.wait_for_timeout(500); axe(pa, tag + f"Admin: {nombre}")
            br.close()
