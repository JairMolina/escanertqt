"""Concurrencia: varios celulares escaneando a la vez sobre SQLite WAL (sin 'database is locked', sin duplicados).

Criterio de aceptación 2: latencia P95 < 500 ms por escaneo (objetivo del servidor: < 30 ms).
"""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import concurrent.futures
import statistics
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import db, inventario as inv
from app.main import app

from _aislamiento import crear_par, mac_unica, nuevo_lote, num_unico, verificar_aislamiento


def p95(valores):
    return statistics.quantiles(valores, n=100)[94]


class TestConcurrencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "conc.db"
        db.init_db(cls.path)
        db.init_db()
        cls.client = TestClient(app)
        cls.lote_id = nuevo_lote()["id"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_01_diez_celulares_escanean_el_mismo_qr_gana_uno(self):
        """10 hilos escanean la MISMA PCB a la vez: 1 AGREGADA y 9 DUPLICADA (sin errores ni filas repetidas)."""
        codigo = f"TQT-R3-V30-{num_unico()}"
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            resultados = [f.result() for f in [ex.submit(lambda: self.client.post("/api/pcb/escanear", json={"codigo": codigo})) for _ in range(10)]]
        self.assertEqual([r.status_code for r in resultados], [200] * 10)
        veredictos = sorted(r.json()["resultado"] for r in resultados)
        self.assertEqual(veredictos, ["AGREGADA"] + ["DUPLICADA"] * 9)
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM pcb_inventario WHERE nombre = ?", (codigo,)).fetchone()[0], 1)

    def test_02_escaneos_distintos_en_paralelo_sin_database_is_locked(self):
        """8 celulares x 25 PCB distintas (200 escrituras): todas AGREGADA, sin bloqueos y con latencia baja."""
        celulares, por_celular = 8, 25

        def celular(c):
            lat, errores = [], []
            for i in range(por_celular):
                tipo = ("R1", "R2", "R3")[i % 3]
                codigo = f"TQT-{tipo}-V{40 + c}-{i + 1:04d}"  # versión distinta por celular: series propias
                t0 = time.perf_counter()
                r = self.client.post("/api/pcb/escanear", json={"codigo": codigo, "operador": f"cel{c}"})
                lat.append((time.perf_counter() - t0) * 1000)
                if r.status_code != 200 or r.json()["resultado"] != "AGREGADA":
                    errores.append(f"celular {c}: {r.status_code} {r.text[:120]}")
            return lat, errores

        with concurrent.futures.ThreadPoolExecutor(max_workers=celulares) as ex:
            resultados = [f.result() for f in [ex.submit(celular, c) for c in range(celulares)]]
        lat = [x for r in resultados for x in r[0]]
        errores = [x for r in resultados for x in r[1]]
        self.assertEqual(errores, [], errores[:3])
        self.assertEqual(len(lat), celulares * por_celular)
        self.assertLess(p95(lat), 500.0)
        print(f"\n  [métricas] escaneo HTTP P95 {p95(lat):.1f} ms · mediana {statistics.median(lat):.1f} ms ({len(lat)} escaneos, {celulares} celulares)")

    def test_03_rafaga_directa_10_hilos_100_altas_manuales(self):
        workers, por_worker = 10, 10

        def tarea(w):
            lat, errores = [], []
            for c in range(por_worker):
                t0 = time.perf_counter()
                try:
                    inv.registrar_manual("R1", f"{w + 1}", f"{c + 1:04d}", 1, db_path=self.path)
                    lat.append((time.perf_counter() - t0) * 1000)
                except Exception as ex:  # noqa: BLE001
                    errores.append(f"worker {w}: {ex}")
            return lat, errores

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            resultados = [f.result() for f in [ex.submit(tarea, w) for w in range(workers)]]
        lat = [x for r in resultados for x in r[0]]
        errores = [x for r in resultados for x in r[1]]
        self.assertEqual(errores, [], errores[:3])
        self.assertEqual(inv.listar_pcb(db_path=self.path, limit=1000)["total"], workers * por_worker)
        self.assertLess(p95(lat), 500.0)

    def test_04_series_automaticas_no_se_repiten_entre_celulares(self):
        """Alta manual sin serie desde 8 hilos: cada llamada toma la siguiente serie libre, sin choques ni repetidos."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda _: inv.registrar_manual("R2", "50", None, 1, db_path=self.path)["pcbs"][0]["serie"], range(24)))
        self.assertEqual(len(set(res)), 24)
        self.assertEqual(sorted(res), [f"{i:04d}" for i in range(1, 25)])

    def test_05_carrera_misma_mac_gana_solo_una(self):
        """10 celulares teclean la MISMA MAC en PCB distintas: 1 gana (200), 9 reciben 409. La BD queda con 1 sola."""
        pcbs = [crear_par(self.lote_id, macs=False)["pcb_r1_id"] for _ in range(10)]
        objetivo = mac_unica()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            codigos = [f.result().status_code for f in [ex.submit(lambda p=p: self.client.put(f"/api/pcb/{p}/mac", json={"mac": objetivo})) for p in pcbs]]
        self.assertEqual(sorted(codigos), [200] + [409] * 9)
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM pcb_inventario WHERE mac = ?", (objetivo,)).fetchone()[0], 1)

    def test_06_carrera_misma_pcb_en_dos_tarjetas_gana_solo_una(self):
        """10 celulares arman una tarjeta con la MISMA R1 disponible: 1 gana (201), 9 reciben 409."""
        pid = inv.registrar_manual("R1", None, None, 1)["pcbs"][0]["id"]
        inv.confirmar_recepcion([pid])

        def corredor(n):
            return self.client.post("/api/tarjetas", json={"lote_id": self.lote_id, "id_tarjeta_num": f"{8000 + n}", "r1_id": pid}).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            codigos = list(ex.map(corredor, range(10)))
        self.assertEqual(sorted(codigos), [201] + [409] * 9)

    def test_07_misma_tarjeta_gana_solo_una(self):
        """10 celulares arman el MISMO número de tarjeta con PCB distintas: 1 gana, 9 reciben 409."""
        r1s = []
        for _ in range(10):
            pid = inv.registrar_manual("R1", None, None, 1)["pcbs"][0]["id"]
            r1s.append(pid)
        inv.confirmar_recepcion(r1s)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            codigos = list(ex.map(lambda p: self.client.post("/api/tarjetas", json={"lote_id": self.lote_id, "id_tarjeta_num": "3333", "r1_id": p}).status_code, r1s))
        self.assertEqual(sorted(codigos), [201] + [409] * 9)

    def test_09_lecturas_no_bloquean_a_las_escrituras(self):
        """Monitor consultando tarjetas/stats mientras 4 celulares escanean: nadie se bloquea (WAL)."""
        def lector(_):
            errores = 0
            for _ in range(15):
                if self.client.get("/api/stats").status_code != 200 or self.client.get("/api/recepcion").status_code != 200:
                    errores += 1
            return errores

        def escritor(c):
            return sum(self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V6{c}-{i + 1:04d}"}).json()["resultado"] != "AGREGADA" for i in range(15))

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(lector, i) for i in range(4)] + [ex.submit(escritor, c) for c in range(4)]
            self.assertEqual(sum(f.result() for f in futs), 0)


if __name__ == "__main__":
    unittest.main()
