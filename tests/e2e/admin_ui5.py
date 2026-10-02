"""QA /admin: admin deshabilitado (8462), caducidad real de 8 s y bloqueo tras 5 fallos (8461), cadena ?next=/monitor y cookie (8460).
Contenedores: qa-admin (8460, clave ClaveDePrueba-123), qa-admin2 (8461, TQT_ADMIN_TOKEN_TTL=8), qa-admin3 (8462, sin clave)."""
import os
import requests
import urllib3
from playwright.sync_api import sync_playwright
from util import *
from admin_ui2 import chk, res, IMG, PW

urllib3.disable_warnings()
H = "https://localhost"
U = {"main": f"{H}:8460", "ttl": f"{H}:8461", "off": f"{H}:8462"}


def estado(pg):
    return pg.evaluate("()=>({login:!document.getElementById('loginView').hidden,admin:!document.getElementById('adminView').hidden})")


with sync_playwright() as p:
    br, ctx = lanzar(p, viewport={"width": 390, "height": 844})
    # ---- 1. admin deshabilitado
    pg = ctx.new_page()
    vg = Vigia(pg)
    pg.goto(U["off"] + "/admin", wait_until="networkidle")
    pg.wait_for_timeout(500)
    msg = pg.inner_text("#loginErr")
    chk("1 deshabilitado: mensaje claro y formulario bloqueado", "TQT_ADMIN_PASSWORD" in msg and pg.is_disabled("#btnLogin") and pg.is_disabled("#pass") and not estado(pg)["admin"], msg[:90])
    pg.screenshot(path=str(IMG / "40_admin_deshabilitado.png"))
    s = requests.Session()
    s.verify = False
    codes = {r: s.get(U["off"] + r).status_code for r in ("/api/admin/resumen", "/api/admin/export/excel")}
    codes["reset"] = s.post(U["off"] + "/api/admin/reset", json={"confirmar": "BORRAR TODO"}).status_code
    codes["login"] = s.post(U["off"] + "/api/admin/login", json={"password": "cualquiera123"}).status_code
    chk("1 deshabilitado: API admin 503", set(codes.values()) == {503}, str(codes))
    chk("1 deshabilitado: /monitor abierto y POST /api/lotes sin sesión permitido", s.get(U["off"] + "/monitor", allow_redirects=False).status_code == 200 and s.post(U["off"] + "/api/lotes", json={"codigo_lote": "OFF-1", "mes": 3, "anio": 2027, "crear_excel": False, "activo": False}).status_code == 201)
    pg.evaluate("sessionStorage.setItem('tqt.admin', JSON.stringify({t:'x.y', e: Date.now()+9e5}))")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    chk("1 deshabilitado + storage falso: sigue sin panel", not estado(pg)["admin"])
    pg.close()

    # ---- 7. caducidad real (TTL 8 s)
    pg = ctx.new_page()
    pg.goto(U["ttl"] + "/admin", wait_until="networkidle")
    pg.fill("#pass", PW)
    pg.press("#pass", "Enter")
    pg.wait_for_selector("#adminView:not([hidden])")
    pg.wait_for_timeout(1500)
    tk = pg.evaluate("JSON.parse(sessionStorage.getItem('tqt.admin')).t")
    chk("7 TTL 8 s: la sesión mostrada es la del token (<= 0:08)", pg.inner_text("#sesion") in ("Sesión 0:07", "Sesión 0:06", "Sesión 0:08", "Sesión 0:05"), pg.inner_text("#sesion"))
    pg.wait_for_timeout(8000)
    chk("7 TTL 8 s: al caducar vuelve al login con mensaje", estado(pg)["login"] and "caduc" in pg.inner_text("#loginErr") and "TQT-R" not in pg.inner_text("body"), pg.inner_text("#loginErr"))
    r = requests.get(U["ttl"] + "/api/admin/resumen", headers={"X-Admin-Token": tk}, verify=False)
    chk("7 el servidor también rechaza el token caducado (401)", r.status_code == 401, r.text[:80])
    # recarga con ese token caducado guardado: login
    pg.evaluate("t=>sessionStorage.setItem('tqt.admin', JSON.stringify({t, e: Date.now()+9e5}))", tk)
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    chk("1 token caducado en storage con e futuro: login", estado(pg)["login"] and not estado(pg)["admin"])

    # ---- 2. bloqueo tras 5 fallos
    for i in range(5):
        pg.fill("#pass", f"mala-clave-{i}")
        pg.press("#pass", "Enter")
        pg.wait_for_timeout(900)
        if i < 4:
            pg.wait_for_function("()=>!document.getElementById('btnLogin').disabled", timeout=8000)
    m = pg.inner_text("#loginErr")
    chk("2 5.º fallo: mensaje de bloqueo con tiempo restante", "Demasiados intentos" in m and "300" in m or "299" in m, m)
    btxt = pg.inner_text("#btnLogin")
    chk("2 botón deshabilitado con cuenta atrás", pg.is_disabled("#btnLogin") and "Espera" in btxt, btxt)
    pg.wait_for_timeout(2500)
    chk("2 la cuenta atrás avanza", "Espera" in pg.inner_text("#btnLogin") and int(pg.inner_text("#btnLogin").split()[1]) < 298, pg.inner_text("#btnLogin"))
    pg.screenshot(path=str(IMG / "41_bloqueo.png"))
    r = requests.post(U["ttl"] + "/api/admin/login", json={"password": PW}, verify=False)
    chk("2 bloqueado: ni la clave correcta entra (429 + Retry-After)", r.status_code == 429 and int(r.headers.get("Retry-After", 0)) > 0, f"{r.status_code} {r.headers.get('Retry-After')}")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    pg.fill("#pass", PW)
    pg.press("#pass", "Enter")
    pg.wait_for_timeout(1200)
    m = pg.inner_text("#loginErr")
    print("   tras recargar bloqueado y probar clave correcta:", m, "| botón:", pg.inner_text("#btnLogin"), "| deshabilitado:", pg.is_disabled("#btnLogin"))
    chk("2 tras recargar sigue bloqueado con el mensaje del servidor", "Demasiados intentos" in m and not estado(pg)["admin"])
    pg.close()

    # ---- cadena ?next=/monitor y cookie (contenedor principal)
    M = U["main"]
    s = requests.Session()
    s.verify = False
    r = s.get(M + "/monitor", allow_redirects=False)
    chk("d /monitor sin sesión: 302 a /admin?next=/monitor", r.status_code == 302 and r.headers["location"] == "/admin?next=/monitor", f"{r.status_code} {r.headers.get('location')}")
    chk("d POST /api/lotes sin sesión: 401", s.post(M + "/api/lotes", json={"codigo_lote": "CK-1", "mes": 4, "anio": 2027, "crear_excel": False, "activo": False}).status_code == 401)
    lg = s.post(M + "/api/admin/login", json={"password": PW})
    ck = lg.headers.get("set-cookie", "")
    chk("d login fija cookie HttpOnly; Secure; SameSite=Strict", "tqt_admin=" in ck and "HttpOnly" in ck and "Secure" in ck and "SameSite=strict" in ck.replace("Strict", "strict"), ck[:200])
    chk("d con cookie: POST /api/lotes 201 y /monitor 200", s.post(M + "/api/lotes", json={"codigo_lote": "CK-1", "mes": 4, "anio": 2027, "crear_excel": False, "activo": False}).status_code == 201 and s.get(M + "/monitor", allow_redirects=False).status_code == 200)
    pg = ctx.new_page()
    vg = Vigia(pg)
    pg.goto(M + "/monitor", wait_until="networkidle")
    chk("d navegador: /monitor sin sesión acaba en /admin?next=/monitor", pg.url.endswith("/admin?next=/monitor"), pg.url)
    pg.fill("#pass", PW)
    pg.press("#pass", "Enter")
    pg.wait_for_url("**/monitor", timeout=15000)
    pg.wait_for_timeout(1500)
    chk("d tras login vuelve al monitor y carga datos", pg.url.endswith("/monitor") and "Administración" not in pg.title() and vg.http == [] or not [h for h in vg.http if h[0] >= 500], f"{pg.url} {vg.http}")
    pg.screenshot(path=str(IMG / "42_monitor_tras_login.png"))
    # ya con sesión: abrir /admin?next=/monitor redirige
    pg.goto(M + "/admin?next=/monitor", wait_until="commit")
    pg.wait_for_timeout(2500)
    print("   con sesión abierta y /admin?next=/monitor ->", pg.url)
    # next hostil
    for n in ("//evil.com", "https://evil.com", "/monitor%0d%0a", "/otra", "javascript:alert(1)"):
        pg.goto(M + "/admin?next=" + n, wait_until="networkidle")
        pg.wait_for_timeout(1500)
        host_ok = pg.url.startswith(M)
        chk(f"d next hostil {n!r}: se queda en el sitio", host_ok and "evil" not in pg.url.split("?")[0], pg.url)
    pg.goto(M + "/admin", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    print("   /admin sin next con sesión:", estado(pg))
    if estado(pg)["admin"]:
        pg.click("#btnLogout")
        pg.wait_for_timeout(700)
    r = pg.evaluate("fetch('/monitor',{redirect:'manual'}).then(r=>r.type+' '+r.status)")
    chk("d tras cerrar sesión /monitor vuelve a redirigir (cookie borrada)", "opaqueredirect" in r or "302" in r, r)
    print("   cookies:", [c["name"] for c in ctx.cookies()])
    br.close()
print(f"{sum(res)}/{len(res)} OK")
