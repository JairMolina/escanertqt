"""Latencia del escaneo (QR en fotograma -> sonido/confirmación visual -> confirmación del servidor) y carga de páginas.
Uso: python latencia.py [N=30]. Requiere el servidor aislado en TQT_BASE. Cámara: canvas.captureStream (ver util.CAM_JS)."""
import json, statistics, sys, time
from playwright.sync_api import sync_playwright
from util import *

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
PAGES = ["/", "/emparejar", "/programar", "/pruebas", "/monitor", "/dymo", "/admin"]
WRAP = """() => {
  window.__t = { sound: [], vis: [], srv: [] };
  const ps = window.SoundFX.playScan.bind(window.SoundFX);
  window.SoundFX.playScan = (t) => { window.__t.sound.push(performance.now()); return ps(t); };
  new MutationObserver(() => {
    const m = document.getElementById('roMsg').textContent;
    const now = performance.now();
    if (m.startsWith('Leída')) window.__t.vis.push(now);
    if (m.startsWith('Registrada')) window.__t.srv.push(now);
  }).observe(document.getElementById('readout'), { subtree: true, childList: true, characterData: true });
}"""


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def resumen(nombre, v):
    if not v:
        return f"{nombre}: sin datos"
    return f"{nombre}: P50={statistics.median(v):.0f} ms  P95={pct(v, .95):.0f} ms  max={max(v):.0f} ms  (n={len(v)})"


def latencia(p, size=320, inv=True, base=3000, label=""):
    br, ctx = lanzar(p, viewport={"width": 1280, "height": 800})
    ctx.add_init_script(CAM_JS)
    pg = ctx.new_page()
    pg.goto(BASE + "/", wait_until="networkidle"); time.sleep(1.0)
    pg.evaluate(WRAP)
    snd, vis, srv, perdidas = [], [], [], 0
    for i in range(N):
        code = f"TQT-R1-V30-{base + i:04d}"
        pg.evaluate("() => { window.__t.sound.length = window.__t.vis.length = window.__t.srv.length = 0 }")
        pg.evaluate("([c, inv, s]) => __showQR(c, inv, s)", [code, inv, size])
        try:
            pg.wait_for_function("() => window.__t.srv.length > 0", timeout=4000)
        except Exception:
            perdidas += 1
            pg.evaluate("__clearQR()"); time.sleep(0.5); continue
        t0 = pg.evaluate("window.__cam.shownAt")
        t = pg.evaluate("window.__t")
        snd.append(t["sound"][0] - t0); vis.append(t["vis"][0] - t0); srv.append(t["srv"][0] - t0)
        pg.evaluate("__clearQR()"); time.sleep(0.35)
    br.close()
    print(f"--- {label} (QR {size}px de 640x480, {'invertido' if inv else 'normal'}), {N} lecturas, perdidas={perdidas}")
    print(" ", resumen("sonido (playScan)", snd)); print(" ", resumen("confirmación visual", vis)); print(" ", resumen("confirmación servidor", srv))
    return {"sonido": snd, "visual": vis, "servidor": srv, "perdidas": perdidas}


def carga(p):
    br = p.chromium.launch(channel="chrome", args=["--ignore-certificate-errors"])
    res = {}
    for ruta in PAGES:
        for viewport in ({"width": 390, "height": 844},):
            ctx = br.new_context(ignore_https_errors=True, viewport=viewport)
            pg = ctx.new_page()
            cdp = ctx.new_cdp_session(pg)
            cdp.send("Network.enable"); cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
            tot, items = [0], []
            cdp.on("Network.loadingFinished", lambda e: tot.__setitem__(0, tot[0] + e["encodedDataLength"]))
            pg.add_init_script("window.__fcp=0;new PerformanceObserver(l=>{for(const e of l.getEntries())if(e.name==='first-contentful-paint')window.__fcp=e.startTime}).observe({type:'paint',buffered:true})")
            t0 = time.time()
            pg.goto(BASE + ruta, wait_until="networkidle"); time.sleep(0.5)
            nav = pg.evaluate("() => { const n = performance.getEntriesByType('navigation')[0]; return { dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, fcp: window.__fcp, res: performance.getEntriesByType('resource').map(r => [r.name.replace(location.origin, ''), Math.round(r.transferSize / 1024 * 10) / 10]) } }")
            bloq = pg.evaluate("() => [...document.querySelectorAll('head script[src]:not([async]):not([defer])')].map(s => s.src)")
            hoja = pg.evaluate("() => [...document.querySelectorAll('link[rel=stylesheet]')].length")
            res[ruta] = {"kb": round(tot[0] / 1024, 1), "dcl": round(nav["dcl"]), "load": round(nav["load"]), "fcp": round(nav["fcp"]), "nreq": len(nav["res"]), "bloqueantesHead": bloq, "css": hoja,
                         "grandes": sorted(nav["res"], key=lambda x: -x[1])[:3]}
            print(f"{ruta:11} {res[ruta]['kb']:8.1f} KB  reqs={len(nav['res']):2}  FCP={nav['fcp']:.0f} ms  DCL={nav['dcl']:.0f} ms  load={nav['load']:.0f} ms  script bloqueante en head={len(bloq)}  top={res[ruta]['grandes']}")
            ctx.close()
    br.close()
    return res


if __name__ == "__main__":
    with sync_playwright() as p:
        out = {}
        out["carga"] = carga(p)
        out["lat_320_inv"] = latencia(p, 320, True, 3000, "escritorio")
        out["lat_180_inv"] = latencia(p, 180, True, 3100, "QR pequeño")
        out["lat_320_norm"] = latencia(p, 320, False, 3200, "QR normal (no invertido)")
    Path(os.environ.get("TQT_SHOTS", ".")).joinpath("latencia.json").write_text(json.dumps(out), encoding="utf-8")
