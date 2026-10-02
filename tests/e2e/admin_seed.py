"""Siembra datos reales por API en un servidor de prueba: 30 PCB R1/R2/R3 confirmadas, 8 tarjetas (2 lotes) con MAC y pruebas.
Uso: python admin_seed.py [base_url]   (idempotente en lo que ya exista)"""
import sys
import requests
import urllib3

urllib3.disable_warnings()
B = sys.argv[1] if len(sys.argv) > 1 else "https://localhost:8460"
S = requests.Session()
S.verify = False


def api(m, p, **kw):
    r = S.request(m, B + p, **kw)
    assert r.status_code < 400, (m, p, r.status_code, r.text[:200])
    return r.json() if r.content else None


import os
r = S.post(B + "/api/admin/login", json={"password": os.environ.get("TQT_ADMIN_PASSWORD", "ClaveDePrueba-123")})
if r.status_code == 200:
    S.headers["X-Admin-Token"] = r.json()["token"]
lotes = api("GET", "/api/lotes")
A = next(l for l in lotes if l["activo"])
Bl = next((l for l in lotes if l["codigo_lote"] == "LOTE-QA-B"), None) or api(
    "POST", "/api/lotes", json={"codigo_lote": "LOTE-QA-B", "mes": 10, "anio": 2026, "crear_excel": False, "activo": False})


def tarjetas():
    return api("GET", f"/api/tarjetas?limit=500&lote_id={A['id']}")["items"] + api("GET", f"/api/tarjetas?limit=500&lote_id={Bl['id']}")["items"]


if api("GET", "/api/pcb?limit=1")["total"] == 0:
    for t in ("R1", "R2", "R3"):
        api("POST", "/api/pcb/manual", json={"tipo": t, "version": "30", "serie": "0001", "cantidad": 30})
    api("POST", "/api/recepcion/confirmar", json={})
if not tarjetas():
    api("POST", "/api/emparejar/auto", json={"lote_id": A["id"], "series": [f"{i:04d}" for i in range(1, 7)]})
    api("POST", "/api/emparejar/auto", json={"lote_id": Bl["id"], "series": ["0007", "0008"]})
tar = tarjetas()
for t in tar:
    n = int(t["id_tarjeta_num"])
    for pid, sfx in ((t.get("pcb_r1_id"), "01"), (t.get("pcb_r2_id"), "02")):
        if pid:
            api("PUT", f"/api/pcb/{pid}/mac", json={"mac": f"70:4B:CA:5B:{n:02X}:{sfx}"})
etapas = ["Soldadura", "Programación", "Prueba PCB", "Integración", "Prueba Final"]
for i, t in enumerate(tar):
    if i % 3 == 0:
        for e in etapas:
            api("PUT", f"/api/tarjetas/{t['id']}/pruebas", json={"etapa": e, "estado": "OK"})
    elif i % 3 == 1:
        api("PUT", f"/api/tarjetas/{t['id']}/pruebas", json={"etapa": "Prueba PCB", "estado": "FALLA"})
    else:
        api("PUT", f"/api/tarjetas/{t['id']}/pruebas", json={"etapa": "Soldadura", "estado": "OK"})
print("tarjetas", len(tar), "pcb", api("GET", "/api/pcb?limit=5000")["total"], "lotes", [(l["id"], l["codigo_lote"]) for l in api("GET", "/api/lotes")])
