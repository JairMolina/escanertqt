"""Carga concurrente REAL (HTTP a un servidor aislado en 8468): 16 "celulares" escaneando/programando a la vez + 5 sesiones de
administración simultáneas. Comprueba: sin errores 5xx ni 'database is locked', sin duplicados, sesiones de admin independientes.
Uso: python tests/e2e/multisesion.py"""
import json
import os
import ssl
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PUERTO = "8468"
BASE = f"https://127.0.0.1:{PUERTO}"
CLAVE = "ClaveDePrueba-123"
tmp = Path(tempfile.mkdtemp(prefix="tqt_multi_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"),
           TQT_BACKUP_DIR=str(tmp / "bk"), TQT_ADMIN_PASSWORD=CLAVE, HTTPS_PORT=PUERTO, TQT_HOST_IP="127.0.0.1")
srv = subprocess.Popen([sys.executable, "run_server.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CTX = ssl._create_unverified_context()
fallos, lat, errores = [], [], []
lock = threading.Lock()


def check(n, c, d=""):
    print(("OK   " if c else "FALLA"), n, "" if c else d)
    if not c:
        fallos.append(n)


def http(metodo, ruta, cuerpo=None, token=None, timeout=30):
    t0 = time.time()
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"content-type": "application/json", **({"X-Admin-Token": token} if token else {})})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
            b = r.read()
            st, data = r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        st, data = e.code, None
    except Exception as e:  # noqa: BLE001
        st, data = 0, str(e)
    with lock:
        lat.append(time.time() - t0)
        if st == 0 or st >= 500:
            errores.append((metodo, ruta, st, str(data)[:80]))
    return st, data


try:
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/config", context=CTX, timeout=2)
            break
        except Exception:
            time.sleep(0.5)

    # --- 1) 16 celulares escanean a la vez: 20 placas propias cada uno + 10 placas COMPARTIDAS que todos intentan registrar
    N, PROPIAS, COMPARTIDAS = 16, 20, 10
    resultados = {"AGREGADA": 0, "DUPLICADA": 0, "otro": 0}

    def celular(i):
        for k in range(PROPIAS):
            serie = f"{(i * 100 + k + 1) % 9999 + 1:04d}"
            tipo = ("R1", "R2", "R3")[k % 3]
            st, d = http("POST", "/api/pcb/escanear", {"codigo": f"TQT-{tipo}-V30-{serie}", "operador": f"celular-{i}"})
            with lock:
                resultados[d["resultado"] if st == 200 and d and d["resultado"] in resultados else "otro"] += 1
        for k in range(COMPARTIDAS):
            st, d = http("POST", "/api/pcb/escanear", {"codigo": f"TQT-R1-V30-{9000 + k}", "operador": f"celular-{i}"})
            with lock:
                resultados[d["resultado"] if st == 200 and d and d["resultado"] in resultados else "otro"] += 1
    t0 = time.time()
    with ThreadPoolExecutor(N) as ex:
        list(ex.map(celular, range(N)))
    dur = time.time() - t0
    total = N * (PROPIAS + COMPARTIDAS)
    check(f"{total} escaneos de {N} celulares simultáneos en {dur:.1f}s sin errores del servidor", not errores, str(errores[:3]))
    check("cada placa compartida se registró UNA sola vez (el resto DUPLICADA)", resultados["AGREGADA"] == N * PROPIAS + COMPARTIDAS and resultados["otro"] == 0, str(resultados))

    # --- 2) confirmar, emparejar y programar MAC desde varios equipos a la vez (misma MAC pedida por dos: gana una)
    http("POST", "/api/recepcion/confirmar", {})
    items = http("GET", "/api/pcb?tipo=R1&limit=500")[1]["items"]
    macs = [f"02:AA:00:00:{(n >> 8) & 255:02X}:{n & 255:02X}" for n in range(len(items) + 5)]
    conflicto = macs[0]

    def programar(par):
        p, mac = par
        return http("PUT", f"/api/pcb/{p['id']}/programacion", {"mac": mac, "firmware": "4.1", "operador": "equipo"})[0]
    with ThreadPoolExecutor(16) as ex:
        estados = list(ex.map(programar, [(items[0], conflicto), (items[1], conflicto)] + [(p, macs[i + 2]) for i, p in enumerate(items[2:60])]))
    check("MAC pedida a la vez por dos equipos: una se guarda y la otra recibe 409", sorted(estados[:2]) == [200, 409], str(estados[:2]))
    check("programar 58 placas en paralelo sin errores", all(s == 200 for s in estados[2:]), str(sorted(set(estados[2:]))))
    check("contador global 'guardadas hoy' = MAC realmente guardadas", http("GET", "/api/programacion/hoy")[1]["guardadas"] == 59, str(http("GET", "/api/programacion/hoy")[1]))

    # --- 3) 5 sesiones de administración simultáneas e independientes
    tokens = []
    with ThreadPoolExecutor(5) as ex:
        logins = list(ex.map(lambda _: http("POST", "/api/admin/login", {"password": CLAVE}), range(5)))
    tokens = [d["token"] for st, d in logins if st == 200]
    check("5 sesiones de administración a la vez (5 tokens distintos)", len(tokens) == 5 and len(set(tokens)) == 5, str([st for st, _ in logins]))
    with ThreadPoolExecutor(10) as ex:
        lecturas = list(ex.map(lambda t: http("GET", "/api/admin/resumen", token=t)[0], tokens * 2))
    check("las 5 sesiones consultan a la vez sin interferirse", all(s == 200 for s in lecturas), str(lecturas))
    http("POST", "/api/admin/logout", token=tokens[0])
    check("cerrar la sesión de una NO afecta a las demás", all(http("GET", "/api/admin/resumen", token=t)[0] == 200 for t in tokens[1:]))
    # dos administradores borran la MISMA tarjeta a la vez: uno la borra, el otro recibe 404 (sin 500)
    t1 = http("POST", "/api/tarjetas", {"r1_id": items[70]["id"]})[1]
    with ThreadPoolExecutor(2) as ex:
        borrados = list(ex.map(lambda t: http("DELETE", "/api/admin/tarjetas", {"ids": [t1["id"]], "liberar_pcb": True}, token=t)[0], tokens[1:3]))
    check("dos administradores borrando lo mismo a la vez: sin errores 500", not any(s >= 500 for s in borrados), str(borrados))
    # las lecturas de administración siguen respondiendo MIENTRAS otros escanean
    def mixto(i):
        return http("GET", "/api/admin/movimientos?limite=20", token=tokens[1 + i % 4])[0] if i % 2 else \
            http("POST", "/api/pcb/escanear", {"codigo": f"TQT-R2-V30-{7000 + i}"})[0]
    with ThreadPoolExecutor(20) as ex:
        mix = list(ex.map(mixto, range(60)))
    check("administración y escaneo simultáneos: todo 200", all(s == 200 for s in mix), str(sorted(set(mix))))
    movs = http("GET", "/api/admin/movimientos?limite=1&q=celular-3", token=tokens[1])[1]
    check("los movimientos registran QUÉ operador/celular hizo cada alta", movs and movs["total"] > 0, str(movs and movs["total"]))

    # --- 4) rendimiento
    p95 = statistics.quantiles(lat, n=20)[18]
    print(f"     {len(lat)} peticiones · mediana {statistics.median(lat)*1000:.0f} ms · p95 {p95*1000:.0f} ms · máx {max(lat)*1000:.0f} ms")
    check("sin errores 5xx ni 'database is locked' en toda la carga", not errores, str(errores[:3]))
finally:
    srv.terminate()
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
