"""QA /admin: paneles con datos reales (resumen, tarjetas, PCB) contra la API. Solo lectura. TQT_BASE=https://localhost:8460"""
import json, os, requests, urllib3
from playwright.sync_api import sync_playwright
from util import *
urllib3.disable_warnings()
PW = os.environ.get("TQT_ADMIN_PASSWORD", "ClaveDePrueba-123")
IMG = RAIZ / "docs" / "qa" / "admin_img"; IMG.mkdir(parents=True, exist_ok=True)
res = []
def chk(n, ok, extra=""):
    res.append(ok); print(("OK   " if ok else "FALLA"), n, extra)
def api(path):
    return requests.get(BASE + path, verify=False).json()

def entrar(ctx, w=1280, h=900):
    pg = ctx.new_page(); pg.set_viewport_size({"width": w, "height": h}); vg = Vigia(pg)
    pg.goto(BASE + "/admin", wait_until="networkidle"); pg.fill("#pass", PW); pg.click("#btnLogin")
    pg.wait_for_selector("#adminView:not([hidden])"); pg.wait_for_timeout(1200)
    return pg, vg

def filas(pg, sel):
    return pg.evaluate("s=>[...document.querySelectorAll(s+' tbody tr')].map(r=>[...r.cells].map(c=>c.innerText.trim()))", sel)

if __name__ == "__main__":
  with sync_playwright() as p:
    br, ctx = lanzar(p)
    pg, vg = entrar(ctx)
    lotes = api("/api/lotes"); tar_all = {l["id"]: api(f"/api/tarjetas?limit=500&lote_id={l['id']}") for l in lotes}
    pcb = api("/api/pcb?limit=5000")
    # --- resumen
    kp = pg.evaluate("()=>[...document.querySelectorAll('#resumenBox .kpi')].map(k=>[k.querySelector('.lbl').innerText,k.querySelector('.v').innerText])")
    d = dict((a.lower(), b) for a, b in kp)
    chk("3 resumen: tarjetas = suma de API", d["tarjetas"] == str(sum(v["total"] for v in tar_all.values())), str(kp))
    chk("3 resumen: PCB = API", d["pcb en inventario"] == str(pcb["total"]))
    pg.screenshot(path=str(IMG / "10_resumen_1280.png"), full_page=True)
    # --- tarjetas
    pg.click("[data-v=tarjetas]"); pg.wait_for_timeout(400)
    act = next(l for l in lotes if l["activo"])
    chk("3 tarjetas: lote activo preseleccionado", pg.input_value("#tLote") == str(act["id"]))
    for l in lotes:
        pg.select_option("#tLote", str(l["id"])); pg.wait_for_timeout(700)
        fr = filas(pg, "#tTabla"); api_items = sorted(tar_all[l["id"]]["items"], key=lambda t: t["id"])
        chk(f"3 tarjetas lote {l['codigo_lote']}: filas = API ({len(api_items)})", len(fr) == len(api_items), str(len(fr)))
        ok = True
        for t in api_items:
            row = next((r for r in fr if r[1] == t["id_tarjeta_num"]), None)
            if not row or row[2] != (t["nombre_r1"] or "—") or row[3] != (t["nombre_r2"] or "—") or row[4] != (t["nombre_r3"] or "—") or t["estado_general"].lower() not in row[6].lower():
                ok = False; print("   difiere", t["id_tarjeta_num"], row, t["estado_general"])
        chk(f"3 tarjetas lote {l['codigo_lote']}: cada dato coincide", ok)
    pg.select_option("#tLote", str(act["id"])); pg.wait_for_timeout(600)
    pg.fill("#tQ", "70:4b:ca:5b:03:02"); pg.wait_for_timeout(500); chk("3 tarjetas: búsqueda por MAC", len(filas(pg, "#tTabla")) == 1 and filas(pg, "#tTabla")[0][1] == "0003", str(filas(pg, "#tTabla")))
    pg.fill("#tQ", "TQT-R2-V30-0005"); pg.wait_for_timeout(500); chk("3 tarjetas: búsqueda por nombre R2", [r[1] for r in filas(pg, "#tTabla")] == ["0005"])
    pg.fill("#tQ", "zzzz"); pg.wait_for_timeout(500); chk("3 tarjetas: sin resultados -> mensaje", "No hay tarjetas" in pg.inner_text("#tTabla"))
    pg.fill("#tQ", ""); pg.wait_for_timeout(400)
    for est in ("LIBERADO", "DETENIDO", "EN PROCESO"):
        pg.select_option("#tEstado", est); pg.wait_for_timeout(300)
        exp = sum(1 for t in tar_all[act["id"]]["items"] if t["estado_general"] == est)
        chk(f"3 tarjetas: filtro {est} = {exp}", len(filas(pg, "#tTabla")) == exp, str(len(filas(pg, "#tTabla"))))
    pg.select_option("#tEstado", ""); pg.wait_for_timeout(300)
    pg.click("#tAllLote"); n = len(filas(pg, "#tTabla")); txt = pg.inner_text("#tSel"); chk("3 tarjetas: seleccionar todas del lote + contador", txt.startswith(f"{n} seleccionadas de {n}") and not pg.is_disabled("#tDel"), txt)
    pg.click("#tNone"); chk("3 tarjetas: quitar selección", pg.inner_text("#tSel").startswith("0 ") and pg.is_disabled("#tDel"))
    pg.locator("#tTabla thead input[type=checkbox]").check(); chk("3 tarjetas: casilla cabecera selecciona visibles", pg.inner_text("#tSel").startswith(f"{n} "), pg.inner_text("#tSel"))
    pg.locator("#tTabla tbody input[type=checkbox]").first.uncheck(); chk("3 tarjetas: desmarcar una actualiza contador", pg.inner_text("#tSel").startswith(f"{n-1} "), pg.inner_text("#tSel"))
    pg.click("#tNone")
    pg.screenshot(path=str(IMG / "11_tarjetas_1280.png"), full_page=True)
    # --- PCB
    pg.click("[data-v=pcb]"); pg.wait_for_timeout(400)
    fr = filas(pg, "#pTabla"); chk("3 pcb: 90 filas (sin filtro) = API", len(fr) == pcb["total"] == 90, str(len(fr)))
    ok = True
    for r in fr:
        a = next(x for x in pcb["items"] if x["nombre"] == r[2])
        mac = "—" if a["tipo"] == "R3" else (a["mac"] or "sin MAC")
        if r[3] != mac or r[5] != (a["id_tarjeta_num"] or "—"): ok = False; print("   difiere", r, a["mac"])
    chk("3 pcb: nombre/MAC/tarjeta coinciden con la API", ok)
    for tipo in ("R1", "R2", "R3"):
        pg.select_option("#pTipo", tipo); pg.wait_for_timeout(250)
        chk(f"3 pcb: tipo {tipo} = 30", len(filas(pg, "#pTabla")) == 30)
    pg.select_option("#pTipo", "")
    for ciclo, exp in (("ASIGNADA", 24), ("DISPONIBLE", 66)):
        pg.select_option("#pCiclo", ciclo); pg.wait_for_timeout(250)
        chk(f"3 pcb: estado {ciclo} = {exp}", len(filas(pg, "#pTabla")) == exp, str(len(filas(pg, "#pTabla"))))
    pg.select_option("#pCiclo", "")
    pg.fill("#pQ", "70:4b:ca:5b:02:01"); pg.wait_for_timeout(400); chk("3 pcb: MAC", [r[2] for r in filas(pg, "#pTabla")] == ["TQT-R1-V30-0002"], str(filas(pg, "#pTabla")))
    pg.fill("#pQ", "0007"); pg.wait_for_timeout(400); chk("3 pcb: serie 0007 -> 3 placas", len(filas(pg, "#pTabla")) == 3)
    pg.fill("#pQ", ""); pg.wait_for_timeout(300); pg.screenshot(path=str(IMG / "12_pcb_1280.png"))
    # --- 390 px: tablas anchas
    for w in (390, 320):
        pg.set_viewport_size({"width": w, "height": 800}); pg.wait_for_timeout(300)
        for v in ("resumen", "tarjetas", "pcb", "riesgo", "cuenta"):
            pg.click(f"[data-v={v}]"); pg.wait_for_timeout(200)
            sw = pg.evaluate("document.documentElement.scrollWidth")
            chk(f"3 {w}px {v}: sin scroll horizontal de página", sw <= w, str(sw))
            pg.screenshot(path=str(IMG / f"13_{v}_{w}.png"), full_page=True)
    print("consola:", vg.consola, "http:", vg.http, "externas:", vg.externas)
    br.close()
  print(f"{sum(res)}/{len(res)} OK")
