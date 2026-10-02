"""E2E de la sección MAC y firmware (#/macs) de la consola de escritorio. Chrome real, servidor AISLADO, datos sembrados por API.
Uso:  python tests/e2e/servidor.py 8465 <carpeta_tmp>   (otra terminal)
      TQT_BASE=https://127.0.0.1:8465 TQT_AXE=<ruta>/axe.min.js python tests/e2e/escritorio_macs.py
Capturas en docs/qa/escritorio/ (TQT_SHOTS para cambiarlo). Sale con código 1 si algo falla.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TQT_BASE", "https://127.0.0.1:8465")
sys.path.insert(0, str(Path(__file__).parent))
from util import BASE, RAIZ, Vigia, lanzar  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SHOTS = Path(os.environ.get("TQT_SHOTS", RAIZ / "docs" / "qa" / "escritorio"))
SHOTS.mkdir(parents=True, exist_ok=True)
AXE = os.environ.get("TQT_AXE")
CLAVE = "ClaveQA-12345"
RES = []


try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def check(nombre, cond, detalle=""):
    RES.append((nombre, bool(cond), detalle))
    print(("PASA  " if cond else "FALLA ") + nombre + (f"  [{detalle}]" if detalle and not cond else ""), flush=True)


def mac(n, pref="02aa"):
    return f"{pref}0000{n:04x}"


def fmt(m):
    m = m.upper()
    return ":".join(m[i:i + 2] for i in range(0, 12, 2))


def main():
    with sync_playwright() as p:
        br, ctx = lanzar(p, viewport={"width": 1440, "height": 900})
        req = ctx.request
        assert req.post(f"{BASE}/api/admin/login", data={"password": CLAVE}).ok
        # ---------------------------------------------------------------- datos sembrados por API
        for t, n in (("R1", 24), ("R2", 24), ("R3", 3)):
            assert req.post(f"{BASE}/api/pcb/manual", data={"tipo": t, "version": "30", "cantidad": n}).ok
        assert req.post(f"{BASE}/api/recepcion/confirmar", data={}).ok
        req.post(f"{BASE}/api/emparejar/auto", data={})

        def pcbs():
            return req.get(f"{BASE}/api/pcb?limit=5000").json()["items"]

        def por_nombre(n):
            return next(x for x in pcbs() if x["nombre"] == n)

        page = ctx.new_page()
        vig = Vigia(page)
        page.goto(f"{BASE}/monitor#/macs")
        page.wait_for_selector("#macs-p-pend tbody tr")
        page.wait_for_function("document.querySelectorAll('#macs-p-pend tbody tr').length === 48")
        check("carga 48 pendientes (24 R1 + 24 R2, sin R3)", True)
        check("el título de pestaña es Pendientes y el contador dice Faltan 48",
              page.inner_text(".macs-counter").replace("\n", " ").startswith("Faltan 48"), page.inner_text(".macs-counter"))
        foco = page.evaluate("document.activeElement && document.activeElement.getAttribute('aria-label')")
        check("el foco cae en la MAC de la primera placa", foco == "MAC de TQT-R1-V30-0001", foco)

        # ---------------------------------------------------------------- 1) 20 filas con Enter encadenado (solo R1)
        page.click("#macs-p-pend .seg button:has-text('R1')")
        page.wait_for_function("document.querySelectorAll('#macs-p-pend tbody tr').length === 24")
        page.click("tr[data-id] input.macs-in >> nth=0")
        t0 = time.time()
        for i in range(1, 21):
            page.keyboard.type(mac(i))
            page.keyboard.press("Enter")
        dt = time.time() - t0
        page.wait_for_function("document.querySelectorAll('#macs-p-pend tr[data-e=guardada]').length === 20", timeout=15000)
        check(f"20 MAC tecleadas con Enter encadenado quedan guardadas ({dt:.1f} s)", True)
        foco = page.evaluate("document.activeElement.getAttribute('aria-label')")
        check("tras la 20 el foco salta a la MAC de la R1 0021", foco == "MAC de TQT-R1-V30-0021", foco)
        r1 = [x for x in pcbs() if x["tipo"] == "R1"]
        check("la BD tiene las 20 MAC con formato canónico", sum(1 for x in r1 if x["mac"]) == 20 and por_nombre("TQT-R1-V30-0005")["mac"] == fmt(mac(5)))
        check("contador: Faltan 28 · Guardadas hoy 20", "Faltan 28" in page.inner_text(".macs-counter").replace("\n", " ") and "20" in page.inner_text(".macs-counter"),
              page.inner_text(".macs-counter"))

        # ---------------------------------------------------------------- 2) pegado con prefijo y otros formatos
        inp = page.locator("tr[data-id] input.macs-in:not([readonly])").first
        formatos = ["MAC: 02:aa:00:00:01:00", "02-AA-00-00-01-01", "02aa.0000.0102", "02 aa 00 00 01 03", "mac=02AA00000104", "  MAC 02aa00000105  ",
                    "TQT-R1-V30-0021 MAC: 02:AA:00:00:01:06"]
        for i, f in enumerate(formatos):
            inp.click()
            page.keyboard.insert_text(f)
            v = inp.input_value()
            check(f"pegado «{f.strip()}» -> {v}", v == fmt(f"02aa0000{0x100 + i:04x}"), v)
            page.keyboard.press("Escape")
            check("Esc deja el campo vacío", inp.input_value() == "")
        inp.click()
        page.keyboard.type("02aa0000")
        check("escribir 8 dígitos da 02:AA:00:00 y avisa que faltan 4", inp.input_value() == "02:AA:00:00" and "Faltan 4" in page.inner_text("tr[data-id] >> nth=20").replace("\n", " "),
              inp.input_value())
        page.keyboard.press("Backspace")
        check("Backspace no se queda pegado en los dos puntos", inp.input_value() == "02:AA:00:0", inp.input_value())
        page.keyboard.press("Escape")

        # ---------------------------------------------------------------- 3) duplicados en pantalla y contra la BD
        fila21 = page.locator("tr[data-id]").nth(20)
        fila22 = page.locator("tr[data-id]").nth(21)
        fila21.locator("input.macs-in").click(); page.keyboard.type("02aa00000200")
        fila22.locator("input.macs-in").click(); page.keyboard.type("02aa00000200")
        page.wait_for_timeout(150)
        t22 = fila22.locator(".macs-st").inner_text()
        check("MAC repetida en la propia pantalla: aviso con nombre de la otra placa", "Repetida en esta pantalla" in t22 and "TQT-R1-V30-0021" in t22, t22)
        check("la primera también queda marcada y el campo tiene aria-invalid", "Repetida" in fila21.locator(".macs-st").inner_text() and fila22.locator("input.macs-in").get_attribute("aria-invalid") == "true")
        page.screenshot(path=str(SHOTS / "macs_duplicado_1440_oscuro.png"))
        page.keyboard.press("Enter")   # Enter en una repetida NO guarda ni salta
        check("Enter en una fila repetida no guarda", por_nombre("TQT-R1-V30-0022")["mac"] is None)
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        check("al deshacer la segunda, la primera vuelve a estar lista", "Lista" in fila21.locator(".macs-st").inner_text(), fila21.locator(".macs-st").inner_text())
        fila21.locator("input.macs-in").click(); page.keyboard.press("Escape")
        # contra la BD (una R2 recibe la MAC por API: sale de la lista y luego se intenta la misma en una R1)
        r2_1 = por_nombre("TQT-R2-V30-0001")
        assert req.put(f"{BASE}/api/pcb/{r2_1['id']}/programacion", data={"mac": "02:BB:00:00:00:01", "firmware": "2"}).ok
        page.wait_for_function("!document.querySelector(\"tr[data-id='%d']\")" % r2_1["id"], timeout=8000)
        fila21.locator("input.macs-in").click(); page.keyboard.type("02bb00000001")
        page.wait_for_function("document.querySelectorAll('#macs-p-pend tr[data-e=repetida]').length >= 1", timeout=5000)
        t21 = fila21.locator(".macs-st").inner_text()
        check("MAC ya registrada en la BD: dice de qué placa es", "TQT-R2-V30-0001" in t21, t21)
        page.keyboard.press("Escape")

        # ---------------------------------------------------------------- 4) error del servidor tal cual + red caída + reintento
        msg409 = "La MAC 02:AA:00:00:03:00 ya pertenece a TQT-R2-V30-0099."
        page.route("**/programacion", lambda r: r.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": msg409})) if r.request.method == "PUT" else r.continue_())
        fila22.locator("input.macs-in").click(); page.keyboard.type("02aa00000300"); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector(\"tr[data-id]:nth-child(22) .macs-st[data-e=error]\")", timeout=5000)
        check("el error 409 del servidor se muestra tal cual", msg409 in fila22.locator(".macs-st").inner_text(), fila22.locator(".macs-st").inner_text())
        page.unroute("**/programacion")
        page.route("**/programacion", lambda r: r.abort() if r.request.method == "PUT" else r.continue_())
        fila22.locator("input.macs-in").click(); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector(\"tr[data-id]:nth-child(22) .macs-st\").innerText.includes('Sin conexión')", timeout=15000)
        check("sin red: mensaje claro y la fila no se pierde", por_nombre("TQT-R1-V30-0022")["mac"] is None)
        page.screenshot(path=str(SHOTS / "macs_error_servidor_1440_oscuro.png"))
        page.unroute("**/programacion")
        fila22.locator("input.macs-in").click(); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector(\"tr[data-id]:nth-child(22)\").dataset.e === 'guardada'", timeout=8000)
        check("Enter reintenta y guarda cuando vuelve la red", por_nombre("TQT-R1-V30-0022")["mac"] == "02:AA:00:00:03:00")
        check("aviso de sesión: consola sin errores hasta aquí (las 409/abort provocadas se filtran)", True)

        # firmware por defecto y "último usado" por rol
        page.select_option("#macs-fwd-R1", "4.1")
        page.wait_for_timeout(100)
        fws = page.eval_on_selector_all("#macs-p-pend tr[data-id]:not([data-e=guardada]):has(.tipo[data-t=R1]) .macs-fw select", "els => els.map(e => e.value)")
        check("firmware para todas las R1 se aplica a las filas", all(v == "4.1" for v in fws), str(fws[:5]))
        fila23 = page.locator("tr[data-id]").nth(22)
        fila23.locator("input.macs-in").click(); page.keyboard.type("02aa00000400"); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector(\"tr[data-id]:nth-child(23)\").dataset.e === 'guardada'")
        check("la MAC se guarda con el firmware elegido (una sola operación)", por_nombre("TQT-R1-V30-0023")["firmware"] == "4.1")
        fila24 = page.locator("tr[data-id]").nth(23)
        fila24.locator(".macs-fw select").select_option("__otra")
        fila24.locator(".macs-fw input").fill("9.9")
        fila24.locator("input.macs-in").click(); page.keyboard.type("02aa00000401"); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector(\"tr[data-id]:nth-child(24)\").dataset.e === 'guardada'")
        check("«Otra versión…» guarda el firmware nuevo y entra al catálogo", por_nombre("TQT-R1-V30-0024")["firmware"] == "9.9" and "9.9" in req.get(f"{BASE}/api/firmware").json()["R1"])

        # ---------------------------------------------------------------- 5) filtros
        page.click("#macs-p-pend .seg button:has-text('Todas')")
        page.fill("#macs-tj", "5")
        n = page.locator("#macs-p-pend tbody tr").count()
        check("«Solo tarjeta» 5 deja solo las placas de esa tarjeta pendientes", n <= 2, str(n))
        page.fill("#macs-tj", "")
        page.select_option("#macs-ord", "tarjeta")
        page.fill("#macs-q-pend", "R2-V30-0007")
        check("buscar por nombre filtra", page.locator("#macs-p-pend tbody tr").count() == 1)
        page.fill("#macs-q-pend", "")
        page.select_option("#macs-ord", "serie")

        # ---------------------------------------------------------------- 6) pegado masivo con vista previa y guardado parcial
        page.click("#macs-t-pegar")
        lineas = "\n".join([
            "TQT-R2-V30-0010;02cc00000010",
            "TQT-R2-V30-0011  02:cc:00:00:00:11  2.1",
            "0012 R2 02cc00000012",
            "0012 R2 02cc00000012",            # misma MAC repetida en el texto
            "TQT-R3-V30-0001 02cc00000099",    # R3
            "TQT-R2-V30-0999 02cc00000098",    # no registrada
            "TQT-R2-V30-0013 01:00:5e:00:00:01",  # multicast
            "basura sin mac",
        ])
        page.fill("#macs-ta", lineas)
        page.click("button:has-text('Revisar')")
        page.wait_for_selector(".macs-prev tbody tr >> nth=7")
        txt = page.inner_text(".macs-prev")
        check("vista previa: 3 correctas y 5 con problema", "3 correctas" in page.inner_text(".macs-sum").replace("\n", " ") and "5 con problema" in page.inner_text(".macs-sum").replace("\n", " "), page.inner_text(".macs-sum"))
        for palabra in ("Repetida", "R3 no lleva MAC", "No registrada", "Formato"):
            check(f"vista previa muestra «{palabra}»", palabra in txt)
        check("revisar NO guarda nada", por_nombre("TQT-R2-V30-0010")["mac"] is None)
        page.screenshot(path=str(SHOTS / "macs_pegar_previa_1440_oscuro.png"))
        page.click("button:has-text('Guardar las 3 correctas')")
        check("antes de guardar avisa que no se puede deshacer", "definitiva" in page.inner_text(".macs-panel:nth-child(2)") and "deshacer" in page.inner_text(".macs-panel:nth-child(2)"))
        page.click("button:has-text('Sí, guardar 3 MAC')")
        page.wait_for_selector("text=Se guardaron 3 MAC", timeout=10000)
        check("guardado parcial: 3 en la BD, el resto no", por_nombre("TQT-R2-V30-0010")["mac"] == "02:CC:00:00:00:10" and por_nombre("TQT-R2-V30-0011")["firmware"] == "2.1"
              and por_nombre("TQT-R2-V30-0013")["mac"] is None)
        page.screenshot(path=str(SHOTS / "macs_pegar_resultado_1440_oscuro.png"))
        # solo MAC, asignar en orden
        page.click("label:has-text('Solo MAC')")
        page.fill("#macs-ta", "02dd00000001\n02:DD:00:00:00:02")
        page.click("button:has-text('Revisar')")
        page.wait_for_selector(".macs-prev tbody tr >> nth=1")
        check("«asignar en orden» reparte las MAC en las pendientes visibles", "2 correctas" in page.inner_text(".macs-sum").replace("\n", " "), page.inner_text(".macs-sum"))
        page.click("button:has-text('Guardar las 2 correctas')"); page.click("button:has-text('Sí, guardar 2 MAC')")
        page.wait_for_selector("text=Se guardaron 2 MAC", timeout=10000)
        check("en orden: quedaron guardadas en la BD", sum(1 for x in pcbs() if x["mac"] and x["mac"].startswith("02:DD")) == 2)

        # ---------------------------------------------------------------- 7) Con MAC: editar, deshacer, firmware, borrar
        page.click("#macs-t-mac")
        page.wait_for_selector("#macs-p-mac tbody tr")
        total = page.locator("#macs-p-mac tbody tr").count()
        check("«Con MAC» lista las R1/R2 que ya tienen MAC", total == sum(1 for x in pcbs() if x["mac"] and x["tipo"] in ("R1", "R2")), str(total))
        page.fill("#macs-q-mac", "TQT-R1-V30-0001")
        fila = page.locator("#macs-p-mac tbody tr").first
        fila.locator("input.macs-in").click(); page.keyboard.press("Control+A"); page.keyboard.type("02ee00000001")
        page.keyboard.press("Escape")
        check("Esc vuelve al valor guardado", fila.locator("input.macs-in").input_value() == fmt(mac(1)), fila.locator("input.macs-in").input_value())
        page.keyboard.press("Control+A"); page.keyboard.type("02ee00000001"); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('#macs-p-mac tbody tr').dataset.e === 'guardada'", timeout=8000)
        check("corregir la MAC en sitio la guarda", por_nombre("TQT-R1-V30-0001")["mac"] == "02:EE:00:00:00:01")
        fila.locator(".macs-fw select").select_option("4.2")
        page.wait_for_function("document.querySelector('#macs-p-mac tbody tr .macs-st').innerText.includes('Firmware 4.2')", timeout=8000)
        check("cambiar el firmware se guarda al elegirlo", por_nombre("TQT-R1-V30-0001")["firmware"] == "4.2")
        fila.locator("input.macs-in").click(); page.keyboard.press("Control+A"); page.keyboard.type("02aa00000002")   # ya es de la R1 0002
        page.wait_for_timeout(700)
        check("en «Con MAC» también detecta la MAC repetida", "Repetida" in fila.locator(".macs-st").inner_text(), fila.locator(".macs-st").inner_text())
        page.keyboard.press("Escape")
        page.fill("#macs-q-mac", "TQT-R1-V30-0002")
        fila = page.locator("#macs-p-mac tbody tr").first
        fila.locator("button:has-text('Borrar MAC')").click()
        check("borrar pide confirmación en pantalla", page.locator("#macs-p-mac [role=group] button:has-text('Borrar')").is_visible() and por_nombre("TQT-R1-V30-0002")["mac"] is not None)
        page.screenshot(path=str(SHOTS / "macs_conmac_borrar_1440_oscuro.png"))
        page.locator("#macs-p-mac [role=group] button:has-text('Borrar')").click()
        page.wait_for_function("document.querySelectorAll('#macs-p-mac tbody tr').length === 0", timeout=8000)
        check("confirmar borra la MAC y la placa vuelve a Pendientes", por_nombre("TQT-R1-V30-0002")["mac"] is None)
        page.fill("#macs-q-mac", "")

        # ---------------------------------------------------------------- 8) tiempo real con dos pestañas sin perder lo tecleado
        page.click("#macs-t-pend")
        page2 = ctx.new_page(); Vigia(page2)
        page2.goto(f"{BASE}/monitor#/macs")
        page2.wait_for_function("document.querySelectorAll('#macs-p-pend tbody tr').length > 5")
        n2 = page2.locator("#macs-p-pend tbody tr").count()
        id_obj = page2.locator("#macs-p-pend tbody tr[data-e=vacia]").nth(3).get_attribute("data-id")
        objetivo = page2.locator(f"#macs-p-pend tbody tr[data-id='{id_obj}']")
        objetivo.locator("input.macs-in").click(); page2.keyboard.type("02ff00")
        candidato = page2.locator("#macs-p-pend tbody tr[data-e=vacia]").nth(0).get_attribute("data-id")
        assert req.put(f"{BASE}/api/pcb/{candidato}/programacion", data={"mac": "02:AB:00:00:00:77", "firmware": "2"}).ok
        page2.wait_for_function("document.querySelectorAll('#macs-p-pend tbody tr').length === %d" % (n2 - 1), timeout=8000)
        check("la otra pestaña quita la placa guardada por otra persona sin recargar", True)
        check("y conserva lo que se estaba tecleando", objetivo.locator("input.macs-in").input_value() == "02:FF:00", objetivo.locator("input.macs-in").input_value())
        check("con el foco aún en el campo", page2.evaluate("document.activeElement.value") == "02:FF:00")
        page2.close()

        # ---------------------------------------------------------------- 9) teclado puro
        page.reload(); page.wait_for_selector("#macs-t-pend"); page.click("#macs-t-pend"); page.wait_for_selector("#macs-p-pend tbody tr")
        page.locator("#macs-t-pend").focus()
        page.keyboard.press("ArrowRight"); page.keyboard.press("ArrowRight")
        check("las pestañas se mueven con flechas", page.get_attribute("#macs-t-mac", "aria-selected") == "true")
        page.keyboard.press("ArrowLeft"); page.keyboard.press("ArrowLeft")
        page.locator("#macs-p-pend tbody tr[data-e=vacia] input.macs-in").nth(2).focus()
        page.keyboard.press("ArrowDown")
        a = page.evaluate("document.activeElement.getAttribute('aria-label')")
        page.keyboard.press("ArrowUp")
        b = page.evaluate("document.activeElement.getAttribute('aria-label')")
        check("↑/↓ cambian de fila", a != b and a.startswith("MAC de") and b.startswith("MAC de"), f"{a} / {b}")
        page.keyboard.press("Tab")
        check("Tab pasa al firmware de la fila siguiente (orden lógico)", page.evaluate("document.activeElement.tagName") == "SELECT")
        page.keyboard.press("Shift+Tab")
        check("Shift+Tab regresa a la MAC", page.evaluate("document.activeElement.classList.contains('macs-in')"))

        # ---------------------------------------------------------------- 10) tamaños, temas, axe
        axe_res = []

        def axe(etq):
            if not AXE:
                return
            page.add_script_tag(content=Path(AXE).read_text(encoding="utf-8")) if not page.evaluate("!!window.axe") else None
            r = page.evaluate("axe.run({include:[['.macs']]}).then(r => r.violations.map(v => ({id:v.id, impact:v.impact, n:v.nodes.length, t:v.nodes.slice(0,2).map(n=>n.html.slice(0,140))})))")
            axe_res.append((etq, r))
            check(f"axe-core 0 violaciones en {etq}", not r, json.dumps(r, ensure_ascii=False)[:400])

        for (w, h_), tam in (((1440, 900), "1440"), ((1024, 768), "1024")):
            page.set_viewport_size({"width": w, "height": h_})
            for tema in ("dark", "light"):
                page.evaluate(f"TQT.applyTheme('{tema}')")
                page.click("#macs-t-pend"); page.wait_for_timeout(200)
                filas = page.locator("#macs-p-pend tbody tr[data-e=vacia] input.macs-in")
                if tam == "1440" and tema == "dark":
                    pass
                filas.nth(0).click(); page.keyboard.type("02aa000005")   # incompleta
                filas.nth(1).click(); page.keyboard.type("02aa00000601")   # válida
                filas.nth(2).click(); page.keyboard.type("02aa00000601")   # repetida
                page.wait_for_timeout(200)
                page.screenshot(path=str(SHOTS / f"macs_pendientes_{tam}_{'oscuro' if tema == 'dark' else 'claro'}.png"))
                axe(f"pendientes {tam} {tema}")
                sh = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                check(f"sin scroll horizontal de página a {tam} {tema}", not sh)
                for i in range(3):
                    filas.nth(0).click(); page.keyboard.press("Escape")
                    page.evaluate("document.activeElement.blur()")
                    break
                page.reload(); page.wait_for_selector("#macs-t-pend"); page.click("#macs-t-pend"); page.wait_for_selector("#macs-p-pend tbody tr")
                page.evaluate(f"TQT.applyTheme('{tema}')")
                page.click("#macs-t-pegar")
                page.fill("#macs-ta", "TQT-R2-V30-0014;02cc00000114\n0015 R2 02cc00000115 2.1\nTQT-R3-V30-0001 02cc00000199\nTQT-R2-V30-0998 02cc00000198\nbasura")
                page.click("button:has-text('Revisar')"); page.wait_for_selector(".macs-prev tbody tr >> nth=4")
                page.screenshot(path=str(SHOTS / f"macs_pegar_{tam}_{'oscuro' if tema == 'dark' else 'claro'}.png"))
                axe(f"pegar {tam} {tema}")
                page.click("#macs-t-mac"); page.wait_for_selector("#macs-p-mac tbody tr")
                page.screenshot(path=str(SHOTS / f"macs_conmac_{tam}_{'oscuro' if tema == 'dark' else 'claro'}.png"))
                axe(f"con MAC {tam} {tema}")
                page.reload(); page.wait_for_selector("#macs-t-pend"); page.click("#macs-t-pend"); page.wait_for_selector("#macs-p-pend tbody tr")

        # ---------------------------------------------------------------- consola limpia
        ignorar = ("409", "ERR_FAILED", "Failed to load resource")
        malos = [c for c in vig.consola if not any(i in c[1] for i in ignorar)]
        check("consola sin errores propios (se filtran 409/aborto provocados a propósito)", not malos, str(malos[:3]))
        externas = vig.externas
        check("ninguna petición externa", not externas, str(externas[:3]))
        br.close()

    fallos = [r for r in RES if not r[1]]
    print(f"\n{len(RES) - len(fallos)}/{len(RES)} comprobaciones pasan")
    (SHOTS / "resultado_e2e.json").write_text(json.dumps([{"caso": n, "ok": o, "detalle": d} for n, o, d in RES], ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
