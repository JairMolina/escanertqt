"""QA Emparejar / Programar: sugerencias, auto, tarjetas impares, asignar, falla, disolver, MAC, concurrencia e invariantes."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import sqlite3
import threading
import unittest

from fastapi.testclient import TestClient

from app.database import db
from app.main import app

from _aislamiento import mac_unica, nuevo_lote, verificar_aislamiento
from _aislamiento import num_unico as _num_unico


def num_unico():
    """Serie libre en TODOS los tipos y versiones (otros módulos de test comparten la BD y dan altas automáticas)."""
    while True:
        s = _num_unico()
        with db.get_db() as c:
            if not c.execute("SELECT 1 FROM pcb_inventario WHERE serie=?", (s,)).fetchone() and                not c.execute("SELECT 1 FROM tarjetas_produccion WHERE id_tarjeta_num=?", (s,)).fetchone():
                return s


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.lote = nuevo_lote()["id"]

    # helpers
    def pcb(self, tipo, serie, version="30", confirmar=True):
        r = self.client.post("/api/pcb/manual", json={"tipo": tipo, "version": version, "serie": serie})
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()["pcbs"][0]
        if confirmar:
            self.assertEqual(self.client.post("/api/recepcion/confirmar", json={"ids": [p["id"]]}).status_code, 200)
            p = self.client.get(f"/api/pcb/{p['id']}").json()
        return p

    def get(self, pid):
        return self.client.get(f"/api/pcb/{pid}").json()

    def tarjeta(self, tid):
        r = self.client.get(f"/api/tarjetas/{tid}")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def invariantes(self):
        """Una PCB en a lo sumo una tarjeta; ASIGNADA <=> en una tarjeta."""
        with db.get_db() as c:
            filas = []
            for col in ("pcb_r1_id", "pcb_r2_id", "pcb_r3_id"):
                filas += [r[0] for r in c.execute(f"SELECT {col} FROM tarjetas_produccion WHERE {col} IS NOT NULL")]
            self.assertEqual(len(filas), len(set(filas)), "una PCB aparece en más de una ranura")
            for r in c.execute("SELECT id, nombre, estado_ciclo FROM pcb_inventario"):
                self.assertEqual(r["estado_ciclo"] == "ASIGNADA", r["id"] in filas, f"{r['nombre']} {r['estado_ciclo']}")


class TestEmparejarAuto(Base):
    def test_completas_y_parciales(self):
        s1, s2, s3, s4 = (num_unico() for _ in range(4))
        for t in ("R1", "R2", "R3"):
            self.pcb(t, s1)
        self.pcb("R1", s2), self.pcb("R2", s2)          # solo R1+R2
        self.pcb("R1", s3)                               # incompleta
        self.pcb("R2", s4, confirmar=True)               # sin R1
        sug = self.client.get(f"/api/emparejar/sugerencias?lote_id={self.lote}").json()
        self.assertIsNone({x["serie"]: x for x in sug["completas"]}[s1]["r3"])   # R3 manual por defecto
        sug = self.client.get(f"/api/emparejar/sugerencias?lote_id={self.lote}&r3=auto").json()
        comp = {x["serie"]: x for x in sug["completas"]}
        inc = {x["serie"]: x for x in sug["incompletas"]}
        self.assertIn(s1, comp)
        self.assertIsNotNone(comp[s1]["r3"])
        self.assertIsNone(comp[s2]["r3"])
        self.assertEqual(inc[s3]["faltan"], ["R2"])
        self.assertEqual(inc[s4]["faltan"], ["R1"])
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote, "series": [s1, s2, s3, s4, s1, "9999"]}).json()
        self.assertEqual([t["id_tarjeta_num"] for t in r["creadas"]], [s1, s2])
        self.assertEqual({o["serie"] for o in r["omitidas"]}, {s3, s4, "9999"})
        self.assertTrue(all(t["completa"] for t in r["creadas"]))
        self.assertEqual(r["creadas"][0]["sin_mac"], ["R1", "R2"])
        # segunda ejecución: nada nuevo de estas series
        r2 = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote, "series": [s1, s2]}).json()
        self.assertEqual(r2["creadas"], [])
        self.assertEqual(len(r2["omitidas"]), 2)
        self.invariantes()

    def test_borrador_no_se_empareja(self):
        s = num_unico()
        self.pcb("R1", s, confirmar=False)
        self.pcb("R2", s, confirmar=False)
        sug = self.client.get(f"/api/emparejar/sugerencias?lote_id={self.lote}").json()
        self.assertNotIn(s, [x["serie"] for x in sug["completas"] + sug["incompletas"]])
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote, "series": [s]}).json()
        self.assertEqual(r["creadas"], [])

    def test_versiones_distintas_mismo_numero_si_empareja(self):
        """DECISIÓN: el emparejado es por número de serie; la versión no impide emparejar (R1 V30 0005 + R2 V31 0005)."""
        s = num_unico()
        self.pcb("R1", s, "30")
        self.pcb("R2", s, "31")
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote, "series": [s]}).json()
        self.assertEqual(len(r["creadas"]), 1)
        t = r["creadas"][0]
        self.assertEqual((t["nombre_r1"], t["nombre_r2"]), (f"TQT-R1-V30-{s}", f"TQT-R2-V31-{s}"))

    def test_series_repetidas_misma_serie_dos_versiones(self):
        s = num_unico()
        self.pcb("R1", s, "30"), self.pcb("R1", s, "31"), self.pcb("R2", s, "30")
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote, "series": [s]}).json()
        self.assertEqual(len(r["creadas"]), 1)
        self.invariantes()
        sug = self.client.get(f"/api/emparejar/sugerencias?lote_id={self.lote}").json()
        self.assertEqual(len(sug["sueltas"]["R1"]) >= 1, True)  # la R1 V31 sobrante sigue suelta

    def test_serie_invalida_en_auto(self):
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote, "series": ["abc"]})
        self.assertEqual(r.status_code, 400, r.text)


class TestTarjetasImpares(Base):
    def armar(self):
        a, b = num_unico(), num_unico()
        r1, r2 = self.pcb("R1", a), self.pcb("R2", b)
        r = self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r1_id": r1["id"], "r2_id": r2["id"]})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json(), r1, r2

    def test_impar_y_defecto(self):
        t, r1, r2 = self.armar()
        self.assertEqual(t["id_tarjeta_num"], r1["serie"])
        self.assertNotEqual(r1["serie"], r2["serie"])
        self.assertTrue(t["completa"])
        self.assertEqual(self.get(r1["id"])["estado_ciclo"], "ASIGNADA")
        self.invariantes()

    def test_asignar_errores(self):
        t, r1, r2 = self.armar()
        otra_r1 = self.pcb("R1", num_unico())
        r3 = self.pcb("R3", num_unico())
        borrador = self.pcb("R1", num_unico(), confirmar=False)
        url = f"/api/tarjetas/{t['id']}/asignar"
        # PCB de otro tipo en la ranura
        self.assertEqual(self.client.put(url, json={"ranura": "R1", "pcb_id": r3["id"]}).status_code, 400)
        # ranura inválida
        self.assertEqual(self.client.put(url, json={"ranura": "R9", "pcb_id": r3["id"]}).status_code, 400)
        # ya asignada a otra tarjeta
        t2 = self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r1_id": otra_r1["id"]}).json()
        self.assertEqual(self.client.put(url, json={"ranura": "R1", "pcb_id": otra_r1["id"]}).status_code, 409)
        # borrador
        self.assertEqual(self.client.put(url, json={"ranura": "R1", "pcb_id": borrador["id"]}).status_code, 409)
        # inexistente / tarjeta inexistente
        self.assertEqual(self.client.put(url, json={"ranura": "R1", "pcb_id": 99999999}).status_code, 404)
        self.assertEqual(self.client.put("/api/tarjetas/99999999/asignar", json={"ranura": "R1", "pcb_id": None}).status_code, 404)
        # FALLA no asignable
        f = self.pcb("R1", num_unico())
        self.client.post(f"/api/pcb/{f['id']}/falla", json={})
        self.assertEqual(self.get(f["id"])["estado_ciclo"], "FALLA")
        self.assertEqual(self.client.put(url, json={"ranura": "R1", "pcb_id": f["id"]}).status_code, 409)
        # nada cambió
        self.assertEqual(self.tarjeta(t["id"])["pcb_r1_id"], r1["id"])
        self.assertEqual(self.tarjeta(t2["id"])["pcb_r1_id"], otra_r1["id"])
        self.invariantes()

    def test_reemplazo_libera_reinicia_y_libera_ranura(self):
        t, r1, r2 = self.armar()
        db.set_prueba(t["id"], "soldadura", "OK")      # dato interno (hoja Pruebas del Excel): ya no hay pantalla ni API
        self.assertEqual(self.tarjeta(t["id"])["soldadura"], "OK")
        nueva = self.pcb("R1", num_unico())
        url = f"/api/tarjetas/{t['id']}/asignar"
        a = self.client.put(url, json={"ranura": "R1", "pcb_id": nueva["id"]})
        self.assertEqual(a.status_code, 200, a.text)
        self.assertEqual(a.json()["soldadura"], "PENDIENTE", "pruebas no reiniciadas")
        self.assertEqual(self.get(r1["id"])["estado_ciclo"], "DISPONIBLE")
        self.assertEqual(self.get(nueva["id"])["estado_ciclo"], "ASIGNADA")
        # misma PCB otra vez: idempotente
        self.assertEqual(self.client.put(url, json={"ranura": "R1", "pcb_id": nueva["id"]}).status_code, 200)
        # liberar R2 -> incompleta, no LIBERADA
        b = self.client.put(url, json={"ranura": "R2", "pcb_id": None})
        self.assertEqual(b.status_code, 200)
        self.assertFalse(b.json()["completa"])
        self.assertIsNone(b.json()["nombre_r2"])
        self.assertNotEqual(b.json()["estado_general"], "LIBERADO")
        self.assertEqual(self.get(r2["id"])["estado_ciclo"], "DISPONIBLE")
        # liberar ranura ya vacía: sin error
        self.assertEqual(self.client.put(url, json={"ranura": "R2", "pcb_id": None}).status_code, 200)
        self.invariantes()

    def test_falla_con_y_sin_reemplazo(self):
        t, r1, r2 = self.armar()
        rep = self.pcb("R2", num_unico())
        r = self.client.post(f"/api/pcb/{r2['id']}/falla", json={"motivo": "corto", "reemplazo_id": rep["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["pcb"]["estado_ciclo"], "FALLA")
        self.assertEqual(d["tarjeta"]["pcb_r2_id"], rep["id"])
        self.assertEqual(d["reemplazo"]["estado_ciclo"], "ASIGNADA")
        # sin reemplazo: R1 sale, tarjeta incompleta
        r = self.client.post(f"/api/pcb/{r1['id']}/falla", json={})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["tarjeta"]["pcb_r1_id"])
        self.assertFalse(r.json()["tarjeta"]["completa"])
        # reemplazo de tipo equivocado y reemplazo sin tarjeta
        r3 = self.pcb("R3", num_unico())
        self.assertEqual(self.client.post(f"/api/pcb/{rep['id']}/falla", json={"reemplazo_id": r3["id"]}).status_code, 400)
        suelta = self.pcb("R1", num_unico())
        self.assertEqual(self.client.post(f"/api/pcb/{suelta['id']}/falla", json={"reemplazo_id": r3["id"]}).status_code, 400)
        self.assertEqual(self.client.post("/api/pcb/99999999/falla", json={}).status_code, 404)
        self.assertEqual(self.get(rep["id"])["estado_ciclo"], "ASIGNADA")
        self.invariantes()

    def test_falla_reemplazo_es_ella_misma(self):
        t, r1, r2 = self.armar()
        r = self.client.post(f"/api/pcb/{r1['id']}/falla", json={"reemplazo_id": r1["id"]})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(self.get(r1["id"])["estado_ciclo"], "ASIGNADA")

    def test_disolver(self):
        t, r1, r2 = self.armar()
        db.set_prueba(t["id"], "soldadura", "OK")
        self.assertEqual(self.client.delete(f"/api/tarjetas/{t['id']}").status_code, 409)
        r = self.client.delete(f"/api/tarjetas/{t['id']}?forzar=1")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["liberadas"]), 2)
        self.assertEqual(self.get(r1["id"])["estado_ciclo"], "DISPONIBLE")
        self.assertEqual(self.client.delete(f"/api/tarjetas/{t['id']}").status_code, 404)
        self.invariantes()

    def test_disolver_sin_pruebas(self):
        t, r1, r2 = self.armar()
        self.assertEqual(self.client.delete(f"/api/tarjetas/{t['id']}").status_code, 200)
        self.assertIsNone(self.get(r2["id"])["tarjeta_id"])

    def test_patch_tarjeta(self):
        t, _, _ = self.armar()
        u = f"/api/tarjetas/{t['id']}"
        r = self.client.patch(u, json={"firmware_r1": "1.2", "semana_produccion": 38, "fecha_real": "2026-09-23"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["firmware_r1"], r.json()["semana_produccion"], r.json()["fecha_real"]), ("1.2", 38, "2026-09-23"))
        self.assertEqual(self.client.patch(u, json={"semana_produccion": 54}).status_code, 422)
        self.assertEqual(self.client.patch(u, json={"semana_produccion": 0}).status_code, 422)
        self.assertEqual(self.client.patch(u, json={"fecha_real": "23/09/2026"}).status_code, 400)
        self.assertEqual(self.client.patch(u, json={"fecha_real": "2026-02-30"}).status_code, 400)
        r = self.client.patch(u, json={"fecha_real": ""})
        self.assertIsNone(r.json()["fecha_real"])
        self.assertEqual(r.json()["firmware_r1"], "1.2")
        self.assertEqual(self.client.patch("/api/tarjetas/99999999", json={"firmware_r1": "x"}).status_code, 404)

    def test_crear_tarjeta_errores(self):
        self.assertEqual(self.client.post("/api/tarjetas", json={"lote_id": self.lote}).status_code, 400)
        r2 = self.pcb("R2", num_unico())
        self.assertEqual(self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r2_id": r2["id"]}).status_code, 400)
        self.assertEqual(self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r2_id": r2["id"], "id_tarjeta_num": "77"}).status_code, 201)
        r2b = self.pcb("R2", num_unico())
        self.assertEqual(self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r2_id": r2b["id"], "id_tarjeta_num": "0077"}).status_code, 409)
        self.assertEqual(self.get(r2b["id"])["estado_ciclo"], "DISPONIBLE")  # el fallo no dejó la PCB a medias
        self.assertEqual(self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r2_id": r2b["id"], "id_tarjeta_num": "12345"}).status_code, 400)
        self.invariantes()

    def test_concurrencia_misma_pcb(self):
        t1, _, _ = self.armar()
        t2, _, _ = self.armar()
        libre = self.pcb("R1", num_unico())
        res = []

        def asignar(tid):
            with TestClient(app) as c:
                res.append(c.put(f"/api/tarjetas/{tid}/asignar", json={"ranura": "R1", "pcb_id": libre["id"]}).status_code)
        hs = [threading.Thread(target=asignar, args=(t["id"],)) for t in (t1, t2)]
        [h.start() for h in hs]
        [h.join() for h in hs]
        self.assertEqual(sorted(res), [200, 409])
        self.invariantes()


class TestMAC(Base):
    def setUp(self):
        super().setUp()
        self.p = self.pcb("R1", num_unico())

    def put(self, pid, mac):
        return self.client.put(f"/api/pcb/{pid}/mac", json={"mac": mac})

    def test_formatos(self):
        for txt in ("70:4b:ca:5b:9f:6e", "70-4B-CA-5B-9F-6E", "704bca5b9f6e", "704b.ca5b.9f6e", "  70 4b ca 5b 9f 6e ",
                    "MAC: 70:4b:ca:5b:9f:6e", "mac 704BCA5B9F6E", "R1 => 70:4B:CA:5B:9F:6E ok"):
            p = self.pcb("R1", num_unico())
            r = self.put(p["id"], txt)
            if r.status_code == 409:  # ya la tiene la PCB de la vuelta anterior: borrar y reintentar
                self.client.put(f"/api/pcb/{self.dueno}/mac", json={"mac": None})
                r = self.put(p["id"], txt)
            self.assertEqual(r.status_code, 200, f"{txt!r}: {r.text}")
            self.assertEqual(r.json()["mac"], "70:4B:CA:5B:9F:6E", txt)
            self.dueno = p["id"]
        self.client.put(f"/api/pcb/{self.dueno}/mac", json={"mac": None})

    def test_invalidos(self):
        for txt in ("70:4b:ca:5b:9f", "70:4b:ca:5b:9f:6e:11", "70:4b:ca:5b:9f:zz", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff",
                    "01:00:5e:00:00:01", "hola", "7", "704bca5b9f6e11", "70:4b:ca:5b:9f:6e:11:22"):
            r = self.put(self.p["id"], txt)
            self.assertEqual(r.status_code, 400, f"{txt!r}: {r.status_code} {r.text}")
        self.assertIsNone(self.get(self.p["id"])["mac"])

    def test_duplicado_propia_borrar_r3_inexistente(self):
        m = mac_unica()
        self.assertEqual(self.put(self.p["id"], m).status_code, 200)
        self.assertEqual(self.put(self.p["id"], m.lower()).status_code, 200)  # reescribir la propia
        otra = self.pcb("R2", num_unico())
        r = self.put(otra["id"], m)
        self.assertEqual(r.status_code, 409)
        self.assertIn(self.p["nombre"], r.json()["detail"])
        self.assertIsNone(self.get(otra["id"])["mac"])
        r3 = self.pcb("R3", num_unico())
        self.assertEqual(self.put(r3["id"], mac_unica()).status_code, 400)
        self.assertEqual(self.put(r3["id"], None).status_code, 200)
        self.assertEqual(self.put(99999999, mac_unica()).status_code, 404)
        r = self.put(self.p["id"], None)
        self.assertEqual((r.status_code, r.json()["mac"]), (200, None))
        self.assertEqual(self.put(self.p["id"], "   ").json()["mac"], None)
        self.assertEqual(self.put(otra["id"], m).status_code, 200)  # ya liberada

    def test_bitacora_y_tarjeta(self):
        r2 = self.pcb("R2", num_unico())
        t = self.client.post("/api/tarjetas", json={"lote_id": self.lote, "r1_id": self.p["id"], "r2_id": r2["id"]}).json()
        self.assertEqual(t["sin_mac"], ["R1", "R2"])
        m1, m2 = mac_unica(), mac_unica()
        self.put(self.p["id"], m1)
        self.assertEqual(self.tarjeta(t["id"])["sin_mac"], ["R2"])
        self.put(r2["id"], m2)
        d = self.tarjeta(t["id"])
        self.assertEqual((d["sin_mac"], d["mac_r1"], d["mac_r2"]), ([], m1, m2))
        with db.get_db() as c:
            n = c.execute("SELECT COUNT(*) FROM bitacora_eventos WHERE tipo_evento='MAC_GUARDADA' AND detalle IN (?,?)", (m1, m2)).fetchone()[0] \
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='bitacora_eventos'").fetchone() else None
        if n is not None:
            self.assertEqual(n, 2)

    def test_concurrencia_misma_mac(self):
        otras = [self.pcb("R1", num_unico()) for _ in range(4)]
        m = mac_unica()
        res = []

        def poner(pid):
            with TestClient(app) as c:
                res.append(c.put(f"/api/pcb/{pid}/mac", json={"mac": m}).status_code)
        hs = [threading.Thread(target=poner, args=(p["id"],)) for p in otras]
        [h.start() for h in hs]
        [h.join() for h in hs]
        self.assertEqual(sorted(res), [200, 409, 409, 409])
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM pcb_inventario WHERE mac=?", (m,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
