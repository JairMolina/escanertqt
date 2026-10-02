"""Siembra movimientos REALES por API en un servidor de prueba (altas, MAC, firmware, versión, falla+reemplazo, borrados de
placa/tarjeta, borrado admin, login fallido, exportación Excel) y >120 movimientos para paginar.
Uso: python admin_mov_seed.py [base_url]   (TQT_ADMIN_PASSWORD=ClaveQA-12345)"""
import os, sys
import requests
import urllib3

urllib3.disable_warnings()
PW = os.environ.get("TQT_ADMIN_PASSWORD", "ClaveQA-12345")


def sembrar(base):
    S = requests.Session(); S.verify = False

    def api(m, p, ok=(200, 201, 204), **kw):
        r = S.request(m, base + p, **kw)
        assert r.status_code in ok, (m, p, r.status_code, r.text[:200])
        return r.json() if r.content else None

    assert S.post(base + "/api/admin/login", json={"password": "mala-clave-1"}).status_code == 401   # ADMIN_LOGIN_FALLIDO
    r = S.post(base + "/api/admin/login", json={"password": PW}); assert r.status_code == 200, r.text   # ADMIN_LOGIN
    S.headers["X-Admin-Token"] = r.json()["token"]
    lote = next(l for l in api("GET", "/api/lotes") if l["activo"])
    for t in ("R1", "R2", "R3"):
        api("POST", "/api/pcb/manual", json={"tipo": t, "version": "30", "serie": "0001", "cantidad": 8, "operador": "Ana"})
    api("POST", "/api/recepcion/confirmar", json={"operador": "Ana"})
    pcbs = api("GET", "/api/pcb?limit=100")["items"]
    por = lambda tipo, serie: next(p for p in pcbs if p["tipo"] == tipo and p["serie"] == serie)
    api("POST", "/api/emparejar/auto", json={"lote_id": lote["id"], "series": ["0001", "0002", "0003", "0004"], "operador": "Ana"})
    tars = api("GET", f"/api/tarjetas?limit=50&lote_id={lote['id']}")["items"]
    for i, t in enumerate(tars):
        api("PUT", f"/api/pcb/{t['pcb_r1_id']}/mac", json={"mac": f"70:4B:CA:5B:{i + 1:02X}:01", "operador": "Beto"})
        api("PUT", f"/api/pcb/{t['pcb_r2_id']}/programacion", json={"mac": f"70:4B:CA:5B:{i + 1:02X}:02", "firmware": "4.1", "operador": "Beto"})
    api("PUT", f"/api/pcb/{tars[0]['pcb_r1_id']}/firmware", json={"firmware": "4.2", "operador": "Beto"})
    api("POST", "/api/pcb/version", json={"ids": [por("R3", "0007")["id"], por("R3", "0008")["id"]], "version": "31", "operador": "Ana"})
    api("POST", f"/api/pcb/{tars[1]['pcb_r1_id']}/falla", json={"motivo": "no enciende", "reemplazo_id": por("R1", "0005")["id"], "operador": "Beto"})
    api("DELETE", f"/api/pcb/{por('R2', '0008')['id']}")                              # PCB_ELIMINADA
    api("DELETE", f"/api/tarjetas/{tars[3]['id']}")                                   # TARJETA_DISUELTA
    api("DELETE", "/api/admin/pcb", json={"ids": [por("R1", "0008")["id"]]})          # ADMIN_PCB_BORRADAS
    api("DELETE", "/api/admin/tarjetas", json={"ids": [tars[2]["id"]], "liberar_pcb": True})   # ADMIN_TARJETAS_BORRADAS
    r = S.get(base + f"/api/admin/export/excel?lote_id={lote['id']}"); assert r.status_code == 200, r.status_code   # EXCEL_EXPORTADO
    S.post(base + "/api/admin/logout")                                                # ADMIN_LOGOUT
    r = S.post(base + "/api/admin/login", json={"password": PW}); S.headers["X-Admin-Token"] = r.json()["token"]
    # volumen: 130 cambios de MAC para paginar (>120)
    vivo = api("GET", f"/api/tarjetas?limit=50&lote_id={lote['id']}")["items"][0]
    for n in range(130):
        api("PUT", f"/api/pcb/{vivo['pcb_r1_id']}/mac", json={"mac": f"70:4B:CA:AA:{n // 256:02X}:{n % 256:02X}", "operador": "Carla"})
    tot = api("GET", "/api/admin/movimientos?limite=1")
    return {"total": tot["total"], "conteo": tot["conteo"], "lote": lote, "token": S.headers["X-Admin-Token"]}


if __name__ == "__main__":
    print(sembrar(sys.argv[1] if len(sys.argv) > 1 else "https://127.0.0.1:8463"))
