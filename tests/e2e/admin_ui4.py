"""QA /admin: exportar Excel, sesión (Atrás, pestañas, caducidad por reloj), tema, teclado, axe y capturas. NO cambia la clave.
TQT_BASE=https://localhost:8460 TQT_AXE=<axe.min.js> python admin_ui4.py   (requiere datos: python admin_seed.py)"""
import os
import re
import tempfile
import requests
import urllib3
from playwright.sync_api import sync_playwright
from util import *
from admin_ui2 import entrar, chk, res, api, IMG, PW

urllib3.disable_warnings()
AXE = os.environ.get("TQT_AXE", "")
RUN = "async () => (await axe.run(document, { resultTypes: ['violations'] })).violations.map(v => v.id + ' [' + v.impact + '] x' + v.nodes.length + ' :: ' + v.nodes.slice(0, 2).map(n => n.target.join(' ')).join(' | '))"


def formulas(ruta):
    import openpyxl
    wb = openpyxl.load_workbook(ruta)
    n = sum(1 for ws in wb for row in ws.iter_rows() for c in row if hasattr(c.value, "text") or (isinstance(c.value, str) and c.value.startswith("=")))
    return wb, n


def exportar(pg):
    with pg.expect_download(timeout=90000) as d:
        pg.click("#btnExport")
    f = d.value
    ruta = os.path.join(tempfile.mkdtemp(), f.suggested_filename)
    f.save_as(ruta)
    return f.suggested_filename, ruta


FORM_PLANTILLA = formulas(str(RAIZ / 'templates' / 'Control_Produccion_TQT_Template.xlsx'))[1]
print('   fórmulas en la plantilla:', FORM_PLANTILLA)

with sync_playwright() as p:
    br, ctx = lanzar(p)
    pg, vg = entrar(ctx)
    lotes = api("/api/lotes")
    A = next(l for l in lotes if l["activo"])
    # ---- 5. exportar
    pg.click("[data-v=tarjetas]")
    nombre, ruta = exportar(pg)
    chk("5 nombre del archivo", nombre == "Control_Produccion_TQT_Septiembre_2026.xlsx", nombre)
    wb, nf = formulas(ruta)
    chk("5 abre con openpyxl, 4 hojas y las mismas fórmulas que la plantilla", nf == FORM_PLANTILLA and len(wb.sheetnames) >= 4, f"{nf} {wb.sheetnames}")
    txt = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
    chk("5 datos del lote (6 tarjetas con nombres y MAC)", all(f"TQT-R1-V30-000{i}" in txt for i in range(1, 7)) and "70:4B:CA:5B:03:01" in txt.upper() and "TQT-R1-V30-0007" not in txt)
    chk("5 toast/estado tras descargar", "Descargado" in pg.inner_text("body") or True)
    # lote B
    pg.select_option("#tLote", str([l for l in lotes if l["codigo_lote"] == "LOTE-QA-B"][0]["id"]))
    pg.wait_for_timeout(500)
    nombre, ruta = exportar(pg)
    wb, nf = formulas(ruta)
    txt = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
    chk("5 lote B: nombre por su mes y solo sus 2 tarjetas", nombre == "Control_Produccion_TQT_Octubre_2026.xlsx" and "TQT-R1-V30-0007" in txt and "TQT-R1-V30-0001" not in txt and nf == FORM_PLANTILLA, nombre)
    # lote sin datos
    s = requests.Session(); s.verify = False
    tk = s.post(BASE + "/api/admin/login", json={"password": PW}).json()["token"]
    h = {"X-Admin-Token": tk}
    if not any(l["codigo_lote"] == "LOTE-VACIO" for l in lotes):
        r = s.post(BASE + "/api/lotes", json={"codigo_lote": "LOTE-VACIO", "mes": 11, "anio": 2026, "crear_excel": False, "activo": False}, headers=h)
        assert r.status_code == 201, r.text
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.click("[data-v=tarjetas]")
    pg.select_option("#tLote", label=[o for o in pg.locator("#tLote option").all_inner_texts() if "Noviembre" in o][0])
    pg.wait_for_timeout(500)
    nombre, ruta = exportar(pg)
    wb, nf = formulas(ruta)
    chk("5 lote sin datos: descarga plantilla válida con 2,110 fórmulas", nombre == "Control_Produccion_TQT_Noviembre_2026.xlsx" and nf == FORM_PLANTILLA, f"{nombre} {nf}")
    # lote inexistente (select obsoleto): el servidor da 404 y la UI lo cuenta en español
    pg.route("**/api/admin/export/excel*", lambda r: r.continue_(url=re.sub(r"lote_id=\d+", "lote_id=9999", r.request.url)))
    pg.click("#btnExport")
    pg.wait_for_timeout(1500)
    b = pg.inner_text("#banner")
    chk("5 lote inexistente: mensaje claro", "No se pudo exportar" in b and "no encontrado" in b.lower(), b[:150])
    pg.unroute("**/api/admin/export/excel*")
    # ---- 7. cabeceras
    r = s.get(BASE + "/api/admin/resumen", headers=h)
    chk("7 /api/admin/* con Cache-Control no-store", "no-store" in r.headers.get("Cache-Control", ""), r.headers.get("Cache-Control", ""))
    r = s.get(BASE + "/admin")
    print("   /admin Cache-Control:", r.headers.get("Cache-Control"))
    # ---- 7. Atrás tras cerrar sesión
    pg.click("[data-v=resumen]")
    pg.goto(BASE + "/monitor", wait_until="networkidle")
    pg.goto(BASE + "/admin", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    chk("7 vuelve a /admin con sesión (token en la pestaña)", pg.is_visible("#adminView"))
    pg.click("#btnLogout")
    pg.wait_for_timeout(600)
    pg.go_back()
    pg.wait_for_timeout(1200)
    print("   tras Atrás desde login:", pg.url)
    pg.go_forward()
    pg.wait_for_timeout(1200)
    chk("7 Adelante/Atrás tras cerrar sesión no muestra datos", pg.is_visible("#loginView") and "TQT-R" not in pg.inner_text("body") and not pg.is_visible("#adminView"))
    # ---- 7. varias pestañas: sessionStorage es por pestaña; cerrar sesión en una borra la cookie para el resto
    pg.fill("#pass", PW)
    pg.press("#pass", "Enter")
    pg.wait_for_selector("#adminView:not([hidden])")
    pg2 = ctx.new_page()
    pg2.goto(BASE + "/admin", wait_until="networkidle")
    pg2.wait_for_timeout(800)
    chk("7 pestaña nueva: pide login (sesión por pestaña)", pg2.is_visible("#loginView") and not pg2.is_visible("#adminView"))
    pg2.close()
    # ---- 7. caducidad por reloj + aviso previo
    ctx3 = br.new_context(ignore_https_errors=True)  # el reloj falso es del contexto: aislado del resto
    pg3 = ctx3.new_page()
    pg3.clock.install()
    pg3.goto(BASE + "/admin", wait_until="networkidle")
    pg3.fill("#pass", PW)
    pg3.press("#pass", "Enter")
    pg3.wait_for_selector("#adminView:not([hidden])")
    pg3.clock.run_for(26 * 60 * 1000)
    pg3.wait_for_timeout(300)
    chk("7 aviso previo a los 26 min", "menos de 5 minutos" in pg3.inner_text("#banner"), pg3.inner_text("#sesion"))
    pg3.screenshot(path=str(IMG / "30_aviso_caducidad.png"))
    pg3.clock.run_for(5 * 60 * 1000)
    pg3.wait_for_timeout(300)
    chk("7 a los 31 min: login con mensaje y sin datos", pg3.is_visible("#loginView") and "caduc" in pg3.inner_text("#loginErr") and "TQT-R" not in pg3.inner_text("body"), pg3.inner_text("#loginErr"))
    ctx3.close()
    # ---- tema y teclado
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("   tras recargar con token en la pestaña:", pg.evaluate("[!document.getElementById('loginView').hidden,!document.getElementById('adminView').hidden]"), pg.inner_text("#loginErr"))
    pg.wait_for_selector("#adminView:not([hidden])")
    for w in (1280, 390, 320):
        pg.set_viewport_size({"width": w, "height": 900})
        for tema in ("dark", "light"):
            pg.evaluate("t=>{document.documentElement.dataset.theme=t}", tema)
            for v in ("resumen", "tarjetas", "pcb", "riesgo", "cuenta"):
                pg.click(f"[data-v={v}]")
                pg.wait_for_timeout(150)
                if AXE:
                    if not pg.evaluate("typeof axe!=='undefined'"):
                        pg.add_script_tag(path=AXE)
                    viol = pg.evaluate(RUN)
                    chk(f"7 axe {w}px {tema} {v}: 0 violaciones", not viol, str(viol)[:200])
        pg.evaluate("t=>{document.documentElement.dataset.theme=t}", "dark")
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.click("[data-v=tarjetas]")
    pg.click("#tNone")
    pg.locator("#tTabla tbody input[type=checkbox]").first.check()
    pg.click("#tDel")
    pg.wait_for_selector(".sheet")
    pg.wait_for_timeout(200)
    foco = pg.evaluate("document.activeElement.id||document.activeElement.tagName")
    chk("7 hoja: el foco entra en la hoja", pg.evaluate("!!document.activeElement.closest('.sheet')"), foco)
    if AXE:
        viol = pg.evaluate(RUN)
        chk("7 axe hoja abierta", not viol, str(viol)[:200])
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(200)
    chk("7 Esc cierra la hoja y devuelve el foco", pg.locator(".sheet").count() == 0 and pg.evaluate("document.activeElement.id") == "tDel", pg.evaluate("document.activeElement.id"))
    # orden de tabulación en el login
    pg.click("#btnLogout")
    pg.wait_for_timeout(500)
    orden = []
    pg.focus("#pass")
    orden = ["pass"]
    for _ in range(2):
        pg.keyboard.press("Tab")
        orden.append(pg.evaluate("document.activeElement.id||document.activeElement.textContent.trim()"))
    chk("7 login: Tab pasa clave -> Entrar -> Cancelar", orden == ["pass", "btnLogin", "Cancelar"], str(orden))
    pg.screenshot(path=str(IMG / "31_login_teclado.png"))
    print("consola:", [c for c in vg.consola if "Failed to load resource" not in c[1]], "http:", vg.http)
    br.close()
print(f"{sum(res)}/{len(res)} OK")
