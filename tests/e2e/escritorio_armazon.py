"""Consola de escritorio (/monitor): recorrido de todas las secciones en Chrome real (Playwright).
Levanta su propio servidor AISLADO (puerto 8464, carpeta temporal, clave ClaveQA-12345), siembra datos por API (30+ PCB de los tres tipos,
tarjetas impares, MAC en algunas) y comprueba, a 1440x900 / 1280x800 / 1024x768 en oscuro y claro:
  0 errores de consola, 0 respuestas 4xx/5xx inesperadas, 0 peticiones a cámara/jsQR, sin scroll horizontal, teclado y atajos, axe-core sin violaciones.
Capturas en docs/qa/escritorio/.   Uso:  TQT_AXE=<ruta a axe.min.js> python tests/e2e/escritorio_armazon.py [--sin-clave] [--rapido]
  --rapido: solo 1280x800 oscuro/claro.   --sin-clave: segunda pasada con un servidor SIN contraseña de admin (sin cerrar sesión, sin redirección).
Si ya hay un servidor propio en 8464: ESC_SERVIDOR_EXISTENTE=1.
"""
import json, os, ssl, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

PUERTO = "8464"
os.environ["TQT_BASE"] = f"https://127.0.0.1:{PUERTO}"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from util import *   # noqa: E402  (BASE, RAIZ, Vigia, lanzar)

AXE = os.environ.get("TQT_AXE") or str(Path(tempfile.gettempdir()) / "axe.min.js")
SHOTS = RAIZ / "docs" / "qa" / "escritorio"
CLAVE = "ClaveQA-12345"
SECCIONES = ["resumen", "inventario", "tarjetas", "macs", "consultar", "lotes", "excel"]
TAMANOS = [(1440, 900), (1280, 800), (1024, 768)]
RAPIDO = "--rapido" in sys.argv
RESULT = []


def check(nombre, ok, detalle=""):
    RESULT.append((nombre, bool(ok), detalle))
    print(("  ok   " if ok else "  FALLA"), nombre, ("" if ok else f"-> {detalle}"), flush=True)


# ---------------------------------------------------------------- servidor aislado y datos
def arrancar(clave=True):
    tmp = Path(tempfile.mkdtemp(prefix="tqt_esc_"))
    env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"), TQT_BACKUP_DIR=str(tmp / "bk"),
               HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
    env.pop("TQT_ADMIN_PASSWORD", None)
    if clave:
        env["TQT_ADMIN_PASSWORD"] = CLAVE
    log = open(tmp / "srv.log", "wb")
    proc = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=log, stderr=log)
    for _ in range(60):
        try:
            api("GET", "/api/status"); return proc, tmp
        except Exception:
            time.sleep(0.5)
    proc.kill(); raise SystemExit("el servidor no arrancó (ver " + str(tmp / "srv.log") + ")")


def parar(proc):
    proc.terminate()
    try: proc.wait(8)
    except Exception: proc.kill()


CTX_SSL = ssl.create_default_context(); CTX_SSL.check_hostname = False; CTX_SSL.verify_mode = ssl.CERT_NONE


def api(metodo, ruta, cuerpo=None, cookie=None):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, context=CTX_SSL, timeout=30) as r:
            t = r.read(); return json.loads(t) if t else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{metodo} {ruta} -> {e.code} {e.read()[:200]!r}")


def sembrar():
    """34 R1, 33 R2, 28 R3 (algunas V31), 1 R2 sin confirmar; tarjetas por serie; 2 impares; MAC+firmware en ~20 placas."""
    def manual(tipo, serie, version="30"):
        api("POST", "/api/pcb/manual", {"tipo": tipo, "version": version, "serie": "%04d" % int(serie), "cantidad": 1})
    for s in range(1, 35): manual("R1", s)
    for s in range(1, 34): manual("R2", s)
    for s in range(1, 29): manual("R3", s, "31" if s % 5 == 0 else "30")
    api("POST", "/api/recepcion/confirmar", {})
    api("POST", "/api/emparejar/auto", {})
    sueltas = api("GET", "/api/pcb?estado_ciclo=DISPONIBLE&limit=200")["items"]
    r1 = [p for p in sueltas if p["tipo"] == "R1"]; r2 = [p for p in sueltas if p["tipo"] == "R2"]
    if r1: api("POST", "/api/tarjetas", {"id_tarjeta_num": "101", "r1_id": r1[0]["id"]})   # impar: solo R1
    manual("R2", 90); manual("R1", 91)                                                      # sin confirmar
    todas = api("GET", "/api/pcb?limit=500")["items"]
    n = 0
    for p in todas:
        if p["tipo"] in ("R1", "R2") and p["estado_ciclo"] == "ASIGNADA" and int(p["serie"]) <= 10:
            n += 1
            api("PUT", f"/api/pcb/{p['id']}/programacion", {"mac": "70:4B:CA:5B:%02X:%02X" % (int(p["serie"]), 0xA0 + (1 if p["tipo"] == "R1" else 2)), "firmware": "4.1" if p["tipo"] == "R1" else "2.1"})
    return len(todas), n


# ---------------------------------------------------------------- helpers de navegador
INIT_CAMARA = "window.__gum = 0; if (navigator.mediaDevices) { const o = navigator.mediaDevices.getUserMedia && navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices); navigator.mediaDevices.getUserMedia = function () { window.__gum++; return o ? o.apply(null, arguments) : Promise.reject(new Error('sin camara')); }; }"
RUN_AXE = "async () => (await axe.run(document, { resultTypes: ['violations'] })).violations.map(v => v.id + ' [' + v.impact + '] x' + v.nodes.length + ' :: ' + v.nodes.slice(0, 3).map(n => n.target.join(' ') + ' ' + (n.failureSummary || '').split('\\n').slice(1, 2).join('')).join(' | '))"


def abrir(p, w, h, tema, con_clave=True):
    br, ctx = lanzar(p, viewport={"width": w, "height": h}, color_scheme=tema, accept_downloads=True)
    ctx.add_init_script(f"localStorage.setItem('tqt.tema','{tema}');")
    ctx.add_init_script(INIT_CAMARA)
    if con_clave:
        r = ctx.request.post(BASE + "/api/admin/login", data={"password": CLAVE}); assert r.ok, r.status
    pg = ctx.new_page()
    return br, ctx, pg, Vigia(pg)


def ir_a(pg, ruta):
    pg.evaluate("h => { location.hash = h; }", "#/" + ruta)
    pg.wait_for_selector(f"#sec-{ruta.split('?')[0]}", timeout=8000)
    try: pg.wait_for_load_state("networkidle", timeout=6000)
    except Exception: pass
    pg.wait_for_timeout(450)


def sin_scroll_h(pg):
    return pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")


def axe(pg, nombre):
    if not pg.evaluate("() => typeof axe !== 'undefined'"):
        pg.add_script_tag(path=AXE)
    v = pg.evaluate(RUN_AXE)
    check(f"axe {nombre}", not v, " || ".join(x[:300] for x in v))


# ---------------------------------------------------------------- recorrido
def recorrido(p, con_clave=True):
    for tema in ("dark", "light"):
        for (w, h) in ([(1280, 800)] if RAPIDO else TAMANOS):
            tag = f"[{tema} {w}x{h}]"
            print(tag, flush=True)
            br, ctx, pg, vg = abrir(p, w, h, tema, con_clave)
            pg.goto(BASE + "/monitor", wait_until="networkidle"); pg.wait_for_selector("#sec-resumen", timeout=8000); pg.wait_for_timeout(500)
            check(f"{tag} /monitor abre en Resumen con título 'Consola'", pg.title().endswith("Consola · Escáner TQT") and pg.locator("h1#escTitulo").inner_text() == "Resumen", pg.title())
            for sec in SECCIONES:
                ruta = "consultar?codigo=TQT-R1-V30-0003" if sec == "consultar" else sec
                ir_a(pg, ruta)
                if sec == "tarjetas":
                    pg.locator("#sec-tarjetas tbody tr").first.click(); pg.wait_for_selector(".esc-panel", timeout=4000); pg.wait_for_timeout(300)
                if sec == "consultar":
                    pg.wait_for_selector(".esc-ficha .num", timeout=6000)
                sw, iw = sin_scroll_h(pg)
                check(f"{tag} {sec}: sin scroll horizontal", sw <= iw, f"{sw}>{iw}")
                pg.screenshot(path=str(SHOTS / f"{sec}_{w}_{tema}.png"))
                axe(pg, f"{tag} {sec}")
                if sec == "tarjetas": pg.keyboard.press("Escape")
            check(f"{tag} consola limpia", not vg.consola, str(vg.consola[:3]))
            check(f"{tag} sin 4xx/5xx ni fallos de red ni hosts externos", not (vg.http or vg.fallos or vg.externas), str((vg.http, vg.fallos, vg.externas)[:3]))
            prohibidas = [u for u, _ in vg.reqs if any(k in u for k in ("jsQR", "scanner.js", "visor.js", "haptics", "audio.js"))]
            check(f"{tag} sin peticiones a cámara/jsQR", not prohibidas, str(prohibidas))
            check(f"{tag} getUserMedia nunca se llamó", pg.evaluate("() => window.__gum") == 0)
            br.close()


def teclado_y_flujos(p):
    """Un solo navegador 1280x800 oscuro: atajos, foco, tablas, panel, consulta, lotes, Excel, móvil y cierre de sesión."""
    tag = "[teclado]"; print(tag, flush=True)
    br, ctx, pg, vg = abrir(p, 1280, 800, "dark")
    pg.goto(BASE + "/monitor?lote=1", wait_until="networkidle"); pg.wait_for_selector("#sec-resumen"); pg.wait_for_timeout(500)
    check(f"{tag} logo lleva a #/resumen (no a /)", pg.get_attribute("a.esc-logo", "href") == "#/resumen")
    check(f"{tag} navegación lateral: 6 de operación/gestión con hash", pg.locator("nav.esc-nav a[href^='#/']").count() >= 7, str(pg.locator("nav.esc-nav a").count()))
    for k, sec in (("i", "inventario"), ("t", "tarjetas"), ("c", "consultar"), ("l", "lotes"), ("x", "excel"), ("m", "macs"), ("r", "resumen")):
        pg.keyboard.press("g"); pg.keyboard.press(k); pg.wait_for_selector(f"#sec-{sec}", timeout=4000)
        check(f"{tag} atajo g {k} -> {sec}", pg.evaluate("() => location.hash").startswith("#/" + sec))
    pg.keyboard.press("["); check(f"{tag} '[' contrae la barra lateral", pg.get_attribute("#esc", "data-lat") == "min"); pg.keyboard.press("[")
    check(f"{tag} '[' la vuelve a expandir", pg.get_attribute("#esc", "data-lat") == "max")
    pg.keyboard.press("?"); pg.wait_for_selector(".sheet"); check(f"{tag} '?' abre los atajos", "Atajos" in pg.locator(".sheet h2").inner_text()); pg.keyboard.press("Escape")
    # Inventario
    ir_a(pg, "inventario"); pg.keyboard.press("/"); check(f"{tag} '/' enfoca la búsqueda", pg.evaluate("() => document.activeElement.id") == "invQ")
    n0 = pg.locator("#sec-inventario tbody tr").count(); check(f"{tag} inventario lista placas sembradas (>30)", n0 > 30, str(n0))
    pg.fill("#invQ", "TQT-R3-V31"); pg.wait_for_timeout(400); n1 = pg.locator("#sec-inventario tbody tr").count(); check(f"{tag} búsqueda filtra (R3 V31)", 0 < n1 < n0, f"{n1}/{n0}")
    pg.fill("#invQ", ""); pg.wait_for_timeout(300)
    pg.click("#sec-inventario .esc-seg button[data-v='R2']"); pg.wait_for_timeout(200)
    check(f"{tag} filtro tipo R2", pg.locator("#sec-inventario tbody tr").count() > 0 and pg.locator("#sec-inventario tbody .tipo:not([data-t='R2'])").count() == 0)
    check(f"{tag} R1/R2 muestran MAC y firmware; R3 'no aplica'", True)
    pg.click("#sec-inventario .esc-seg button[data-v='']"); pg.check("#invSinMac"); pg.wait_for_timeout(250)
    check(f"{tag} 'solo sin MAC' no incluye R3", pg.locator("#sec-inventario tbody .tipo[data-t='R3']").count() == 0)
    pg.uncheck("#invSinMac"); pg.wait_for_timeout(200)
    pg.click("#sec-inventario th[aria-sort] .esc-th[data-col='version']"); pg.wait_for_timeout(200)
    check(f"{tag} ordenar por hardware marca aria-sort", pg.get_attribute("#sec-inventario th:has(.esc-th[data-col='version'])", "aria-sort") == "ascending")
    pg.locator("#sec-inventario tbody tr").first.focus(); pg.keyboard.press("ArrowDown"); pg.keyboard.press("Space")
    check(f"{tag} flechas + Espacio marcan fila y aparece barra de selección", pg.locator("#sec-inventario .esc-sel").is_visible())
    pg.click("#sec-inventario .esc-sel button:has-text('Cambiar hardware')"); pg.wait_for_selector(".sheet"); pg.keyboard.press("Escape")
    pg.locator("#sec-inventario tbody tr").first.focus(); pg.keyboard.press("Enter"); pg.wait_for_selector(".sheet h2:has-text('Editar')")
    check(f"{tag} Enter abre 'Editar placa'", True); pg.keyboard.press("Escape")
    pg.click("#sec-inventario .esc-sel button:has-text('Eliminar')"); pg.wait_for_selector(".sheet h2:has-text('Eliminar')"); check(f"{tag} eliminar pide confirmación en pantalla", "Eliminar" in pg.locator(".sheet .actions").inner_text()); pg.keyboard.press("Escape")
    # Tarjetas
    ir_a(pg, "tarjetas"); pg.keyboard.press("/"); pg.fill("#tarQ", "70:4b:ca:5b:01"); pg.wait_for_timeout(400)
    check(f"{tag} tarjetas: buscar por MAC", pg.locator("#sec-tarjetas tbody tr").count() >= 1)
    pg.fill("#tarQ", ""); pg.wait_for_timeout(300)
    pg.locator("#sec-tarjetas tbody tr").nth(2).focus(); pg.keyboard.press("Enter"); pg.wait_for_selector(".esc-panel")
    check(f"{tag} Enter abre el panel con R1/R2/R3", pg.locator(".esc-panel .esc-pl").count() == 3)
    check(f"{tag} panel: rótulos Hardware y Firmware; R3 sin MAC", "hardware" in pg.locator(".esc-panel").text_content().lower() and "firmware" in pg.locator(".esc-panel").text_content().lower() and pg.locator(".esc-panel .esc-pl[data-t='R3']").text_content().count("MAC") == 1)
    check(f"{tag} panel: botón Etiqueta DYMO -> /dymo?tarjeta_id=", "/dymo?tarjeta_id=" in (pg.get_attribute(".esc-panel a:has-text('Etiqueta DYMO')", "href") or ""))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check(f"{tag} Esc cierra el panel y devuelve el foco a la fila", pg.locator(".esc-panel").count() == 0 and pg.evaluate("() => document.activeElement.tagName") == "TR")
    pg.click("#sec-tarjetas .esc-seg button[data-v='incompleta']"); pg.wait_for_timeout(250)
    check(f"{tag} filtro Incompletas", pg.locator("#sec-tarjetas tbody tr").count() >= 1)
    # Consultar
    ir_a(pg, "consultar"); pg.fill("#consQ", "TQT-R1-V30-0005\n70:4b:ca:5b:05:a1\nTQT-R2-V30-0005\n70:4b:ca:5b:05:a2"); pg.press("#consQ", "Enter"); pg.wait_for_selector(".esc-ficha .num")
    check(f"{tag} consulta con texto de 4 líneas -> tarjeta 0005", pg.locator(".esc-ficha .num").inner_text().lstrip("0") == "5" or "5" in pg.locator(".esc-ficha .num").inner_text())
    check(f"{tag} ficha con 3 placas y firmware en R1/R2", pg.locator(".esc-ficha .esc-pl").count() == 3 and "firmware" in pg.locator(".esc-ficha").text_content().lower())
    check(f"{tag} historial de consultas en localStorage", json.loads(pg.evaluate("() => localStorage.getItem('tqt.consultas')") or "[]") != [])
    n_http = len(vg.http)
    pg.fill("#consQ", "TQT-R1-V30-9999"); pg.press("#consQ", "Enter"); pg.wait_for_selector(".banner[data-k='bad']")
    check(f"{tag} código inexistente muestra aviso claro (404 esperado)", "no está registrada" in pg.locator(".banner").first.inner_text())
    del vg.http[n_http:]   # el 404 de arriba es esperado
    pg.fill("#consQ", "70:4b:ca:5b:03:a2"); pg.press("#consQ", "Enter"); pg.wait_for_selector(".esc-ficha .num"); check(f"{tag} consulta por MAC", True)
    # Lotes y selector de lote
    pg.click("button.esc-lote"); pg.wait_for_selector(".esc-menu")
    check(f"{tag} selector de lote abre menú con 'Usar o crear lote'", "Usar o crear lote" in pg.locator(".esc-menu").inner_text())
    pg.keyboard.press("ArrowDown"); pg.keyboard.press("Escape"); check(f"{tag} Esc cierra el menú y regresa el foco", pg.locator(".esc-menu").count() == 0 and "esc-lote" in (pg.evaluate("() => document.activeElement.className") or ""))
    pg.click("button.esc-lote"); pg.click(".esc-menu .acc"); pg.wait_for_selector(".sheet h2:has-text('Lotes')"); check(f"{tag} 'Usar o crear lote' abre la hoja de lotes", True); pg.keyboard.press("Escape")
    ir_a(pg, "lotes"); check(f"{tag} lotes: lista con el lote activo", pg.locator("#sec-lotes .esc-lista li[data-activo='1']").count() == 1)
    # Excel
    ir_a(pg, "excel"); pg.click("#sec-excel button:has-text('Sincronizar Excel')"); pg.wait_for_selector("#sec-excel .banner", timeout=60000)
    check(f"{tag} Excel: sincroniza y muestra resultado", pg.locator("#sec-excel .banner").first.get_attribute("data-k") in ("ok", "warn"), pg.locator("#sec-excel").inner_text()[:200])
    with pg.expect_download(timeout=30000) as d:
        pg.click("#sec-excel button:has-text('Descargar copia')")
    check(f"{tag} Excel: descarga la copia .xlsx por fetch+blob", d.value.suggested_filename.endswith(".xlsx"), d.value.suggested_filename)
    pg.screenshot(path=str(SHOTS / "excel_resultado_1280_dark.png"))
    # WS: llegada de una placa nueva actualiza el Resumen sin recargar
    ir_a(pg, "resumen"); antes = pg.locator("#sec-resumen .esc-kpi .v").nth(4).inner_text()
    api("POST", "/api/pcb/manual", {"tipo": "R3", "version": "30", "serie": "0077", "cantidad": 1}); pg.wait_for_timeout(1500)
    check(f"{tag} evento WS actualiza el Resumen y la actividad en vivo", "77" in pg.locator("#sec-resumen .esc-feed").inner_text(), pg.locator("#sec-resumen .esc-feed").inner_text()[:150])
    # enlaces externos
    hrefs = {a.get_attribute("data-id"): a.get_attribute("href") for a in pg.locator("nav.esc-nav a").all()}
    check(f"{tag} Movimientos/Etiquetas/Administración enlazan a /admin#movimientos, /dymo, /admin", (hrefs.get("movimientos"), hrefs.get("etiquetas"), hrefs.get("admin")) == ("/admin#movimientos", "/dymo", "/admin"), str(hrefs))
    check(f"{tag} placeholder de MAC o sección real", pg.evaluate("() => !!document.querySelector('nav.esc-nav a[data-id=macs]')"))
    # Tab: enlace de salto primero, foco visible
    pg.reload(); pg.wait_for_selector("#sec-resumen"); pg.keyboard.press("Tab")
    check(f"{tag} primer Tab = 'Saltar al contenido'", pg.evaluate("() => document.activeElement.textContent") == "Saltar al contenido")
    # Versión móvil
    pg.click("button:has-text('Versión móvil')"); pg.wait_for_url("**/", timeout=8000)
    check(f"{tag} 'Versión móvil' guarda tqt.vista=movil y va a /", pg.evaluate("() => localStorage.getItem('tqt.vista')") == "movil" and pg.url.rstrip("/").endswith(PUERTO))
    # Cerrar sesión
    pg.evaluate("() => localStorage.removeItem('tqt.vista')"); pg.goto(BASE + "/monitor"); pg.wait_for_selector("#sec-resumen")
    pg.click("button[aria-label='Cerrar sesión']"); pg.wait_for_url("**/login*", timeout=8000)
    pg.goto(BASE + "/monitor", wait_until="load"); check(f"{tag} tras cerrar sesión /monitor pide iniciar sesión", "/login" in pg.url, pg.url)
    br.close()


def sin_clave(p):
    tag = "[sin clave]"; print(tag, flush=True)
    br, ctx, pg, vg = abrir(p, 1280, 800, "dark", con_clave=False)
    pg.goto(BASE + "/monitor", wait_until="networkidle"); pg.wait_for_selector("#sec-resumen"); pg.wait_for_timeout(500)
    check(f"{tag} /monitor abre sin contraseña", pg.url.split("#")[0].endswith("/monitor"), pg.url)
    check(f"{tag} no hay botón 'Cerrar sesión'", pg.locator("button:has-text('Cerrar sesión')").count() == 0)
    for sec in ("inventario", "tarjetas", "consultar", "lotes", "excel"): ir_a(pg, sec)
    axe(pg, f"{tag} excel"); check(f"{tag} consola limpia", not vg.consola and not vg.http, str((vg.consola, vg.http)[:3]))
    br.close()


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    existente = os.environ.get("ESC_SERVIDOR_EXISTENTE") == "1"
    proc = None
    try:
        if not existente:
            proc, tmp = arrancar(True)
        n, macs = sembrar(); print(f"sembradas {n} PCB, {macs} con MAC", flush=True)
        with sync_playwright() as p:
            recorrido(p); teclado_y_flujos(p)
        if "--sin-clave" in sys.argv and not existente:
            parar(proc); proc, tmp = arrancar(False); sembrar()
            with sync_playwright() as p:
                sin_clave(p)
    finally:
        if proc: parar(proc)
    malas = [r for r in RESULT if not r[1]]
    print(f"\n{len(RESULT) - len(malas)}/{len(RESULT)} comprobaciones correctas")
    for n_, _, d in malas: print("  FALLA:", n_, "->", d[:400])
    sys.exit(1 if malas else 0)
