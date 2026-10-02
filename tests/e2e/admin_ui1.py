"""QA /admin: arranque sin sesión, sessionStorage manipulado y login. TQT_BASE=https://localhost:8460 TQT_ADMIN_PASSWORD=ClaveDePrueba-123"""
import base64, json, os, sys, time
from playwright.sync_api import sync_playwright
from util import *

PW = os.environ.get("TQT_ADMIN_PASSWORD", "ClaveDePrueba-123")
IMG = RAIZ / "docs" / "qa" / "admin_img"; IMG.mkdir(parents=True, exist_ok=True)
res = []
def chk(nombre, ok, extra=""):
    res.append(ok); print(("OK   " if ok else "FALLA"), nombre, extra)

def tok(exp, firma="x"):
    c = base64.urlsafe_b64encode(json.dumps({"exp": exp, "iat": exp - 1800, "v": "0", "n": "1"}).encode()).decode().rstrip("=")
    return f"{c}.{firma}"

def estado(pg):
    return pg.evaluate("()=>({login:!document.getElementById('loginView').hidden,admin:!document.getElementById('adminView').hidden,err:document.getElementById('loginErr').hidden?'':document.getElementById('loginErr').innerText})")

def con_storage(ctx, valor):
    pg = ctx.new_page(); vg = Vigia(pg)
    pg.goto(BASE + "/admin", wait_until="domcontentloaded")
    pg.evaluate("v=>{if(v===null)sessionStorage.clear();else sessionStorage.setItem('tqt.admin',v)}", valor)
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(500)
    return pg, vg

with sync_playwright() as p:
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844})
    pg = ctx.new_page(); vg = Vigia(pg)
    pg.goto(BASE + "/admin", wait_until="networkidle"); pg.wait_for_timeout(400)
    e = estado(pg); chk("1 sin sesión: solo login", e["login"] and not e["admin"])
    txt = pg.inner_text("body"); chk("1 sin sesión: ningún dato", not any(k in txt for k in ("TQT-R", "Tarjetas", "LOTE", "2026-09")), repr(txt[:80]))
    pg.screenshot(path=str(IMG / "01_login.png"))
    fut = int(time.time()) + 900
    for nombre, valor in [("token basura", json.dumps({"t": "basura", "e": fut * 1000})),
                          ("token caducado", json.dumps({"t": tok(int(time.time()) - 60), "e": (fut) * 1000})),
                          ("e futuro token firma falsa", json.dumps({"t": tok(fut), "e": fut * 1000})),
                          ("JSON roto", "{no"), ("e sin token", json.dumps({"e": fut * 1000})), ("vacío", None)]:
        pg2, vg2 = con_storage(ctx, valor); e = estado(pg2)
        chk(f"1 storage {nombre}: login y sin panel", e["login"] and not e["admin"], e["err"][:60])
        chk(f"1 storage {nombre}: sin datos en pantalla", "TQT-R" not in pg2.inner_text("body"))
        pg2.close()
    # validación con el servidor ANTES de enseñar el panel (resumen lento, token válido)
    pg3 = ctx.new_page(); pg3.goto(BASE + "/admin", wait_until="networkidle")
    tk = pg3.evaluate("async pw=>{const r=await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});return (await r.json()).token}", PW)
    pg3.evaluate("v=>sessionStorage.setItem('tqt.admin',v)", json.dumps({"t": tk, "e": 1}))  # e manipulado (pasado): el token manda
    pg3.close()
    pg4 = ctx.new_page(); pg4.route("**/api/admin/resumen", lambda r: (time.sleep(1.5), r.continue_()))
    pg4.goto(BASE + "/admin", wait_until="domcontentloaded")
    pg4.evaluate("v=>sessionStorage.setItem('tqt.admin',v)", json.dumps({"t": tk, "e": 1}))
    pg4.reload(wait_until="commit"); pg4.wait_for_timeout(700)
    e = estado(pg4); chk("1 token válido: el panel NO aparece hasta que el servidor valida", not e["admin"], str(e))
    pg4.wait_for_timeout(2500); e = estado(pg4); chk("1 token válido: tras validar aparece el panel (e manipulado ignorado)", e["admin"], str(e))
    pg4.close()
    # login
    pg = ctx.new_page(); vg = Vigia(pg); pg.goto(BASE + "/admin", wait_until="networkidle"); pg.evaluate("sessionStorage.clear()"); pg.reload(wait_until="networkidle")
    pg.click("#btnLogin"); e = estado(pg); chk("2 clave vacía: mensaje", "Escribe la contraseña" in e["err"], e["err"])
    pg.fill("#pass", "   "); pg.click("#btnLogin"); e = estado(pg); chk("2 solo espacios: mensaje sin llamar", "Escribe la contraseña" in e["err"], e["err"])
    pg.fill("#pass", "incorrecta1"); pg.click("#btnLogin"); pg.wait_for_timeout(900); e = estado(pg)
    chk("2 clave incorrecta: mensaje claro y sigue en login", e["login"] and "incorrecta" in e["err"].lower(), e["err"]); pg.screenshot(path=str(IMG / "02_login_error.png"))
    pg.fill("#pass", PW + " "); pg.press("#pass", "Enter"); pg.wait_for_timeout(900); e = estado(pg)
    chk("2 clave con espacio final: rechazada", e["login"] and not e["admin"], e["err"])
    pg.fill("#pass", PW); pg.press("#pass", "Enter"); pg.wait_for_timeout(2500); e = estado(pg)
    chk("2 Enter con clave correcta entra", e["admin"] and not e["login"])
    chk("2 token no en URL ni localStorage", "token" not in pg.url and pg.evaluate("Object.keys(localStorage).join()") .find("admin") < 0)
    print("consola:", vg.consola, "http:", vg.http)
    pg.screenshot(path=str(IMG / "03_resumen_390.png"), full_page=True)
    print("logout"); pg.click("#btnLogout"); pg.wait_for_timeout(600); e = estado(pg); chk("7 cerrar sesión -> login, sin datos", e["login"] and "TQT-R" not in pg.inner_text("body") and pg.evaluate("sessionStorage.getItem('tqt.admin')") is None)
    pg.fill("#pass", PW); pg.click("#btnLogin"); pg.wait_for_timeout(2000); chk("2 botón con clave correcta entra", estado(pg)["admin"])
    br.close()
print(f"{sum(res)}/{len(res)} OK")
