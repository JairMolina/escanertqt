"""Estados vacíos (BD nueva) y volumen (300 PCB): mide tareas largas y tiempo de pintado en cada pantalla.
Uso: python volumen.py vacio | volumen   (vacio en servidor recién creado; volumen crea 300 PCB por API y 100 tarjetas)."""
import json, sys, time
from playwright.sync_api import sync_playwright
from util import *

SP = Path(os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots"))); SP.mkdir(parents=True, exist_ok=True)
RUTAS = ["/", "/emparejar", "/programar", "/pruebas", "/monitor", "/dymo", "/admin"]
LONG = "window.__lt=[];new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lt.push(Math.round(e.duration))}).observe({type:'longtask',buffered:true})"


def post(pg, path, body):
    return pg.evaluate("async ([p,b])=>{const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.status}", [path, body])


def vacio(p):
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844}); ctx.add_init_script(CAM_JS)
    for ruta in RUTAS:
        pg = ctx.new_page(); vg = Vigia(pg)
        pg.goto(BASE + ruta, wait_until="networkidle"); pg.wait_for_timeout(900)
        if ruta == "/admin":
            pg.fill("#pass", "ClaveQA-12345"); pg.click("#btnLogin"); pg.wait_for_timeout(1200)
        pg.screenshot(path=str(SP / f"vacio_{ruta.strip('/') or 'recibir'}.png"), full_page=True)
        print(ruta, "consola:", [c for c in vg.consola if 'ERR_CONNECTION_REFUSED' not in c[1]], "http:", vg.http, "| textos vacíos:", " / ".join(t.replace("\n", " ") for t in pg.locator(".empty").all_inner_texts())[:200])
        pg.close()
    br.close()


def volumen(p):
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844}); ctx.add_init_script(CAM_JS)
    pg = ctx.new_page(); pg.goto(BASE + "/", wait_until="networkidle")
    t0 = time.time()
    for t in ("R1", "R2", "R3"):
        for lote in range(1, 3):
            print("manual", t, post(pg, "/api/pcb/manual", {"tipo": t, "version": "30", "serie": f"{(lote-1)*50+1:04d}", "cantidad": 50}))
    print(f"creadas 300 PCB en {time.time()-t0:.1f} s")
    # Recibir con 300 en el borrador
    pg2 = ctx.new_page(); pg2.add_init_script(LONG)
    t0 = time.time(); pg2.goto(BASE + "/", wait_until="networkidle")
    pg2.wait_for_function("()=>document.getElementById('cT').textContent==='300'", timeout=15000)
    print(f"Recibir con 300 en borrador: listo en {(time.time()-t0)*1000:.0f} ms | filas={pg2.locator('#lista .item').count()} | tareas largas(ms)={pg2.evaluate('window.__lt')}")
    pg2.evaluate("__showQR('TQT-R1-V30-0999', true)"); t1 = time.time()
    pg2.wait_for_function("()=>document.getElementById('roMsg').textContent.startsWith('Registrada')", timeout=8000)
    print(f"  escaneo con 300 filas: {(time.time()-t1)*1000:.0f} ms hasta confirmación | tareas largas={pg2.evaluate('window.__lt')}")
    pg2.screenshot(path=str(SP / "vol_recibir_300.png"))
    pg2.click("#btnConfirm"); pg2.click(".sheet .actions button:has-text('Confirmar lote')"); pg2.wait_for_selector(".toast:has-text('confirmadas')")
    # Emparejar auto de 50+ series
    pg3 = ctx.new_page(); pg3.add_init_script(LONG)
    t0 = time.time(); pg3.goto(BASE + "/emparejar", wait_until="networkidle"); pg3.wait_for_timeout(500)
    print(f"Emparejar: comp={pg3.locator('#nComp').inner_text()} sueltas={pg3.locator('#nSue').inner_text()} listo en {(time.time()-t0)*1000:.0f} ms | tareas largas={pg3.evaluate('window.__lt')}")
    t0 = time.time(); pg3.click("#btnAuto"); pg3.wait_for_selector(".toast:has-text('creadas')", timeout=30000)
    print(f"  emparejar auto (50-100 tarjetas): {(time.time()-t0)*1000:.0f} ms | tarjetas={pg3.locator('#nTar').inner_text()}")
    pg3.wait_for_timeout(600); pg3.screenshot(path=str(SP / "vol_emparejar.png"))
    # Programar con muchas pendientes: teclear en filtro
    pg4 = ctx.new_page(); pg4.add_init_script(LONG)
    t0 = time.time(); pg4.goto(BASE + "/programar", wait_until="networkidle"); pg4.wait_for_timeout(500)
    print(f"Programar: pendientes={pg4.locator('#lista .item').count()} listo en {(time.time()-t0)*1000:.0f} ms | tareas largas={pg4.evaluate('window.__lt')}")
    t0 = time.time(); pg4.type("#filtro", "0042", delay=30); print(f"  filtro tecleado: {(time.time()-t0)*1000:.0f} ms, filas={pg4.locator('#lista .item').count()}")
    # Monitor inventario y tarjetas (1280)
    pg5 = ctx.new_page(); pg5.set_viewport_size({"width": 1280, "height": 800}); pg5.add_init_script(LONG)
    t0 = time.time(); pg5.goto(BASE + "/monitor", wait_until="networkidle"); pg5.wait_for_timeout(600)
    print(f"Monitor resumen listo en {(time.time()-t0)*1000:.0f} ms | KPI: {pg5.locator('#sec-resumen .esc-kpis').nth(1).inner_text()[:80]!r}")
    t0 = time.time(); pg5.evaluate("location.hash='#/inventario'"); pg5.wait_for_timeout(700)
    print(f"  inventario: filas={pg5.locator('#sec-inventario tbody tr').count()} en {(time.time()-t0)*1000:.0f} ms | tareas largas={pg5.evaluate('window.__lt')}")
    t0 = time.time(); pg5.fill("#invQ", "0042"); pg5.wait_for_timeout(400); print(f"  filtro inventario: {(time.time()-t0)*1000:.0f} ms filas={pg5.locator('#sec-inventario tbody tr').count()}")
    pg5.fill("#invQ", ""); pg5.wait_for_timeout(300)
    pg5.evaluate("location.hash='#/tarjetas'"); pg5.wait_for_timeout(700); print(f"  tarjetas: filas={pg5.locator('#sec-tarjetas tbody tr').count()} | tareas largas={pg5.evaluate('window.__lt')}")
    pg5.screenshot(path=str(SP / "vol_monitor.png"))
    # sincronizar Excel con ~100 tarjetas
    pg5.evaluate("location.hash='#/excel'"); pg5.wait_for_timeout(600)
    t0 = time.time(); pg5.click("#sec-excel button:has-text('Sincronizar Excel')"); pg5.wait_for_selector("#sec-excel .banner", timeout=90000)
    print(f"  sincronizar Excel: {(time.time()-t0)*1000:.0f} ms | banner: {pg5.locator('#sec-excel .banner').first.inner_text()[:200]!r}")
    # DYMO lote
    pg6 = ctx.new_page(); pg6.set_viewport_size({"width": 1280, "height": 800})
    t0 = time.time(); pg6.goto(BASE + "/dymo", wait_until="networkidle"); pg6.wait_for_timeout(800)
    print(f"DYMO con {pg6.locator('#selTarjeta option').count()} tarjetas: {(time.time()-t0)*1000:.0f} ms")
    br.close()


if __name__ == "__main__":
    with sync_playwright() as p:
        {"vacio": vacio, "volumen": volumen}[sys.argv[1]](p)
