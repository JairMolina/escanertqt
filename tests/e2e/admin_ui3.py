"""QA /admin: acciones destructivas de verdad (borra datos del servidor de PRUEBA).
TQT_BASE=https://localhost:8460 QA_CONTENEDOR=qa-admin python admin_ui3.py"""
import json
import os
import sqlite3
import subprocess
import tempfile
import urllib3
from playwright.sync_api import sync_playwright
from util import *
from admin_ui2 import entrar, filas, chk, res, api, IMG, PW

urllib3.disable_warnings()
CT = os.environ.get("QA_CONTENEDOR", "qa-admin")
ENV = dict(os.environ, MSYS_NO_PATHCONV="1")


def respaldos():
    o = subprocess.run(["docker", "exec", CT, "ls", "/backups"], capture_output=True, text=True, env=ENV).stdout.split()
    return sorted(x for x in o if x.endswith(".db"))


def pcb_by(nombre):
    return next((x for x in api("/api/pcb?limit=5000")["items"] if x["nombre"] == nombre), None)


def tar(lote):
    return api(f"/api/tarjetas?limit=500&lote_id={lote}")["items"]


def sel_tarjetas(pg, nums):
    pg.click("[data-v=tarjetas]")
    pg.wait_for_timeout(300)
    pg.click("#tNone")
    for n in nums:
        pg.locator(f"#tTabla tr:has(td:text-is('{n}')) input[type=checkbox]").check()


def hoja(pg):
    return pg.locator(".sheet")


with sync_playwright() as p:
    br, ctx = lanzar(p)
    pg, vg = entrar(ctx)
    A, B = 1, 2
    r0 = respaldos()
    # 4a. eliminar 2 tarjetas CON devolver PCB
    sel_tarjetas(pg, ["0001", "0002"])
    chk("4 contador 2 seleccionadas", pg.inner_text("#tSel").startswith("2 seleccionadas"), pg.inner_text("#tSel"))
    pg.click("#tDel")
    pg.wait_for_selector(".sheet")
    pg.screenshot(path=str(IMG / "20_borrar_tarjetas.png"))
    chk("4 hoja: 'devolver PCB' marcada por defecto", pg.is_checked("#liberar"))
    pg.click(".sheet button:has-text('Cancelar')")
    chk("4 cancelar no borra nada", len(tar(A)) == 6 and len(respaldos()) == len(r0))
    pg.click("#tDel")
    pg.wait_for_selector(".sheet")
    pg.dblclick(".sheet .btn-danger")
    pg.wait_for_timeout(1800)
    rr = respaldos()
    chk("4 doble clic: un solo respaldo y una sola operación", len(rr) == len(r0) + 1 and len(tar(A)) == 4, f"resp={len(rr)-len(r0)} tarjetas={len(tar(A))}")
    for n in ("0001", "0002"):
        for t in ("R1", "R2", "R3"):
            x = pcb_by(f"TQT-{t}-V30-{n}")
            chk(f"4 liberar: {t}-{n} DISPONIBLE (estado_pcb={x and x['estado_pcb']}, mac={x and x['mac']})", x and x["estado_ciclo"] == "DISPONIBLE" and not x["tarjeta_id"])
    ban = pg.inner_text("#banner")
    chk("4 banner con respaldo", "Respaldo guardado" in ban and rr[-1] in ban, ban[:120])
    pg.screenshot(path=str(IMG / "21_tras_borrar.png"))
    # 4b. eliminar 2 SIN devolver PCB
    sel_tarjetas(pg, ["0003", "0004"])
    pg.click("#tDel")
    pg.wait_for_selector(".sheet")
    pg.uncheck("#liberar")
    pg.click(".sheet .btn-danger")
    pg.wait_for_timeout(1500)
    tot = api("/api/pcb?limit=1")["total"]
    chk("4 sin devolver: tarjetas 2 menos y PCB eliminadas", len(tar(A)) == 2 and pcb_by("TQT-R1-V30-0003") is None and pcb_by("TQT-R3-V30-0004") is None and tot == 84, str(tot))
    # 4c. eliminar PCB asignada (0005 R1)
    pg.click("[data-v=pcb]")
    pg.fill("#pQ", "TQT-R1-V30-0005")
    pg.wait_for_timeout(400)
    pg.locator("#pTabla tbody input[type=checkbox]").first.check()
    pg.click("#pDel")
    pg.wait_for_selector(".sheet")
    chk("4 eliminar PCB asignada: aviso de tarjeta incompleta", "incompleta" in hoja(pg).inner_text(), hoja(pg).inner_text()[:150])
    pg.screenshot(path=str(IMG / "22_borrar_pcb.png"))
    pg.click(".sheet .btn-danger")
    pg.wait_for_timeout(1500)
    t5 = next(t for t in tar(A) if t["id_tarjeta_num"] == "0005")
    chk("4 PCB asignada eliminada: tarjeta 0005 sin R1, no LIBERADA", pcb_by("TQT-R1-V30-0005") is None and not t5["nombre_r1"] and t5["estado_general"] != "LIBERADO", f"{t5['estado_general']} completa={t5['completa']}")
    pg.fill("#pQ", "")
    # 5. vaciar lote: palabra incorrecta
    pg.click("[data-v=riesgo]")
    pg.select_option("#vLote", str(B))
    pg.click("#btnVaciar")
    pg.wait_for_selector(".sheet")
    pg.screenshot(path=str(IMG / "23_vaciar.png"))
    btn = pg.locator(".sheet .btn-danger")
    for w in ("vaciar", "VACIA", "VACIAR X", ""):
        pg.fill("#palabra", w)
        chk(f"4 vaciar: '{w}' deja el botón deshabilitado", btn.is_disabled())
    n0 = len(respaldos())
    pg.fill("#palabra", "VACIAR")
    chk("4 vaciar: 'VACIAR' habilita", not btn.is_disabled())
    pg.route("**/api/admin/lote/*/vaciar", lambda r: r.abort())
    btn.click()
    pg.wait_for_timeout(800)
    chk("4 error de red: mensaje en español, hoja abierta, nada borrado", "Sin conexión" in hoja(pg).inner_text() and len(tar(B)) == 2 and len(respaldos()) == n0, hoja(pg).inner_text()[-80:])
    chk("4 error de red: el botón sigue utilizable", not btn.is_disabled())
    pg.unroute("**/api/admin/lote/*/vaciar")
    # 401 a mitad de operación
    pg.route("**/api/admin/lote/*/vaciar", lambda r: r.fulfill(status=401, content_type="application/json", body=json.dumps({"detail": "Token de administrador inválido."})))
    btn.click()
    pg.wait_for_timeout(800)
    chk("4 401 a mitad: vuelve al login, hoja cerrada, sin datos", pg.is_visible("#loginView") and pg.locator(".sheet").count() == 0 and "TQT-R" not in pg.inner_text("body") and "no es válida" in pg.inner_text("#loginErr"), pg.inner_text("#loginErr"))
    pg.screenshot(path=str(IMG / "24_401_login.png"))
    pg.unroute("**/api/admin/lote/*/vaciar")
    pg.fill("#pass", PW)
    pg.press("#pass", "Enter")
    pg.wait_for_selector("#adminView:not([hidden])")
    pg.wait_for_timeout(1200)
    # vaciar de verdad
    pg.click("[data-v=riesgo]")
    pg.select_option("#vLote", str(B))
    pg.click("#btnVaciar")
    pg.wait_for_selector(".sheet")
    pg.fill("#palabra", "VACIAR")
    pg.click(".sheet .btn-danger")
    pg.wait_for_timeout(1500)
    chk("4 vaciar lote B: 0 tarjetas, sus PCB DISPONIBLES", len(tar(B)) == 0 and pcb_by("TQT-R1-V30-0007")["estado_ciclo"] == "DISPONIBLE" and len(tar(A)) == 2)
    chk("4 vaciar: banner con respaldo", "Respaldo guardado" in pg.inner_text("#banner"))
    # borrar TODO + respaldo restaurable
    pre = {"tar": len(tar(A)) + len(tar(B)), "pcb": api("/api/pcb?limit=1")["total"]}
    pg.click("#btnReset")
    pg.wait_for_selector(".sheet")
    pg.screenshot(path=str(IMG / "25_borrar_todo.png"))
    btn = pg.locator(".sheet .btn-danger")
    for w in ("borrar todo", "BORRAR", "BORRAR  TODO"):
        pg.fill("#palabra", w)
        chk(f"4 reset: '{w}' deshabilitado", btn.is_disabled())
    pg.fill("#palabra", "BORRAR TODO")
    n0 = len(respaldos())
    btn.click()
    pg.wait_for_timeout(2000)
    chk("4 reset: BD vacía por API, lotes conservados", api("/api/pcb?limit=1")["total"] == 0 and len(tar(A)) == 0 and len(api("/api/lotes")) == 2)
    rn = respaldos()
    chk("4 reset: respaldo creado", len(rn) == n0 + 1, rn[-1])
    print("   banner:", pg.inner_text("#banner")[:160].replace("\n", " "))
    d = tempfile.mkdtemp()
    subprocess.run(["docker", "cp", f"{CT}:/backups/{rn[-1]}", d + "/r.db"], env=ENV, check=True)
    c = sqlite3.connect(d + "/r.db")
    ic = c.execute("pragma integrity_check").fetchone()[0]
    cnt = {"tar": c.execute("select count(*) from tarjetas_produccion").fetchone()[0], "pcb": c.execute("select count(*) from pcb_inventario").fetchone()[0]}
    c.close()
    chk("4 respaldo restaurable: integrity_check ok y mismos conteos", ic == "ok" and cnt == pre, f"{ic} {cnt} vs {pre}")
    pg.screenshot(path=str(IMG / "26_tras_reset.png"), full_page=True)
    print("consola:", [c for c in vg.consola if "Failed to load resource" not in c[1]], "http:", vg.http)
    br.close()
print(f"{sum(res)}/{len(res)} OK")
