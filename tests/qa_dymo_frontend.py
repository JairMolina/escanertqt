"""QA manual del frontend /dymo con Playwright y un servicio DYMO Connect SIMULADO (no es hardware real).

    python tests/qa_dymo_frontend.py [carpeta_capturas]

Levanta: (1) uvicorn con la app en https://127.0.0.1:8455 con BD/Excel/exports temporales y un certificado propio
(no toca certs/ ni datos reales); (2) un DYMO Connect simulado por page.route (en la PC hay uno real en 41951: NO se usa ni se le imprime). No se descubre por unittest (no empieza por test_).
"""
import datetime
import http.server
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="tqt_qa_dymo_"))
PUERTO = 8455
BASE = f"https://127.0.0.1:{PUERTO}"
CAPTURAS = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "docs" / "qa" / "dymo_img"
CAPTURAS.mkdir(parents=True, exist_ok=True)

ENTORNO = {**os.environ, "TQT_DB_PATH": str(TMP / "x.db"), "TQT_EXCEL_DIR": str(TMP / "xl"), "TQT_EXPORTS_DIR": str(TMP / "ex"),
           "TQT_BACKUP_DIR": str(TMP / "bk"), "TQT_ADMIN_PASSWORD": "ClaveQA-12345", "HTTPS_PORT": str(PUERTO), "TQT_HOST_IP": "127.0.0.1"}


# ------------------------------------------------------------------ certificado propio (nunca certs/)
def generar_cert():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import ipaddress
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "localhost")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(ahora - datetime.timedelta(days=1))
            .not_valid_after(ahora + datetime.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .sign(key, hashes.SHA256()))
    (TMP / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (TMP / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                                     serialization.NoEncryption()))


# ------------------------------------------------------------------ DYMO Connect simulado (page.route)
# En esta PC hay un DYMO Connect REAL escuchando en 127.0.0.1:41951 (LabelWriter 450 desconectada): no se puede ni se debe
# ocupar ese puerto ni mandarle trabajos. Por eso el servicio se simula interceptando en el navegador las peticiones a
# https://127.0.0.1:4195x/DYMO/DLS/Printing/* (mismos endpoints, formatos y cabeceras que el servicio real; ver el framework).
import re as _re


class DymoFalso:
    """Modos: off (servicio caido) | ok | desconectada | varias | sin_impresoras | error_impresion."""

    def __init__(self):
        self.modo = "off"
        self.peticiones = []      # (metodo, comando, cuerpo_dict)

    def impresoras_xml(self):
        def lw(n, conn=True):
            return (f"<LabelWriterPrinter><Name>{n}</Name><ModelName>{n}</ModelName><IsConnected>{'True' if conn else 'False'}</IsConnected>"
                    f"<IsLocal>True</IsLocal><IsTwinTurbo>False</IsTwinTurbo></LabelWriterPrinter>")
        if self.modo == "sin_impresoras":
            return "<Printers></Printers>"
        if self.modo == "desconectada":
            return f"<Printers>{lw('DYMO LabelWriter 550', False)}</Printers>"
        if self.modo == "varias":
            return (f"<Printers>{lw('DYMO LabelWriter 450 Turbo')}{lw('DYMO LabelWriter 550')}"
                    "<TapePrinter><Name>DYMO LabelManager PnP</Name><ModelName>DYMO LabelManager PnP</ModelName>"
                    "<IsConnected>True</IsConnected><IsLocal>True</IsLocal><IsAutoCutSupported>False</IsAutoCutSupported></TapePrinter></Printers>")
        return f"<Printers>{lw('DYMO LabelWriter 550')}</Printers>"

    def instalar(self, ctx):
        cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}

        def manejar(route):
            req = route.request
            m = _re.match(r"https://(?:127\.0\.0\.1|localhost):(\d+)/DYMO/DLS/Printing/(\w+)", req.url)
            if not m or self.modo == "off" or m.group(1) != "41951":
                return route.abort("connectionrefused")
            cmd = m.group(2)
            if req.method == "OPTIONS":
                return route.fulfill(status=200, headers=cors, body="")
            cuerpo = dict(urllib.parse.parse_qsl(req.post_data or "", keep_blank_values=True)) if req.method == "POST" else                 dict(urllib.parse.parse_qsl(urllib.parse.urlparse(req.url).query))
            self.peticiones.append((req.method, cmd, cuerpo))
            if cmd == "StatusConnected":
                return route.fulfill(status=200, headers=cors, content_type="text/plain", body="true")
            if cmd == "GetPrinters":
                return route.fulfill(status=200, headers=cors, content_type="text/xml", body=self.impresoras_xml())
            if cmd == "PrintLabel":
                if self.modo == "error_impresion":
                    return route.fulfill(status=500, headers=cors, content_type="text/plain", body="Printer error")
                return route.fulfill(status=200, headers=cors, content_type="text/plain", body="true")
            return route.fulfill(status=404, headers=cors, body="no")
        ctx.route(_re.compile(r"https://(127\.0\.0\.1|localhost):419\d\d/.*"), manejar)

    def arrancar(self):  # compatibilidad: ahora el "servicio" vive en cada contexto
        pass

    def parar(self):
        pass

    def impresiones(self):
        return [p for p in self.peticiones if p[0] == "POST" and p[1] == "PrintLabel"]


FALSO = DymoFalso()


# ------------------------------------------------------------------ datos de prueba
def sembrar():
    os.environ.update(ENTORNO)
    sys.path.insert(0, str(RAIZ))
    sys.path.insert(0, str(RAIZ / "tests"))
    from app.database import db, inventario as inv
    db.init_db()
    lote = db.create_lote("QA-DYMO", 9, 2026, activo=True)["id"]
    macs = iter(f"70:4B:CA:5B:9F:{n:02X}" for n in range(1, 60))

    def par(num, con_mac=True, probada=True, r2=True):
        i1 = inv.registrar_manual("R1", "30", num)["pcbs"][0]["id"]
        ids = [i1]
        if r2:
            i2 = inv.registrar_manual("R2", "30", num)["pcbs"][0]["id"]
            ids.append(i2)
        inv.confirmar_recepcion(ids)
        t = inv.crear_tarjeta(lote, num, i1, ids[1] if r2 else None, None)
        if con_mac:
            for pid in ids:
                inv.set_mac(pid, next(macs))
        if probada:
            db.set_prueba(t["id"], "prueba_pcb", "OK")
        return t["id"]
    ids = {"final": par("0021"), "final2": par("0022"), "sinmac": par("0023", con_mac=False),
           "sinprobar": par("0024", probada=False), "incompleta": par("0025", r2=False)}
    return ids


def esperar_http(url, seg=40):
    ctx = ssl._create_unverified_context()
    fin = time.time() + seg
    while time.time() < fin:
        try:
            urllib.request.urlopen(url, context=ctx, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


# ------------------------------------------------------------------ pruebas
RESULTADOS = []


def chk(nombre, ok, detalle=""):
    RESULTADOS.append((nombre, bool(ok), detalle))
    print(("PASA  " if ok else "FALLA ") + nombre + (f"  -> {detalle}" if detalle and not ok else ""), flush=True)


def main():
    from playwright.sync_api import sync_playwright
    generar_cert()
    ids = sembrar()
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO),
                            "--ssl-keyfile", str(TMP / "key.pem"), "--ssl-certfile", str(TMP / "cert.pem")],
                           cwd=RAIZ, env=ENTORNO, stdout=open(TMP / "srv.log", "w"), stderr=subprocess.STDOUT)
    falso = FALSO
    try:
        if not esperar_http(BASE + "/api/status"):
            print("El servidor no arrancó:", (TMP / "srv.log").read_text()[-2000:])
            return 2
        with sync_playwright() as pw:
            nav = None
            for canal in (None, "chrome", "msedge"):
                try:
                    nav = pw.chromium.launch(channel=canal) if canal else pw.chromium.launch()
                    break
                except Exception as e:  # noqa: BLE001
                    print("navegador", canal, "no disponible:", str(e).splitlines()[0])
            escenarios(pw, nav, falso, ids)
            nav.close()
    finally:
        falso.parar()
        srv.terminate()
    fallos = [r for r in RESULTADOS if not r[1]]
    print(f"\n{len(RESULTADOS) - len(fallos)} pasan, {len(fallos)} fallan. Capturas: {CAPTURAS}")
    return 1 if fallos else 0


def nuevo_ctx(nav, movil=False, ancho=1280, alto=800):
    if movil:
        ctx = nav.new_context(ignore_https_errors=True, viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True,
                              user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
                              accept_downloads=True)
    else:
        ctx = nav.new_context(ignore_https_errors=True, viewport={"width": ancho, "height": alto}, accept_downloads=True)
    FALSO.instalar(ctx)
    ctx.add_init_script("window.__prints = 0; const _p = window.print; window.print = function(){ window.__prints++; };")
    return ctx


def abrir(ctx, url="/dymo", errores=None):
    pg = ctx.new_page()
    errs = [] if errores is None else errores
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    pg.goto(BASE + url, wait_until="networkidle")
    return pg, errs


def esperar_pill(pg, texto, seg=15):
    pg.wait_for_function("t => document.getElementById('pillTxt').textContent.includes(t)", arg=texto, timeout=seg * 1000)


def escenarios(pw, nav, falso, ids):
    api = lambda ruta: json.loads(urllib.request.urlopen(BASE + ruta, context=ssl._create_unverified_context()).read())  # noqa: E731

    # ---- 1) DYMO Connect NO detectado
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "no detectado", 30)
    chk("no detectado: pastilla", "DYMO Connect no detectado" in pg.inner_text("#pillTxt"))
    chk("no detectado: ayuda accionable", "Abre DYMO Connect" in pg.inner_text("#ayuda") and "Actualizar" in pg.inner_text("#ayuda"))
    chk("no detectado: 'Imprimir en DYMO' deshabilitado", pg.is_disabled("#btnPrint"))
    chk("no detectado: 'Abrir en DYMO Connect' habilitado", not pg.is_disabled("#btnOpen"))
    pg.screenshot(path=str(CAPTURAS / "1_no_detectado_1280.png"), full_page=True)
    ctx.close()

    # ---- 2) Detectado, 1 impresora 550
    falso.modo = "ok"
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "detectado", 20)
    chk("detectado: pastilla verde", pg.get_attribute("#pill", "data-k") == "ok" and "1 impresora" in pg.inner_text("#pillTxt"), pg.inner_text("#pillTxt"))
    chk("detectado: selector con la 550", pg.eval_on_selector("#selPrinter", "s => [...s.options].map(o => o.text)") == ["DYMO LabelWriter 550"])
    chk("detectado: Imprimir habilitado", not pg.is_disabled("#btnPrint"))
    sel = pg.eval_on_selector("#selTarjeta", "s => [...s.options].map(o => [o.value, o.text])")
    chk("selector de tarjetas etiqueta el estado", any("final" in t for _, t in sel) and any("incompleta" in t for _, t in sel), str(sel))

    chk("tarjeta por defecto = primera imprimible (no la incompleta)", pg.input_value("#selTarjeta") != str(ids["incompleta"]))
    pg.select_option("#selTarjeta", str(ids["final"]))
    # ---- vista previa a escala real y guía 3 mm
    caja = pg.evaluate("""() => { const e = document.querySelector('.dymo-label'); const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
        const mm = 96 / 25.4; const host = document.getElementById('zoomHost');
        return {w: e.offsetWidth / mm, h: e.offsetHeight / mm, pad: parseFloat(cs.paddingLeft) / mm, rw: r.width, rh: r.height,
                transform: getComputedStyle(host).transform}; }""")
    chk("preview 57x32 mm (proporcion 57:32)", abs(caja["w"] - 57) < 0.3 and abs(caja["h"] - 32) < 0.3, str(caja))
    chk("preview con zona segura de 3 mm", abs(caja["pad"] - 3) < 0.1, str(caja))
    chk("preview escalada 3x proporcional", abs(caja["rw"] / caja["rh"] - 57 / 32) < 0.02, str(caja))
    txt = pg.evaluate("() => [...document.querySelectorAll('.dymo-l')].map(e => e.textContent)")
    chk("preview muestra la trama de 4 lineas", txt[0] == "TQT-R1-V30-0021" and txt[2] == "TQT-R2-V30-0021" and txt[1] == txt[1].lower() and len(txt) == 4, str(txt))
    desb = pg.evaluate("() => [...document.querySelectorAll('.dymo-l')].some(l => l.scrollWidth > l.clientWidth + 1)")
    chk("preview sin desbordar", not desb)
    chk("aviso final", "Etiqueta final" in pg.inner_text("#aviso"))
    pg.screenshot(path=str(CAPTURAS / "2_detectado_final_1280.png"), full_page=True)

    # ---- imprimir UNA peticion por tarjeta con XML correcto y Copies
    pg.select_option("#selTarjeta", str(ids["final"]))
    pg.fill("#inCopias", "3")
    falso.peticiones.clear()
    pg.click("#btnPrint")
    pg.wait_for_function("document.getElementById('progTxt').textContent.includes('enviada')", timeout=15000)
    imp = falso.impresiones()
    chk("imprimir: UNA peticion PrintLabel", len(imp) == 1, str(len(imp)))
    if imp:
        cuerpo = imp[0][2]
        esperado = urllib.request.urlopen(BASE + f"/api/dymo/label/{ids['final']}/xml", context=ssl._create_unverified_context()).read().decode("utf-8")
        chk("imprimir: XML enviado == /xml del servidor", cuerpo.get("labelXml") == esperado)
        chk("imprimir: Copies=3", "<Copies>3</Copies>" in cuerpo.get("printParamsXml", ""), cuerpo.get("printParamsXml", ""))
        chk("imprimir: impresora correcta", cuerpo.get("printerName") == "DYMO LabelWriter 550")
    chk("imprimir: window.print nunca invocado", pg.evaluate("window.__prints") == 0)

    # copias limites
    for entrada, esperado_c in (("", 1), ("0", 1), ("99", 99), ("abc", 1)):
        pg.fill("#inCopias", entrada)
        falso.peticiones.clear()
        pg.click("#btnPrint")
        pg.wait_for_function("document.getElementById('progTxt').textContent.includes('enviada')", timeout=15000)
        pg.wait_for_timeout(100)
        imp = falso.impresiones()
        chk(f"copias '{entrada}' -> {esperado_c}", len(imp) == 1 and f"<Copies>{esperado_c}</Copies>" in imp[0][2].get("printParamsXml", ""),
            imp[0][2].get("printParamsXml", "") if imp else "sin peticion")
    pg.fill("#inCopias", "1")

    # doble clic rapido en Imprimir: una sola peticion
    falso.peticiones.clear()
    pg.dblclick("#btnPrint")
    pg.wait_for_timeout(1500)
    chk("doble clic en Imprimir -> 1 peticion", len(falso.impresiones()) == 1, str(len(falso.impresiones())))

    # ---- tarjeta sin MAC / incompleta / sin probar
    pg.select_option("#selTarjeta", str(ids["sinmac"]))
    pg.wait_for_timeout(200)
    aviso = pg.inner_text("#aviso")
    chk("sin MAC: aviso de identificacion y MAC faltante", "identificación" in aviso.lower() and "MAC" in aviso, aviso)
    txt = pg.evaluate("() => [...document.querySelectorAll('.dymo-l')].map(e => e.textContent)")
    chk("sin MAC: lineas de MAC vacias", txt[1] == "" and txt[3] == "", str(txt))
    pg.screenshot(path=str(CAPTURAS / "3_sin_mac_1280.png"), full_page=True)
    falso.peticiones.clear()
    pg.click("#btnPrint")
    pg.wait_for_function("document.getElementById('progTxt').textContent.includes('enviada')", timeout=15000)
    xml = falso.impresiones()[0][2]["labelXml"]
    chk("sin MAC: imprime con lineas vacias en el XML", "<Text></Text>" in xml)
    pg.select_option("#selTarjeta", str(ids["incompleta"]))
    pg.wait_for_timeout(200)
    chk("incompleta: aviso y boton Imprimir deshabilitado", "No se puede etiquetar" in pg.inner_text("#aviso") and pg.is_disabled("#btnPrint"))
    pg.screenshot(path=str(CAPTURAS / "4_incompleta_1280.png"), full_page=True)

    # ---- Abrir en DYMO Connect = descarga .dymo
    pg.select_option("#selTarjeta", str(ids["final"]))
    with pg.expect_download() as d:
        pg.click("#btnOpen")
    dl = d.value
    ruta = TMP / "descarga.dymo"
    dl.save_as(ruta)
    chk("Abrir en DYMO Connect: descarga .dymo", dl.suggested_filename.endswith(".dymo") and ruta.read_bytes().startswith(b"\xef\xbb\xbf<?xml"), dl.suggested_filename)

    # ---- lote: solo finales vs todas
    pg.select_option("#selLoteModo", "final")
    falso.peticiones.clear()
    pg.click("#btnPrintAll")
    pg.wait_for_function("document.getElementById('progTxt').textContent.includes('etiquetas enviadas')", timeout=30000)
    chk("lote solo finales: 2 peticiones (0021, 0022)", len(falso.impresiones()) == 2, str(len(falso.impresiones())))
    pg.select_option("#selLoteModo", "todas")
    falso.peticiones.clear()
    pg.click("#btnPrintAll")
    pg.wait_for_function("document.getElementById('progTxt').textContent.includes('4 de 4')", timeout=30000)
    pg.wait_for_timeout(200)
    chk("lote todas: 4 peticiones (sin la incompleta)", len(falso.impresiones()) == 4, str(len(falso.impresiones())))
    pg.screenshot(path=str(CAPTURAS / "5_lote_1280.png"), full_page=True)

    # ---- descargar lote
    for modo, esperado_n in (("final", 2), ("todas", 4)):
        pg.select_option("#selLoteModo", modo)
        descargas = []
        alta = lambda x: descargas.append(x)
        pg.on("download", alta)
        pg.click("#btnDownAll")
        pg.wait_for_timeout(4500)
        pg.remove_listener("download", alta)
        nombres = [x.suggested_filename for x in descargas]
        if any(n.endswith(".zip") for n in nombres):
            z = zipfile.ZipFile(io.BytesIO(Path(descargas[0].path()).read_bytes())) if nombres[0].endswith(".zip") else None
            n_arch = len(z.namelist()) if z else -1
            chk(f"descargar lote ({modo}): un ZIP con {esperado_n} .dymo", len(nombres) == 1 and n_arch == esperado_n, f"{nombres} n={n_arch}")
        else:
            chk(f"descargar lote ({modo}): {esperado_n} archivos", len(nombres) == esperado_n, str(nombres))
        pg.reload(wait_until="networkidle")
        esperar_pill(pg, "detectado", 20)

    chk("window.print nunca invocado (sesion completa)", pg.evaluate("window.__prints") == 0)
    # el framework de DYMO sondea los puertos 41952-41960 (conexion rechazada = ruido esperado del navegador, no un fallo)
    malos = [e for e in errs if "ERR_CONNECTION_REFUSED" not in e]
    chk("consola sin errores (DYMO conectado)", not malos, str(malos[:5]))
    # 390x844 con servicio disponible pero UA de escritorio
    pg.set_viewport_size({"width": 390, "height": 844})
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(CAPTURAS / "6_detectado_390_desktopUA.png"), full_page=True)
    desb = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    chk("390 px: sin scroll horizontal de pagina", not desb)
    ctx.close()

    # ---- impresora desconectada
    falso.modo = "desconectada"
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "desconectada", 20)
    chk("desconectada: pastilla y aviso", pg.get_attribute("#pill", "data-k") == "warn" and "desconectada" in pg.inner_text("#ayuda"))
    chk("desconectada: Imprimir deshabilitado, descarga habilitada", pg.is_disabled("#btnPrint") and not pg.is_disabled("#btnOpen"))
    pg.screenshot(path=str(CAPTURAS / "7_desconectada_1280.png"), full_page=True)
    ctx.close()

    # ---- sin impresoras
    falso.modo = "sin_impresoras"
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "no encontrada", 20)
    chk("sin impresoras: mensaje accionable", "Enciende la LabelWriter" in pg.inner_text("#ayuda"))
    ctx.close()

    # ---- varias impresoras: 550 preferida; la de cinta (LabelManager) no debe ofrecerse
    falso.modo = "varias"
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "detectado", 20)
    opciones = pg.eval_on_selector("#selPrinter", "s => [...s.options].map(o => o.text)")
    chk("varias: 550 preseleccionada", pg.input_value("#selPrinter") == "DYMO LabelWriter 550", pg.input_value("#selPrinter"))
    chk("varias: impresora de cinta no se ofrece", not any("LabelManager" in o for o in opciones), str(opciones))
    pg.select_option("#selTarjeta", str(ids["final"]))
    pg.select_option("#selPrinter", "DYMO LabelWriter 450 Turbo")
    falso.peticiones.clear()
    pg.click("#btnPrint")
    pg.wait_for_function("document.getElementById('progTxt').textContent.includes('enviada')", timeout=15000)
    chk("varias: imprime en la impresora elegida", falso.impresiones()[0][2]["printerName"] == "DYMO LabelWriter 450 Turbo")
    pg.screenshot(path=str(CAPTURAS / "8_varias_1280.png"), full_page=True)
    ctx.close()

    # ---- error del servicio al imprimir
    falso.modo = "error_impresion"
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "detectado", 20)
    pg.select_option("#selTarjeta", str(ids["final"]))
    pg.click("#btnPrint")
    pg.wait_for_selector("#aviso :text('No se pudo imprimir')", timeout=20000)
    msg = pg.inner_text("#aviso")
    chk("error de impresion: mensaje visible y accionable", "No se pudo imprimir" in msg and len(msg) > 30, msg)
    chk("error de impresion: boton se rehabilita", not pg.is_disabled("#btnPrint"))
    pg.screenshot(path=str(CAPTURAS / "9_error_impresion_1280.png"), full_page=True)
    # lote con errores: no debe declarar exito
    pg.select_option("#selLoteModo", "final")
    pg.click("#btnPrintAll")
    pg.wait_for_timeout(3000)
    chk("lote con errores: informa 'sin imprimir'", "sin imprimir" in pg.inner_text("#aviso"), pg.inner_text("#aviso")[:200])
    ctx.close()

    # ---- celular
    ctx = nuevo_ctx(nav, movil=True)
    pg, errs = abrir(ctx)
    esperar_pill(pg, "Celular", 20)
    chk("celular: estado 'solo descarga'", "Celular" in pg.inner_text("#pillTxt") and "no se imprime directo" in pg.inner_text("#ayuda").lower())
    chk("celular: Imprimir deshabilitado, Abrir habilitado", pg.is_disabled("#btnPrint") and not pg.is_disabled("#btnOpen"))
    desb = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    chk("celular 390: sin scroll horizontal de pagina", not desb)
    pg.screenshot(path=str(CAPTURAS / "10_celular_390.png"), full_page=True)
    chk("celular: consola sin errores", not [e for e in errs if "ERR_CONNECTION_REFUSED" not in e], str(errs[:5]))
    ctx.close()

    # ---- peor caso visual en 1x (tamano real)
    falso.modo = "ok"
    ctx = nuevo_ctx(nav)
    pg, errs = abrir(ctx)
    pg.select_option("#selZoom", "1")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(CAPTURAS / "11_tamano_real_1x.png"))
    ctx.close()


if __name__ == "__main__":
    sys.exit(main())
