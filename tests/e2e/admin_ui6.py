"""QA /admin: cambiar contraseña desde la UI + semántica variable de entorno vs clave guardada (reinicia el contenedor qa-admin).
Tras correr esto la clave de qa-admin queda como TQT_ADMIN_PASSWORD (ClaveDePrueba-123)."""
import os
import subprocess
import time
import requests
import urllib3
from playwright.sync_api import sync_playwright
from util import *
from admin_ui2 import chk, res, IMG, PW

urllib3.disable_warnings()
M = BASE
NUEVA = "NuevaClave-2026"
ENV = dict(os.environ, MSYS_NO_PATHCONV="1")


def login(pw, base=M):
    return requests.post(base + "/api/admin/login", json={"password": pw}, verify=False)


def relanzar(clave_env):
    subprocess.run(["docker", "rm", "-f", "qa-admin"], capture_output=True, env=ENV)
    subprocess.run(["docker", "run", "-d", "--name", "qa-admin", "-p", "8460:8443", "-e", "TQT_HOST_IP=192.168.3.36", "-e", f"TQT_ADMIN_PASSWORD={clave_env}",
                    "-e", "TQT_BACKUP_DIR=/backups", "-v", "qa_admin_db:/data/db", "qa-admin-img"], capture_output=True, env=ENV, check=True)
    for _ in range(40):
        time.sleep(1.5)
        try:
            if requests.get(M + "/api/admin/estado", verify=False, timeout=2).ok:
                return
        except Exception:
            pass


with sync_playwright() as p:
    br, ctx = lanzar(p, viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    vg = Vigia(pg)
    pg.goto(M + "/admin", wait_until="networkidle")
    pg.fill("#pass", PW)
    pg.press("#pass", "Enter")
    pg.wait_for_selector("#adminView:not([hidden])")
    viejo = pg.evaluate("JSON.parse(sessionStorage.getItem('tqt.admin')).t")
    pg.click("[data-v=cuenta]")

    def enviar(a, n, r):
        pg.fill("#cActual", a)
        pg.fill("#cNueva", n)
        pg.fill("#cRep", r)
        pg.click("#btnClave")
        pg.wait_for_timeout(1200)
        return pg.inner_text("#cErr")

    e = enviar("", NUEVA, NUEVA)
    chk("6 sin clave actual", "actual" in e, e)
    e = enviar("incorrecta-1", NUEVA, NUEVA)
    chk("6 clave actual incorrecta: mensaje en español", "no es correcta" in e, e)
    e = enviar(PW, "corta", "corta")
    chk("6 nueva < 8 caracteres", "8 caracteres" in e, e)
    e = enviar(PW, NUEVA, "otra-distinta")
    chk("6 confirmación distinta", "no coincide" in e, e)
    e = enviar(PW, PW, PW)
    chk("6 nueva igual a la actual", "distinta" in e, e)
    pg.screenshot(path=str(IMG / "50_cambiar_clave_error.png"))
    e = enviar(PW, NUEVA, NUEVA)
    chk("6 clave válida: 'Contraseña actualizada'", "actualizada" in e, e)
    pg.screenshot(path=str(IMG / "51_cambiar_clave_ok.png"))
    nuevo = pg.evaluate("JSON.parse(sessionStorage.getItem('tqt.admin')).t")
    chk("6 la UI adoptó un token nuevo", nuevo != viejo)
    r = requests.get(M + "/api/admin/resumen", headers={"X-Admin-Token": viejo}, verify=False)
    chk("6 el token viejo ya no sirve (401)", r.status_code == 401, r.text[:80])
    pg.click("[data-v=resumen]")
    pg.wait_for_timeout(300)
    pg.click("[data-v=tarjetas]")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1500)
    chk("6 tras cambiar y recargar sigue dentro (token nuevo válido)", pg.is_visible("#adminView"))
    chk("6 login con la nueva funciona; con la vieja no", login(NUEVA).status_code == 200 and login(PW).status_code == 401)
    pg.click("#btnLogout")
    br.close()

# semántica variable de entorno vs BD
print("--- reinicio con la MISMA variable (ClaveDePrueba-123)")
relanzar(PW)
a, b = login(NUEVA).status_code, login(PW).status_code
print(f"   tras reiniciar: nueva(UI)={a} original(env)={b}")
chk("6 la clave cambiada desde la UI SOBREVIVE a un reinicio con la misma variable", a == 200 and b == 401)
print("--- reinicio con la variable CAMBIADA (OtraEnv-2027)")
relanzar("OtraEnv-2027")
a, b, c = login("OtraEnv-2027").status_code, login(NUEVA).status_code, login(PW).status_code
print(f"   env nueva={a} clave de la UI={b} env vieja={c}")
chk("6 cambiar la variable y reiniciar restablece la clave (gana la variable)", a == 200 and b == 401 and c == 401)
print("--- vuelta a la variable original")
relanzar(PW)
chk("6 con la variable original vuelve ClaveDePrueba-123", login(PW).status_code == 200 and login("OtraEnv-2027").status_code == 401)
print(f"{sum(res)}/{len(res)} OK")
