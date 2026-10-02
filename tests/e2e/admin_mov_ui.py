"""QA pestaña Movimientos de /admin (Chrome real). Siembra por API y comprueba filtros, paginación, anchos, temas, axe y consola.
TQT_BASE=https://127.0.0.1:8463 TQT_ADMIN_PASSWORD=ClaveQA-12345 TQT_AXE=<ruta a axe.min.js> python admin_mov_ui.py"""
import os, re
from playwright.sync_api import sync_playwright
from util import *
from admin_mov_seed import sembrar

PW = os.environ.get("TQT_ADMIN_PASSWORD", "ClaveQA-12345")
AXE = open(os.environ["TQT_AXE"], encoding="utf-8").read()
IMG = RAIZ / "docs" / "qa" / "admin_mov_img"; IMG.mkdir(parents=True, exist_ok=True)
RUN = "async () => (await axe.run(document, { resultTypes: ['violations'] })).violations.map(v => v.id + ' [' + v.impact + '] x' + v.nodes.length + ' :: ' + v.nodes.slice(0, 2).map(n => n.target.join(' ')).join(' | '))"
res = []
def chk(n, ok, extra=""):
    res.append(bool(ok)); print(("OK   " if ok else "FALLA"), n, extra)

sem = sembrar(BASE)
print("sembrado:", sem["total"], sem["conteo"])

def filas(pg):  # filas visibles (tabla en escritorio, tarjetas en móvil)
    return pg.evaluate("()=>{const t=document.querySelector('.mv-table-wrap');const vis=t&&t.offsetParent!==null;return vis?document.querySelectorAll('.mv-table tbody tr').length:document.querySelectorAll('.mv-card').length}")

def estado(pg): return pg.inner_text("#mEstado").strip()
def espera(pg): pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(500)

def entrar(pg):
    pg.goto(BASE + "/admin", wait_until="networkidle"); pg.fill("#pass", PW); pg.press("#pass", "Enter")
    pg.wait_for_selector("#adminView:not([hidden])", timeout=8000); espera(pg)

def sin_scroll(pg): return pg.evaluate("()=>document.documentElement.scrollWidth<=window.innerWidth")

with sync_playwright() as p:
    br, ctx = lanzar(p, viewport={"width": 1280, "height": 800})
    pg = ctx.new_page(); vg = Vigia(pg)
    entrar(pg)
    # ---- Resumen
    pg.wait_for_selector(".mv-resumen-lista li", timeout=5000)
    txt = pg.inner_text("#v-resumen")
    chk("resumen: 'Últimos movimientos' con 5 filas", "últimos movimientos" in txt.lower() and pg.locator(".mv-resumen-lista li").count() == 5)
    chk("resumen: KPI 'Movimientos registrados' presente", "movimientos registrados" in pg.inner_text(".kpis").lower())
    pg.screenshot(path=str(IMG / "resumen_1280.png"), full_page=True)
    pg.click("#verMov"); espera(pg)
    chk("'Ver movimientos' abre la pestaña", pg.is_visible("#v-movimientos") and pg.get_attribute("[data-v=movimientos]", "aria-selected") == "true")
    # ---- Movimientos: estado inicial
    chk("línea explicativa", "No se borra con «Borrar TODO»" in pg.inner_text("#v-movimientos"))
    chips = pg.evaluate("()=>[...document.querySelectorAll('.mv-cat')].map(b=>b.innerText.replace(/\\s+/g,' '))")
    print("chips:", chips)
    chk("chips: Todos + 6 categorías con contador", len(chips) == 7 and chips[0].startswith("Todos") and chips[1].startswith("Altas"), str(chips))
    api = pg.evaluate("async()=>{const t=JSON.parse(sessionStorage.getItem('tqt.admin')).t;return (await fetch('/api/admin/movimientos?limite=1',{headers:{'X-Admin-Token':t}})).json()}")
    chk("chip Todos = suma de conteo", chips[0].endswith(str(sum(api["conteo"].values()))), chips[0])
    chk("primera página: 50 filas y 'N de total'", filas(pg) == 50 and re.match(r"50 de \d+ movimientos", estado(pg)), estado(pg))
    tit = pg.inner_text(".mv-table tbody tr:first-child").replace("\n", " | "); print("primera fila:", tit)
    chk("fecha legible (hoy hh:mm)", re.search(r"hoy \d\d:\d\d", tit) is not None, tit)
    chk("insignia con texto (no solo color)", pg.locator(".mv-table tbody tr:first-child .badge").inner_text().strip() != "")
    pg.screenshot(path=str(IMG / "movimientos_1280_claro_o_oscuro.png"), full_page=True)
    # ---- paginación
    total = int(re.search(r"de (\d+)", estado(pg)).group(1)); pg.click("#mMas"); espera(pg)
    chk("cargar más: 100 filas", filas(pg) == 100, estado(pg))
    pg.click("#mMas"); espera(pg)
    chk("cargar más otra vez: 150 o total", filas(pg) == min(150, total), estado(pg))
    while pg.is_visible("#mMas"): pg.click("#mMas"); espera(pg)
    chk("al terminar: todas cargadas y 'Cargar más' oculto", filas(pg) == total and not pg.is_visible("#mMas") and estado(pg).startswith(f"{total} de {total}"), estado(pg))
    ids = pg.evaluate("()=>[...document.querySelectorAll('.mv-table tbody tr')].length")
    # ---- categorías
    for cat, nombre in (("eliminacion", "Eliminaciones"), ("edicion", "Ediciones"), ("alta", "Altas"), ("sesion", "Sesiones"), ("excel", "Excel")):
        pg.click(f".mv-cat[data-cat={cat}]"); espera(pg)
        n = api["conteo"][cat] if False else None
        cats = pg.evaluate("()=>[...document.querySelectorAll('.mv-table tbody tr')].map(r=>r.dataset.cat)")
        chk(f"categoría {nombre}: todas las filas son {cat}", len(cats) > 0 and set(cats) == {cat}, f"{len(cats)} filas")
        chk(f"categoría {nombre}: chip presionado", pg.get_attribute(f".mv-cat[data-cat={cat}]", "aria-pressed") == "true")
    pg.click(".mv-cat[data-cat=eliminacion]"); espera(pg)
    e = pg.inner_text("#v-movimientos")
    chk("eliminaciones: título y detalle legibles", "Placa eliminada" in e and "Tarjetas borradas (admin)" in e and "Tarjeta disuelta" in e)
    pg.screenshot(path=str(IMG / "eliminaciones_1280.png"), full_page=True)
    # ---- búsqueda (caracteres especiales) y sin resultados
    pg.click(".mv-cat[data-cat='']"); espera(pg)
    for q, esperado in (("70:4B:CA:5B:01:01", True), ("Carla", True), ("%", False), ("_", True), ("!", False), ("<img src=x onerror=alert(1)>", False)):
        pg.fill("#mQ", q); pg.wait_for_timeout(700); espera(pg); n = filas(pg)
        chk(f"buscar {q!r}: {'con' if esperado else 'sin'} resultados y sin romper", (n > 0) == esperado and not pg.is_visible("#v-movimientos .banner[data-k=bad]"), f"{n} filas; {estado(pg)}")
    chk("sin resultados: estado vacío con el texto pedido", "Todavía no hay movimientos con esos filtros" in pg.inner_text("#mLista"))
    chk("nada del servidor/entrada se inyectó como HTML", pg.evaluate("document.querySelectorAll('#mLista img').length") == 0)
    pg.screenshot(path=str(IMG / "vacio_1280.png"))
    pg.click("#mLimpiar"); espera(pg); chk("quitar filtros restablece", filas(pg) == 50 and pg.input_value("#mQ") == "")
    # ---- fechas y lote
    hoy = pg.evaluate("new Date().toISOString().slice(0,10)")
    pg.fill("#mDesde", "2030-01-01"); espera(pg); chk("desde futuro: vacío", filas(pg) == 0 and "Todavía no hay movimientos" in pg.inner_text("#mLista"))
    pg.fill("#mDesde", hoy); espera(pg); chk("desde hoy: hay movimientos", filas(pg) > 0)
    pg.fill("#mHasta", "2020-01-01"); espera(pg); chk("desde > hasta: aviso claro, sin llamar a la API", "posterior a «Hasta»" in pg.inner_text("#mLista"))
    pg.click("#mLimpiar"); espera(pg)
    pg.select_option("#mLote", str(sem["lote"]["id"])); espera(pg); chk("filtro por lote", filas(pg) > 0 and int(re.search(r"de (\d+)", estado(pg)).group(1)) < total, estado(pg))
    pg.click("#mLimpiar"); espera(pg)
    # ---- actualizar y CSV
    pg.click("#mAct"); espera(pg); chk("actualizar mantiene la lista", filas(pg) == 50)
    pg.click(".mv-cat[data-cat=eliminacion]"); espera(pg)
    with pg.expect_download() as d: pg.click("#mCsv")
    ruta = d.value.path(); csv = open(ruta, encoding="utf-8-sig").read().splitlines()
    chk("CSV: cabecera y una fila por movimiento filtrado", csv[0].startswith('"Fecha","Tipo"') and len(csv) - 1 == int(re.search(r"de (\d+)", estado(pg)).group(1)), f"{len(csv) - 1} filas")
    pg.click("#mLimpiar"); espera(pg)
    # ---- WebSocket/otros: eliminar algo en admin y ver el movimiento nuevo sin recargar
    antes = int(re.search(r"de (\d+)", estado(pg)).group(1))
    pg.evaluate("async()=>{await fetch('/api/pcb/manual',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tipo:'R3',version:'30',serie:'0090',cantidad:1,operador:'Zoe'})})}")
    pg.click("#mAct"); espera(pg); chk("actualizar trae el movimiento nuevo", int(re.search(r"de (\d+)", estado(pg)).group(1)) == antes + 1 and "Zoe" in pg.inner_text(".mv-table tbody tr:first-child"))
    # ---- 'Borrar TODO' no borra movimientos
    pg.click("[data-v=riesgo]"); chk("texto de Borrar TODO conserva movimientos", "Se conservan los lotes, la contraseña y los movimientos" in pg.inner_text("#v-riesgo"))
    # ---- anchos y temas
    for w, h_ in ((1280, 800), (390, 844), (320, 700)):
        pg.set_viewport_size({"width": w, "height": h_})
        for tema in ("dark", "light"):
            pg.evaluate("t=>{document.documentElement.dataset.theme=t}", tema)
            pg.click("[data-v=movimientos]"); espera(pg)
            chk(f"{w}px {tema}: sin scroll horizontal", sin_scroll(pg))
            nav = pg.evaluate("()=>{const t=document.querySelector('.mv-table-wrap');return t&&t.offsetParent!==null?'tabla':'tarjetas'}")
            chk(f"{w}px {tema}: {'tabla' if w > 700 else 'tarjetas'} apiladas", nav == ("tabla" if w > 700 else "tarjetas"))
            pg.evaluate(AXE) if not pg.evaluate("typeof axe!=='undefined'") else None
            viol = pg.evaluate(RUN); chk(f"{w}px {tema} axe Movimientos: 0 violaciones", not viol, str(viol)[:300])
            if tema == "dark": pg.screenshot(path=str(IMG / f"movimientos_{w}_{tema}.png"), full_page=(w != 1280))
            else: pg.screenshot(path=str(IMG / f"movimientos_{w}_{tema}.png"))
            pg.click("[data-v=resumen]"); espera(pg)
            viol = pg.evaluate(RUN); chk(f"{w}px {tema} axe Resumen: 0 violaciones", not viol, str(viol)[:300])
    # ---- login + cerrada con axe
    pg.set_viewport_size({"width": 390, "height": 844}); pg.evaluate("t=>{document.documentElement.dataset.theme=t}", "dark")
    pg.click("#btnLogout"); pg.wait_for_timeout(600)
    viol = pg.evaluate(RUN); chk("axe 'Sesión cerrada': 0 violaciones", not viol, str(viol)[:300]); pg.screenshot(path=str(IMG / "sesion_cerrada_390.png"))
    pg.click("#cerradaVolver"); viol = pg.evaluate(RUN); chk("axe login: 0 violaciones", not viol, str(viol)[:300])
    print("consola:", vg.consola, "http:", vg.http, "externas:", vg.externas)
    chk("consola sin errores (los 401 provocados no cuentan)", not [c for c in vg.consola if "401" not in c[1]])
    br.close()
print(f"{sum(res)}/{len(res)} OK")
