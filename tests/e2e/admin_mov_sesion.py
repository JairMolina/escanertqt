"""QA cierre de sesion de /admin (todos los caminos). TQT_BASE=https://127.0.0.1:8463 TQT_ADMIN_PASSWORD=ClaveQA-12345
Modo 'repro' (argumento) solo describe lo que pasa; sin argumento comprueba el flujo correcto."""
import os, sys
from playwright.sync_api import sync_playwright
from util import *

PW = os.environ.get("TQT_ADMIN_PASSWORD", "ClaveQA-12345")
IMG = RAIZ / "docs" / "qa" / "admin_mov_img"; IMG.mkdir(parents=True, exist_ok=True)
res = []
def chk(n, ok, extra=""):
    res.append(ok); print(("OK   " if ok else "FALLA"), n, extra)

def vista(pg):
    return pg.evaluate("()=>({login:!document.getElementById('loginView').hidden,admin:!document.getElementById('adminView').hidden,"
                       "form:!!document.getElementById('loginForm') && document.getElementById('loginForm').offsetParent!==null,"
                       "url:location.pathname+location.search,txt:document.getElementById('loginView').innerText})")

def entrar(pg, ruta="/admin"):
    pg.goto(BASE + ruta, wait_until="networkidle"); pg.wait_for_timeout(300)
    pg.fill("#pass", PW); pg.press("#pass", "Enter"); pg.wait_for_selector("#adminView:not([hidden])", timeout=8000)

with sync_playwright() as p:
    br, ctx = lanzar(p, viewport={"width": 1280, "height": 800})
    pg = ctx.new_page(); vg = Vigia(pg)
    entrar(pg)
    print("href logo:", pg.get_attribute(".brand", "href"))
    pg.click("#btnLogout"); pg.wait_for_timeout(700)
    v = vista(pg); print("tras cerrar:", v["url"], v["txt"][:120].replace("\n", " | "))
    cookies = [c["name"] for c in ctx.cookies()]
    chk("cookie tqt_admin borrada tras cerrar", "tqt_admin" not in cookies, str(cookies))
    if len(sys.argv) > 1:
        pg.click("#loginForm a.btn-ghost"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(400)
        v = vista(pg); print("tras 'Cancelar':", v["url"], "login visible:", v["login"], "|", v["txt"][:90].replace("\n", " | "))
        br.close(); sys.exit()
    chk("muestra 'Sesión cerrada' (no error)", "Sesión cerrada" in v["txt"] and pg.locator("#loginErr").is_hidden())
    chk("salida 'Ir al escáner' -> /", pg.get_attribute("#cerradaEscaner", "href") == "/")
    chk("salida 'Volver a entrar' visible", pg.locator("#cerradaVolver").is_visible())
    chk("sin formulario de login encadenado", not v["form"])
    chk("sin datos en el DOM", "TQT-R" not in pg.inner_text("body") and pg.evaluate("sessionStorage.getItem('tqt.admin')") is None)
    pg.screenshot(path=str(IMG / "sesion_cerrada_1280.png"))
    # /monitor tras cerrar -> un solo login con motivo
    pg.goto(BASE + "/monitor", wait_until="networkidle"); v = vista(pg)
    chk("monitor sin sesion -> /admin?next=/monitor", v["url"] == "/admin?next=/monitor", v["url"])
    chk("motivo del monitor visible", "contraseña de supervisor" in v["txt"], v["txt"][:200].replace("\n", " | "))
    chk("un solo login (formulario visible, sin 'Sesión cerrada')", v["form"] and "Sesión cerrada" not in v["txt"])
    pg.screenshot(path=str(IMG / "login_next_monitor_1280.png"))
    pg.fill("#pass", PW); pg.press("#pass", "Enter"); pg.wait_for_url("**/monitor", timeout=8000)
    chk("login correcto vuelve a /monitor", pg.url.endswith("/monitor"))
    # otro next -> ignorado
    pg.goto(BASE + "/admin?next=//evil.com", wait_until="networkidle"); pg.wait_for_timeout(400)
    v = vista(pg); chk("next hostil: pide login sin motivo de monitor", v["login"] and "supervisor" not in v["txt"])
    # volver a entrar desde la pantalla de cierre
    pg2 = ctx.new_page(); entrar(pg2)
    pg2.click("#btnLogout"); pg2.wait_for_timeout(600); pg2.click("#cerradaVolver"); pg2.wait_for_timeout(200)
    v = vista(pg2); chk("Volver a entrar muestra el formulario", v["form"] and pg2.evaluate("document.activeElement.id") == "pass")
    pg2.fill("#pass", PW); pg2.press("#pass", "Enter"); pg2.wait_for_selector("#adminView:not([hidden])", timeout=8000)
    chk("re-login correcto entra al panel", True)
    # logo -> escaner
    pg2.click(".brand"); pg2.wait_for_load_state("networkidle")
    chk("logo lleva a / (escáner), no a login", pg2.url.rstrip("/") == BASE.rstrip("/"), pg2.url)
    # Atras tras cerrar sesion
    pg3 = ctx.new_page(); entrar(pg3)
    pg3.goto(BASE + "/", wait_until="networkidle"); pg3.goto(BASE + "/admin", wait_until="networkidle"); pg3.wait_for_selector("#adminView:not([hidden])", timeout=8000)
    pg3.click("#btnLogout"); pg3.wait_for_timeout(600); pg3.go_back(); pg3.wait_for_load_state("networkidle"); pg3.go_forward(); pg3.wait_for_load_state("networkidle"); pg3.wait_for_timeout(500)
    v = vista(pg3); chk("Atrás/Adelante tras cerrar: sin datos ni panel", not v["admin"] and "TQT-R" not in pg3.inner_text("body"), v["url"])
    # monitor abierto en otra pestaña, cerrar en admin
    a = ctx.new_page(); entrar(a)
    m = ctx.new_page(); m.goto(BASE + "/monitor", wait_until="networkidle"); m.wait_for_timeout(500)
    chk("monitor abre con sesión", m.url.endswith("/monitor"))
    a.click("#btnLogout"); a.wait_for_timeout(600)
    m.reload(wait_until="networkidle"); v = vista(m)
    chk("monitor tras cerrar: un solo login con motivo", m.url.endswith("/admin?next=/monitor") and v["form"] and "supervisor" in v["txt"], m.url)
    # cerrar en una pestaña admin cierra las demás admin
    x = ctx.new_page(); entrar(x); y = ctx.new_page(); entrar(y)
    x.click("#btnLogout"); y.wait_for_timeout(800)
    chk("otra pestaña de admin también sale", not vista(y)["admin"])
    # sesion caducada: token invalido a mitad
    z = ctx.new_page(); entrar(z)
    z.evaluate("()=>sessionStorage.setItem('tqt.admin', JSON.stringify({t:'x.y', e:9e12}))"); z.reload(wait_until="networkidle"); z.wait_for_timeout(600)
    v = vista(z); chk("token roto -> un solo login, sin panel", v["login"] and not v["admin"] and v["form"])
    print("consola:", vg.consola[:3], "http:", vg.http[:3])
    br.close()
print(f"{sum(res)}/{len(res)} OK")
