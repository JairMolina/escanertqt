"""Robustez: servidor caído y vuelto a levantar, 500 simulados, respuestas lentas (doble envío), textos largos, recarga, Atrás, tema en caliente, horizontal.
Uso: TQT_TMP=<carpeta del servidor> python robustez.py [seccion ...]   (secciones: caida http500 lento largo recarga tema horizontal)
'caida' mata y relanza el servidor del puerto con la MISMA carpeta (no borra datos): usa el servidor aislado de pruebas."""
import json, random, subprocess, sys, time
from playwright.sync_api import sync_playwright
from util import *

TMP = os.environ.get("TQT_TMP", "")
PUERTO = BASE.rsplit(":", 1)[1]
SP = Path(os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots"))); SP.mkdir(parents=True, exist_ok=True)


def matar():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Get-NetTCPConnection -LocalPort {PUERTO} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}"], check=False)


def levantar():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process -FilePath python -ArgumentList 'tests/e2e/servidor.py',{PUERTO},'{TMP}' -WorkingDirectory '{RAIZ}' -WindowStyle Hidden -RedirectStandardOutput '{TMP}.re.log' -RedirectStandardError '{TMP}.re.err.log'"], check=False)
    for _ in range(40):
        time.sleep(0.5)
        r = subprocess.run(["curl", "-sk", "-o", "NUL", "-w", "%{http_code}", BASE + "/api/stats"], capture_output=True, text=True)
        if r.stdout.strip() == "200":
            return True
    return False


def nuevo(p, w=390, h=844, cam=True, **kw):
    br, ctx = lanzar(p, viewport={"width": w, "height": h}, **kw)
    if cam:
        ctx.add_init_script(CAM_JS)
    return br, ctx, ctx.new_page()


def api(pg, path, **kw):
    return pg.evaluate("async ([p,o])=>{const r=await fetch(p,o);let d=null;try{d=await r.json()}catch(e){};return {s:r.status,d}}", [path, kw or {}])


def sec_caida(p):
    print("== CAIDA del servidor con la página abierta (Recibir)")
    br, ctx, pg = nuevo(p); vg = Vigia(pg)
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1000)
    print("indicador inicial:", pg.locator(".conn").inner_text(), pg.locator(".conn").get_attribute("data-s"))
    S1, S2 = random.randint(1000, 4999), random.randint(5000, 9999)
    pg.evaluate(f"__showQR('TQT-R2-V30-{S1}', true)")
    pg.wait_for_function("()=>document.getElementById('roMsg').textContent.startsWith('Registrada')", timeout=5000)
    pg.evaluate("__clearQR()")
    antes = pg.locator("#cT").inner_text()
    matar(); t0 = time.time()
    try:
        pg.wait_for_function("()=>document.querySelector('.conn').dataset.s!=='connected'", timeout=15000)
        print(f"indicador tras caída ({time.time()-t0:.1f} s):", pg.locator(".conn").inner_text(), pg.locator(".conn").get_attribute("data-s"))
    except Exception:
        print("HALLAZGO: el indicador no cambió en 15 s con el servidor caído")
    pg.screenshot(path=str(SP / "rob_caida_indicador.png"))
    # escanear con el servidor caído
    pg.evaluate(f"__showQR('TQT-R2-V30-{S2}', true)"); pg.wait_for_timeout(2500)
    print("readout sin red:", pg.locator("#roMsg").inner_text(), "| fila:", pg.locator("#lista .item").first.inner_text().replace("\n", " "))
    pg.screenshot(path=str(SP / "rob_caida_escaneo.png"))
    pg.evaluate("__clearQR()")
    # tocar Confirmar sin servidor
    print("CTA habilitado?", pg.locator("#btnConfirm").is_enabled())
    ok = levantar(); t1 = time.time()
    print("servidor levantado:", ok)
    try:
        pg.wait_for_function("()=>document.querySelector('.conn').dataset.s==='connected'", timeout=40000)
        print(f"reconectó WS en {time.time()-t1:.1f} s tras levantar el servidor:", pg.locator(".conn").inner_text())
    except Exception:
        print("HALLAZGO: no reconectó el WS en 40 s;", pg.locator(".conn").inner_text())
    pg.wait_for_timeout(3000)
    print("tras reconexión: lista:", [i.inner_text().replace("\n", " ") for i in pg.locator("#lista .item").all()][:4], "| total", pg.locator("#cT").inner_text(), "(antes de caer:", antes, ")")
    r = api(pg, "/api/recepcion")["d"]
    print("servidor tiene borrador:", [x["nombre"] for x in r["items"]])
    pg.screenshot(path=str(SP / "rob_caida_reconectado.png"))
    print("consola:", vg.consola[:6])
    br.close()


def sec_http500(p):
    print("== 500 simulados")
    br, ctx, pg = nuevo(p); vg = Vigia(pg)
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1000)
    pg.route("**/api/pcb/escanear", lambda r: r.fulfill(status=500, content_type="application/json", body='{"detail":"boom"}'))
    pg.evaluate("__showQR('TQT-R1-V30-0601', true)"); pg.wait_for_timeout(2000)
    print("escanear 500 -> readout:", pg.locator("#roMsg").inner_text(), "| fila:", pg.locator("#lista .item").first.inner_text().replace("\n", " "), "| kind:", pg.locator("#readout").get_attribute("data-k"))
    pg.unroute("**/api/pcb/escanear"); pg.evaluate("__clearQR()")
    pg.route("**/api/pcb/escanear", lambda r: r.fulfill(status=200, content_type="application/json", body='{"resultado":"INVALIDA","mensaje":"Código inválido de prueba"}'))
    pg.evaluate("__showQR('TQT-R1-V30-0602', true)"); pg.wait_for_timeout(1500)
    print("INVALIDA -> readout:", pg.locator("#roMsg").inner_text())
    pg.unroute("**/api/pcb/escanear")
    # confirmar con 500
    pg.route("**/api/recepcion/confirmar", lambda r: r.fulfill(status=500, content_type="application/json", body='{"detail":"Error interno"}'))
    pg.click("#btnConfirm"); pg.click(".sheet .actions button:has-text('Confirmar lote')"); pg.wait_for_timeout(1000)
    print("confirmar 500 -> sheet:", pg.locator(".sheet .hint.err").inner_text(), "| sheet sigue abierta:", pg.locator(".sheet").count())
    pg.screenshot(path=str(SP / "rob_confirmar_500.png"))
    pg.keyboard.press("Escape"); pg.unroute("**/api/recepcion/confirmar")
    # cada página con /api/* = 500
    for ruta in ("/emparejar", "/programar", "/pruebas", "/monitor"):
        pg2 = ctx.new_page(); pg2.route("**/api/**", lambda r: r.fulfill(status=500, content_type="application/json", body='{"detail":"caído"}'))
        errs = []; pg2.on("pageerror", lambda e: errs.append(str(e)))
        pg2.goto(BASE + ruta, wait_until="networkidle"); pg2.wait_for_timeout(1200)
        txt = " | ".join(pg2.locator(".toast, .banner, .empty").all_inner_texts())[:200].replace("\n", " ")
        print(f"{ruta} con API en 500: pageerrors={errs} avisos={txt!r}")
        pg2.screenshot(path=str(SP / f"rob_500_{ruta.strip('/')}.png"))
        pg2.close()
    print("consola (ignorando 500 esperados):", [c for c in vg.consola if "500" not in c[1]][:5])
    br.close()


def sec_lento(p):
    print("== respuestas lentas (3 s): doble envío / estados de carga")
    br, ctx, pg = nuevo(p, cam=False); vg = Vigia(pg)
    cuenta = {}

    def lento(ruta):
        def h(route):
            cuenta[ruta] = cuenta.get(ruta, 0) + 1
            pg.wait_for_timeout(3000) if False else None
            route.continue_()
        return h
    # Playwright sync no permite dormir dentro del handler sin bloquear: se usa un proxy con retardo vía fetch wrapper en la página
    pg.add_init_script("""(() => { const f = window.fetch; window.__n = {}; window.__delay = 3000;
      window.fetch = (u, o) => { const k = (o && o.method || 'GET') + ' ' + String(u).split('?')[0]; window.__n[k] = (window.__n[k] || 0) + 1;
        const slow = (o && o.method && o.method !== 'GET'); return slow ? new Promise((res) => setTimeout(res, window.__delay)).then(() => f(u, o)) : f(u, o); }; })()""")
    # preparar datos: 2 series completas sueltas
    pg.goto(BASE + "/", wait_until="networkidle")
    for t in ("R1", "R2", "R3"):
        api(pg, "/api/pcb/manual", method="POST", headers={"Content-Type": "application/json"}, body=json.dumps({"tipo": t, "version": "30", "serie": "0701", "cantidad": 1}))
    api(pg, "/api/recepcion/confirmar", method="POST", headers={"Content-Type": "application/json"}, body="{}")
    # Emparejar: doble clic en el botón auto
    pg.goto(BASE + "/emparejar", wait_until="networkidle"); pg.wait_for_timeout(800)
    print("Emparejar: btnAuto habilitado", pg.locator("#btnAuto").is_enabled(), "series", pg.locator("#autoCount").inner_text())
    pg.dblclick("#btnAuto"); pg.wait_for_timeout(400)
    print("  tras 2 clics: btnAuto deshabilitado durante la petición?", not pg.locator("#btnAuto").is_enabled(), "| POST enviados:", pg.evaluate("window.__n['POST /api/emparejar/auto']"))
    pg.wait_for_timeout(3500)
    print("  toasts:", pg.locator(".toast").all_inner_texts())
    # Programar: doble Enter/clic al guardar
    pg.goto(BASE + "/programar", wait_until="networkidle"); pg.wait_for_timeout(800)
    if pg.locator("#lista button.item").count():
        pg.locator("#lista button.item").first.click()
        pg.fill("#macIn", "704BCA5B7701"); pg.wait_for_timeout(600)
        pg.click("button:has-text('Guardar MAC')"); pg.wait_for_timeout(200)
        d1 = pg.locator("button:has-text('Guardar MAC')").is_disabled()
        pg.keyboard.press("Enter") if False else None
        print("Programar: botón guardar deshabilitado mientras carga:", d1, "| PUT:", pg.evaluate("Object.entries(window.__n).filter(([k])=>k.startsWith('PUT'))"))
        pg.wait_for_timeout(3500)
    # Recibir: confirmar lote con doble clic
    pg.goto(BASE + "/", wait_until="networkidle")
    api(pg, "/api/pcb/manual", method="POST", headers={"Content-Type": "application/json"}, body=json.dumps({"tipo": "R1", "version": "30", "serie": "0702", "cantidad": 1}))
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(800)
    pg.click("#btnConfirm"); btn = pg.locator(".sheet .actions button:has-text('Confirmar lote')")
    btn.dblclick(); pg.wait_for_timeout(500)
    print("Confirmar: botón deshabilitado durante la petición:", btn.is_disabled(), "| POST:", pg.evaluate("window.__n['POST /api/recepcion/confirmar']"))
    pg.screenshot(path=str(SP / "rob_lento_confirmar.png"))
    pg.wait_for_timeout(3500)
    # Pruebas masivo: doble clic en aplicar
    pg.goto(BASE + "/pruebas", wait_until="networkidle"); pg.wait_for_timeout(800)
    pg.click("#segModo button[data-m='masivo']"); pg.fill("#ids", "0701"); pg.click(".btn-primary.btn-block"); pg.click(".btn-primary.btn-block"); pg.wait_for_timeout(500)
    print("Pruebas masivo: deshabilitado durante carga:", pg.locator(".btn-primary.btn-block").is_disabled(), "| POST:", pg.evaluate("window.__n['POST /api/pruebas/lote']"))
    br.close()


def sec_largo(p):
    print("== textos largos / hostiles")
    br, ctx, pg = nuevo(p, w=320, h=640); vg = Vigia(pg)
    largo = "A" * 400
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(800)
    pg.evaluate("([t]) => __showQR(t, true, 360)", ["TQT-R1-V30-0801 " + "X" * 150]); pg.wait_for_timeout(1500)
    print("QR con texto largo -> nombre:", pg.locator("#roName").inner_text()[:60], "|", pg.locator("#roMsg").inner_text())
    pg.evaluate("__clearQR()")
    pg.evaluate("([t]) => __showQR(t, true, 360)", ["<img src=x onerror=alert(1)>" + "Z" * 60]); pg.wait_for_timeout(1500)
    print("QR con HTML -> nombre:", pg.locator("#roName").inner_text()[:60], "|", pg.locator("#roMsg").inner_text())
    print("hscroll /:", pg.evaluate("document.documentElement.scrollWidth>innerWidth"))
    pg.screenshot(path=str(SP / "rob_largo_recibir.png"))
    pg.goto(BASE + "/emparejar", wait_until="networkidle"); pg.fill("#filtro", largo)
    pg.goto(BASE + "/programar", wait_until="networkidle"); pg.fill("#filtro", largo); print("programar filtro largo hscroll:", pg.evaluate("document.documentElement.scrollWidth>innerWidth"), "| lista:", pg.locator("#lista").inner_text().replace("\n", " ")[:60])
    pg.goto(BASE + "/pruebas", wait_until="networkidle"); pg.fill("#q", largo); pg.wait_for_timeout(600); print("pruebas q largo hscroll:", pg.evaluate("document.documentElement.scrollWidth>innerWidth"), "| res:", pg.locator(".empty").all_inner_texts())
    # falla con motivo largo vía API y verlo en monitor/admin
    print("consola:", vg.consola[:5])
    br.close()


def sec_recarga(p):
    print("== recarga en mitad de flujos / Atrás")
    br, ctx, pg = nuevo(p); vg = Vigia(pg)
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(800)
    pg.click("#btnManual"); pg.fill("#mnQty", "3"); pg.reload(wait_until="networkidle"); pg.wait_for_timeout(500)
    print("recarga con hoja 'Agregar sin QR' abierta -> hoja:", pg.locator(".sheet").count(), "| CTA:", pg.locator("#ctaCount").inner_text())
    pg.goto(BASE + "/programar", wait_until="networkidle"); pg.wait_for_timeout(600)
    if pg.locator("#lista button.item").count():
        pg.locator("#lista button.item").first.click(); pg.fill("#macIn", "704BCA5B88"); pg.reload(wait_until="networkidle"); pg.wait_for_timeout(600)
        print("programar recarga con MAC parcial -> campo:", pg.locator("#macIn").count(), "(el borrador se pierde:", pg.locator("#macIn").count() == 0, ")")
    pg.goto(BASE + "/pruebas", wait_until="networkidle"); pg.click("#segModo button[data-m='masivo']"); pg.reload(wait_until="networkidle"); pg.wait_for_timeout(600)
    print("pruebas modo persistido tras recarga:", pg.locator("#segModo button[aria-pressed=true]").inner_text())
    # Atrás
    pg.goto(BASE + "/", wait_until="networkidle"); pg.click(".tabbar a:has-text('Emparejar')"); pg.wait_for_load_state("networkidle")
    u1 = pg.url; pg.go_back(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(600)
    print("Atrás desde", u1, "->", pg.url, "| pestaña activa:", pg.locator(".tabbar a[aria-current=page]").inner_text(), "| conn:", pg.locator(".conn").inner_text())
    pg.click("#btnVersion"); print("hoja versión abierta:", pg.locator(".sheet").count()); pg.go_back(); pg.wait_for_timeout(600)
    print("Atrás con hoja abierta ->", pg.url, "(la hoja no tiene entrada de historial)")
    # visibilidad: pestaña oculta libera cámara
    br.close()


def sec_tema(p):
    print("== tema en caliente")
    br, ctx, pg = nuevo(p); vg = Vigia(pg)
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(600)
    bg0 = pg.evaluate("getComputedStyle(document.body).backgroundColor"); pg.screenshot(path=str(SP / "rob_tema_oscuro.png"))
    pg.click("button[aria-label*='tema']"); pg.wait_for_timeout(300)
    bg1 = pg.evaluate("getComputedStyle(document.body).backgroundColor"); pg.screenshot(path=str(SP / "rob_tema_claro.png"))
    print("body bg", bg0, "->", bg1, "| data-theme:", pg.evaluate("document.documentElement.dataset.theme"), "| meta theme-color:", pg.evaluate("document.querySelector('meta[name=theme-color]').content"))
    pg.evaluate("__showQR('TQT-R3-V30-0901', true)"); pg.wait_for_timeout(1200)
    pg.click("#btnManual"); pg.screenshot(path=str(SP / "rob_tema_claro_hoja.png")); pg.keyboard.press("Escape")
    pg.goto(BASE + "/monitor", wait_until="networkidle"); print("persiste en /monitor:", pg.evaluate("document.documentElement.dataset.theme"))
    br.close()
    # sin preferencia guardada, con el SO en claro
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844}, color_scheme="light")
    pg = ctx.new_page(); pg.goto(BASE + "/", wait_until="networkidle")
    print("sin preferencia guardada y SO claro -> data-theme:", pg.evaluate("document.documentElement.dataset.theme"), "(DISENO.md dice que respeta prefers-color-scheme)")
    br.close()


def sec_horizontal(p):
    print("== móvil horizontal 844x390")
    br, ctx = lanzar(p, viewport={"width": 844, "height": 390}, is_mobile=True, has_touch=True); ctx.add_init_script(CAM_JS)
    for ruta in ("/", "/emparejar", "/programar", "/pruebas"):
        pg = ctx.new_page(); pg.goto(BASE + ruta, wait_until="networkidle"); pg.wait_for_timeout(800)
        r = pg.evaluate("""() => { const cta = document.querySelector('.cta-bar'), tab = document.querySelector('.tabbar'), v = document.querySelector('.visor');
          const b = (e) => e ? (r => [Math.round(r.top), Math.round(r.bottom)])(e.getBoundingClientRect()) : null;
          return { hscroll: document.documentElement.scrollWidth > innerWidth, cta: b(cta), tab: b(tab), visor: b(v), H: innerHeight, mainScroll: document.documentElement.scrollHeight } }""")
        print(ruta, r); pg.screenshot(path=str(SP / f"rob_horizontal_{ruta.strip('/') or 'recibir'}.png")); pg.close()
    br.close()


SECS = {"caida": sec_caida, "http500": sec_http500, "lento": sec_lento, "largo": sec_largo, "recarga": sec_recarga, "tema": sec_tema, "horizontal": sec_horizontal}
if __name__ == "__main__":
    quiero = sys.argv[1:] or list(SECS)
    with sync_playwright() as p:
        for s in quiero:
            try:
                SECS[s](p)
            except Exception as e:
                print(f"ERROR en {s}: {type(e).__name__}: {str(e)[:400]}")
