"""Recorrido (parte 2): Programar -> Pruebas -> reemplazo (impar) -> Monitor -> DYMO -> Excel -> /admin.
Continúa el estado que deja flujo.py (4 tarjetas 0001-0004 y R3 0084 suelta)."""
import json, sys, time, glob
from playwright.sync_api import sync_playwright, expect
from util import *

SP = os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots"))
XL = os.environ.get("TQT_EXCEL_DIR", "")
os.makedirs(SP, exist_ok=True)
hall = []
def hallazgo(x): hall.append(x); print("HALLAZGO:", x, flush=True)
def shot(page, n): page.screenshot(path=f"{SP}/{n}.png")
def api(page, path, **kw):
    return page.evaluate("async ([p,o])=>{const r=await fetch(p,o);let d=null;try{d=await r.json()}catch(e){};return {s:r.status,d}}", [path, kw or {}])

def set_prueba(pg, num, etapa_label, estado):
    pg.fill("#q", num)
    pg.click(f"button.item:has(span.mono:text-is('{num}'))")
    pg.click(f"button[aria-expanded]:has-text('{etapa_label}')")
    pg.click(f".estado-btn[data-e='{estado}']")
    time.sleep(0.35)

with sync_playwright() as p:
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844})
    ctx.add_init_script(CAM_JS)
    pg = ctx.new_page(); v = Vigia(pg)

    # ---------------- Programar
    pg.goto(BASE + "/programar"); pg.wait_for_load_state("networkidle")
    nombres = [b.get_attribute("aria-label").replace("Capturar MAC de ", "") for b in pg.locator("#lista button.item").all()]
    print("pendientes de MAC:", nombres)
    shot(pg, "10_programar_lista")
    i = 0
    for n in nombres:
        i += 1
        mac = "704BCA5B%04X" % (0x9F00 + i)
        pg.click(f"button[aria-label='Capturar MAC de {n}']")
        pg.fill("#macIn", mac)
        pg.wait_for_function("()=>document.getElementById('macHint').textContent.includes('sin repetir')", timeout=4000)
        if i == 1: shot(pg, "11_programar_mac_ok")
        pg.click("button:has-text('Guardar MAC')")
        pg.wait_for_selector(f".toast:has-text('{n}')")
    time.sleep(0.5)
    print("tras programar, lista:", pg.locator("#lista").inner_text().replace("\n", " | "))
    # MAC duplicada: reintenta con una MAC ya usada sobre una placa ya programada no aparece; se prueba con la API
    pcbs = api(pg, "/api/pcb?limit=100")["d"]["items"]
    print("MACs:", [(x["nombre"], x["mac"]) for x in pcbs if x["mac"]][:3], "... total", sum(1 for x in pcbs if x["mac"]))

    # ---------------- Pruebas (modo unitario)
    pg.goto(BASE + "/pruebas"); pg.wait_for_load_state("networkidle")
    pg.click("#segModo button[data-m='unit']") if pg.locator("#segModo button[data-m='unit']").count() else None
    for et in ("Soldadura", "Programación", "Prueba PCB", "Integración", "Prueba Final"):
        set_prueba(pg, "0001", et, "OK")
    print("0001:", pg.locator(".card-t header").inner_text().replace("\n", " "))
    shot(pg, "12_pruebas_0001")
    set_prueba(pg, "0002", "Soldadura", "OK"); set_prueba(pg, "0002", "Programación", "OK"); set_prueba(pg, "0002", "Prueba PCB", "FALLA")
    print("0002:", pg.locator(".card-t header").inner_text().replace("\n", " "))
    set_prueba(pg, "0003", "Soldadura", "OK")
    print("0003:", pg.locator(".card-t header").inner_text().replace("\n", " "))
    tar = {t["id_tarjeta_num"]: t for t in api(pg, "/api/tarjetas?limit=50")["d"]["items"]}
    print("estados:", {k: t["estado_general"] for k, t in tar.items()})

    # ---------------- Emparejar: falla de R3 de la 0002 + reemplazo por la suelta 0084 -> impar
    pg.goto(BASE + "/emparejar"); pg.wait_for_load_state("networkidle")
    pg.click("button[aria-label='Tarjeta 0002. Abrir']")
    shot(pg, "13_tarjeta_0002")
    slot = pg.locator(".sheet .slot").nth(2)
    slot.locator("button:has-text('Falla')").click()
    pg.click(".sheet:last-of-type button:has-text('Elegir reemplazo')") if False else pg.locator(".sheet button:has-text('Elegir reemplazo')").click()
    pg.wait_for_selector(".sheet button.item:has-text('TQT-R3-V30-0084')")
    shot(pg, "14_elegir_reemplazo")
    pg.click(".sheet button.item:has-text('TQT-R3-V30-0084')")
    pg.fill("#fMot", "cortocircuito")
    pg.click(".sheet button:has-text('Marcar falla')")
    pg.wait_for_selector(".toast:has-text('marcada en falla')")
    time.sleep(0.8)
    t2 = api(pg, "/api/tarjetas?search=0002")["d"]["items"][0]
    print("0002 tras reemplazo:", t2["nombre_r3"], t2["estado_general"], [t2[k] for k in ("soldadura", "programacion", "prueba_pcb")])
    shot(pg, "15_tarjeta_impar")
    print("lista emparejar:", pg.locator("#tar").inner_text().replace("\n", " | ")[:300])
    # etapa OK otra vez en la 0002 tras reemplazo
    pg.goto(BASE + "/pruebas"); pg.wait_for_load_state("networkidle")
    set_prueba(pg, "0002", "Soldadura", "OK")

    # ---------------- Monitor
    pm = ctx.new_page(); vm = Vigia(pm)
    pm.set_viewport_size({"width": 1280, "height": 800})
    pm.goto(BASE + "/monitor"); pm.wait_for_load_state("networkidle"); time.sleep(0.8)
    print("KPIs:", pm.locator("#sec-resumen .esc-kpis").all_inner_texts())
    print("atencion:", pm.locator("#sec-resumen table.esc-t").first.inner_text().replace("\n", " | ")[:300])
    print("feed:", pm.locator("#sec-resumen .esc-feed").inner_text().replace("\n", " | ")[:400])
    shot(pm, "16_monitor_resumen")
    print("API stats:", api(pm, "/api/stats")["d"])
    pm.evaluate("location.hash='#/inventario'"); time.sleep(0.8); shot(pm, "17_monitor_inv")
    print("inventario filas:", pm.locator("#sec-inventario tbody tr").count(), "|", pm.locator("#sec-inventario table").inner_text().replace("\n", " ")[:200])
    pm.evaluate("location.hash='#/tarjetas'"); time.sleep(0.8); shot(pm, "18_monitor_tar")
    print("tarjetas:", pm.locator("#sec-tarjetas table").inner_text().replace("\n", " | ")[:500])

    # ---------------- DYMO
    pd = ctx.new_page(); vd = Vigia(pd)
    pd.set_viewport_size({"width": 1280, "height": 800})
    pd.goto(BASE + "/dymo"); pd.wait_for_load_state("networkidle"); time.sleep(1.0)
    opts = [o.inner_text() for o in pd.locator("#selTarjeta option").all()]
    print("dymo opciones:", opts)
    pd.select_option("#selTarjeta", label=[o for o in opts if "0001" in o][0])
    time.sleep(1.0)
    print("etiqueta 0001 texto:", repr(pd.locator("#dymoLabelContainer").inner_text()))
    print("aviso:", pd.locator("#aviso").inner_text().replace("\n", " | "))
    shot(pd, "19_dymo_0001")
    pd.select_option("#selTarjeta", label=[o for o in opts if "0002" in o][0]); time.sleep(0.8)
    print("etiqueta 0002 texto:", repr(pd.locator("#dymoLabelContainer").inner_text()))
    print("aviso 0002:", pd.locator("#aviso").inner_text().replace("\n", " | "))
    for n in ("0001", "0002", "0003", "0004"):
        t = api(pd, "/api/tarjetas?search=" + n)["d"]["items"][0]
        lab = api(pd, f"/api/dymo/label/{t['id']}")["d"]
        print("API dymo", n, repr(lab.get("texto")), lab.get("estado_etiqueta"))

    # ---------------- Excel
    pm.bring_to_front()
    pm.evaluate("location.hash='#/excel'"); time.sleep(0.8)
    pm.click("#sec-excel button:has-text('Sincronizar Excel')"); time.sleep(2.5)
    print("sync banner:", pm.locator("#sec-excel .banner").first.inner_text().replace("\n", " | "))
    print("toasts:", pm.locator(".toast").all_inner_texts())
    shot(pm, "20_monitor_sync")
    if XL:
        print("excel:", glob.glob(XL + "/*"))

    # ---------------- Admin
    pa = ctx.new_page(); va = Vigia(pa)
    pa.set_viewport_size({"width": 1280, "height": 800})
    pa.goto(BASE + "/admin"); pa.wait_for_load_state("networkidle")
    shot(pa, "21_admin_login")
    pa.fill("#pass", "ClaveQA-12345"); pa.click("#btnLogin"); time.sleep(1.5)
    shot(pa, "22_admin")
    print("admin resumen:", pa.locator("#resumenBox").inner_text().replace("\n", " | ")[:500])

    for nm, vv in (("recibir", v), ("monitor", vm), ("dymo", vd), ("admin", va)):
        print("VIGIA", nm, "consola", vv.consola, "http", vv.http, "fallos", vv.fallos, "ext", vv.externas)
    br.close()
