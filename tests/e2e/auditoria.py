"""Auditoría de calidad del frontend en las 7 páginas x 5 tamaños x 2 temas (Chrome real).
Uso: TQT_AXE=<ruta a axe.min.js> TQT_SHOTS=<carpeta> python auditoria.py   (salida JSON en TQT_SHOTS/auditoria.json)
axe-core NO va en el repo: descárgalo aparte (npm i axe-core / cdn.jsdelivr.net/npm/axe-core/axe.min.js)."""
import json, re, sys, time
from playwright.sync_api import sync_playwright
from util import *

SP = Path(os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots")))
AXE = os.environ.get("TQT_AXE", "")
SP.mkdir(parents=True, exist_ok=True)
PAGINAS = [("/", "Recibir"), ("/emparejar", "Emparejar"), ("/programar", "Programar"), ("/pruebas", "Pruebas"),
           ("/monitor", None), ("/dymo", None), ("/admin", None)]
TAMANOS = [(320, 640), (360, 740), (390, 844), (768, 1024), (1280, 800)]
DYMO_LOCAL = re.compile(r":419\d\d/DYMO")

JS_CHECK = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !e.closest('[hidden]') && !e.closest('.sr-only'); };
  const desc = (e) => (e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '') +
    ' "' + ((e.getAttribute('aria-label') || e.textContent || e.value || '').trim().replace(/\s+/g, ' ').slice(0, 30)) + '"');
  const W = innerWidth;
  const out = { W, scrollW: document.documentElement.scrollWidth, bodyScrollW: document.body.scrollWidth };
  out.hscroll = out.scrollW > W + 1;
  out.small = []; out.offscreen = []; out.clipped = [];
  document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=tab]').forEach((e) => {
    if (!vis(e) || e.disabled && false) return;
    const r = e.getBoundingClientRect();
    if (Math.min(r.width, r.height) < 44 - 0.5) out.small.push(desc(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  });
  document.querySelectorAll('body *').forEach((e) => {
    if (!vis(e)) return;
    const r = e.getBoundingClientRect();
    let p = e.parentElement, inScroller = false;
    while (p) { const o = getComputedStyle(p).overflowX; if ((o === 'auto' || o === 'scroll') && p.scrollWidth > p.clientWidth) { inScroller = true; break; } p = p.parentElement; }
    if (!inScroller && (r.right > W + 1 || r.left < -1) && !e.closest('svg')) out.offscreen.push(desc(e) + ' [' + Math.round(r.left) + ',' + Math.round(r.right) + ']');
    const cs = getComputedStyle(e);
    if ((cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis') && e.scrollWidth > e.clientWidth + 1 && e.textContent.trim() && e.children.length < 3)
      out.clipped.push(desc(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  });
  out.lang = document.documentElement.lang; out.title = document.title;
  out.viewport = (document.querySelector('meta[name=viewport]') || {}).content || null;
  out.icon = !!document.querySelector('link[rel~=icon]'); out.manifest = !!document.querySelector('link[rel=manifest]');
  out.h1 = document.querySelectorAll('h1').length;
  const cur = document.querySelector('.tabbar a[aria-current=page]');
  out.tabActive = cur ? cur.textContent.trim() : null; out.tabs = document.querySelectorAll('.tabbar a').length;
  out.unlabeled = [...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter((e) => vis(e) && !e.labels.length && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby')).map(desc);
  out.noNameBtn = [...document.querySelectorAll('button,a[href]')].filter((e) => vis(e) && !(e.getAttribute('aria-label') || e.textContent.trim() || e.title)).map(desc);
  out.links = [...new Set([...document.querySelectorAll('a[href]')].map((a) => a.getAttribute('href')).filter((h) => h && !h.startsWith('#') && !h.startsWith('javascript')))];
  out.live = [...document.querySelectorAll('[aria-live],[role=status],[role=alert]')].map((e) => e.id || e.className);
  return out;
}
"""

JS_TAB = r"""
async (n) => {
  const seq = [];
  document.activeElement && document.activeElement.blur();
  return seq;
}
"""


def foco(page, n=24):
    """Tabula n veces y mide si el elemento enfocado muestra indicador (outline o box-shadow) y el orden vertical."""
    res, prev_y, saltos = [], -1, []
    for i in range(n):
        page.keyboard.press("Tab")
        info = page.evaluate("""() => { const e = document.activeElement; if (!e || e === document.body) return null;
          const cs = getComputedStyle(e), r = e.getBoundingClientRect();
          return { d: e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + ' "' + (e.getAttribute('aria-label') || e.textContent || e.value || '').trim().slice(0, 24) + '"',
                   ol: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0, sh: cs.boxShadow !== 'none', y: Math.round(r.top + scrollY), x: Math.round(r.left), inView: r.bottom > 0 && r.top < innerHeight } }""")
        if not info:
            continue
        res.append(info)
        if prev_y >= 0 and info["y"] < prev_y - 120:
            saltos.append(f"{res[-2]['d']} (y{prev_y}) -> {info['d']} (y{info['y']})")
        prev_y = info["y"]
    sin_indicador = [r["d"] for r in res if not (r["ol"] or r["sh"])]
    return {"n": len(res), "sinIndicador": sin_indicador, "saltosArriba": saltos, "orden": [r["d"] for r in res]}


def main():
    out = {}
    with sync_playwright() as p:
        br, _ = lanzar(p)
        for tema in ("dark", "light"):
            for (w, h) in TAMANOS:
                ctx = br.new_context(ignore_https_errors=True, viewport={"width": w, "height": h}, color_scheme=tema, permissions=["camera"],
                                     has_touch=w < 900, is_mobile=w < 700)
                ctx.add_init_script(f"try{{localStorage.setItem('tqt.tema','{tema}')}}catch(e){{}}")
                ctx.add_init_script(CAM_JS)
                for ruta, _n in PAGINAS:
                    key = f"{ruta}|{w}x{h}|{tema}"
                    pg = ctx.new_page(); vg = Vigia(pg)
                    pg.goto(BASE + ruta, wait_until="networkidle")
                    time.sleep(0.9)
                    r = pg.evaluate(JS_CHECK)
                    slug = (ruta.strip("/") or "recibir")
                    pg.screenshot(path=str(SP / f"aud_{slug}_{w}_{tema}.png"), full_page=False)
                    r["consola"] = [c for c in vg.consola if not (ruta == "/dymo" and "ERR_CONNECTION_REFUSED" in c[1])]
                    r["http"] = vg.http
                    r["fallos"] = [f for f in vg.fallos if not DYMO_LOCAL.search(f[0])]
                    r["externas"] = [u for u in vg.externas if not DYMO_LOCAL.search(u)]
                    r["dymoLocal"] = len([u for u in vg.externas if DYMO_LOCAL.search(u)])
                    if AXE and w in (320, 390, 1280):
                        pg.add_script_tag(path=AXE)
                        ax = pg.evaluate("async () => (await axe.run(document, { resultTypes: ['violations'] })).violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, help: v.help, ej: v.nodes.slice(0, 3).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\\n').slice(1, 3).join(' '))}))")
                        r["axe"] = [a for a in ax]
                    if (w, tema) in ((390, "dark"), (1280, "light")):
                        r["foco"] = foco(pg)
                    out[key] = r
                    print(key, "hscroll" if r["hscroll"] else "", "small=%d" % len(r["small"]), "off=%d" % len(r["offscreen"]), "clip=%d" % len(r["clipped"]),
                          "axe=%s" % ([(a["id"], a["impact"], a["n"]) for a in r.get("axe", [])]), flush=True)
                    pg.close()
                ctx.close()
        # reduced motion
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 390, "height": 844}, reduced_motion="reduce", permissions=["camera"])
        ctx.add_init_script(CAM_JS)
        pg = ctx.new_page(); pg.goto(BASE + "/", wait_until="networkidle"); time.sleep(0.8)
        pg.evaluate("__showQR('TQT-R1-V30-0777', true)"); time.sleep(1.5)
        out["reducedMotion"] = pg.evaluate("() => document.getAnimations().map(a => (a.animationName || a.transitionProperty || '?') + ':' + (a.effect ? a.effect.getComputedTiming().iterations : '?') + ':' + a.playState)")
        br.close()
    (SP / "auditoria.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
