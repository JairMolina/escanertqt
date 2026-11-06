"""v1.4.94: R3 «Aprobada» (aprobar/desaprobar, anulación automática) y estado de tarjeta `finalizada`."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import itertools
import unittest

from app.database import db, inventario as inv
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

_serie = itertools.count(8000)


class TestR3AprobadaFinalizada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        from app.services import test_station
        test_station.init()
        with db.get_db() as c:
            c.execute("INSERT OR IGNORE INTO stm32_stations (id, name, token_hash, owner) VALUES ('st','st','x','test')")

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))

    # ---- utilidades
    def _tarjeta(self, mac_ok=True, fw_r3="1.0"):
        n = next(_serie)
        serie = f"{n:04d}"
        with db.get_db() as c:
            r1 = inv.asegurar_pcb(c, "R1", "30", serie, mac=f"70:4B:CA:{n % 256:02X}:00:01" if mac_ok else None)
            r2 = inv.asegurar_pcb(c, "R2", "30", serie, mac=f"70:4B:CA:{n % 256:02X}:00:02" if mac_ok else None)
            r3 = inv.asegurar_pcb(c, "R3", "30", serie)
            for pid in (r1, r2):
                inv.set_firmware(pid, "4.1", conn=c)
            if fw_r3:
                inv.set_firmware(r3, fw_r3, conn=c)
            t = inv.crear_tarjeta(id_tarjeta_num=serie, r1_id=r1, r2_id=r2, r3_id=r3, conn=c)
        return t["id"], r1, r2, r3

    def _skytec(self, tid):
        with db.get_db() as c:
            for slot in ("R1", "R2"):
                mac = c.execute(f"SELECT p.mac FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id=t.pcb_{slot.lower()}_id WHERE t.id=?", (tid,)).fetchone()[0]
                c.execute("INSERT OR REPLACE INTO skytec_candados (tarjeta_id, slot, nombre, mac, estado) VALUES (?,?,?,?,'creado')",
                          (tid, slot, f"X-{slot}", mac.upper()))

    def _prueba_tqt(self, tid, result="aprobado", created=None):
        import time
        with db.get_db() as c:
            c.execute("INSERT INTO tqt_test_runs(id,station,requested_card,tarjeta_id,operator,state,created,updated,inventory,result) "
                      "VALUES (?,?,?,?,?,'done',?,?,'{}',?)",
                      (f"run-{tid}-{time.time_ns()}", "st", tid, tid, "op", created or time.time(), created or time.time(), result))

    def _tarjeta_api(self, tid):
        return db.get_tarjeta_by_id(tid)

    # ---- R3 aprobada
    def test_aprobar_r3_programada_ok_e_idempotente(self):
        _, _, _, r3 = self._tarjeta()
        r = self.c.post(f"/api/pcb/{r3}/aprobar", json={"operador": "ana"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["aprobada"])
        self.assertEqual(r.json()["aprobada_por"], "ana")
        self.assertTrue(r.json()["aprobada_en"])
        again = self.c.post(f"/api/pcb/{r3}/aprobar", json={"operador": "otro"})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["aprobada_en"], r.json()["aprobada_en"])   # idempotente: no se re-escribe
        self.assertTrue(self.c.get(f"/api/pcb/{r3}").json()["aprobada"])
        with db.get_db() as c:
            n = c.execute("SELECT COUNT(*) FROM escaneos WHERE evento='PCB_APROBADA'").fetchone()[0]
        self.assertGreaterEqual(n, 1)
        d = self.c.post(f"/api/pcb/{r3}/desaprobar", json={})
        self.assertEqual(d.status_code, 200)
        self.assertFalse(d.json()["aprobada"])

    def test_aprobar_r3_sin_programar_da_409(self):
        _, _, _, r3 = self._tarjeta(fw_r3=None)
        r = self.c.post(f"/api/pcb/{r3}/aprobar", json={})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("no está programada", r.text)
        self.assertFalse(self.c.get(f"/api/pcb/{r3}").json()["aprobada"])

    def test_solo_r3_se_aprueba(self):
        _, r1, _, _ = self._tarjeta()
        self.assertEqual(self.c.post(f"/api/pcb/{r1}/aprobar", json={}).status_code, 400)

    def test_cambio_de_firmware_anula_la_aprobacion(self):
        _, _, _, r3 = self._tarjeta()
        self.assertEqual(self.c.post(f"/api/pcb/{r3}/aprobar", json={}).status_code, 200)
        r = self.c.put(f"/api/pcb/{r3}/firmware", json={"firmware": "2.0"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["aprobada"])
        self.assertIsNone(r.json()["aprobada_en"])

    def test_falla_anula_la_aprobacion(self):
        _, _, _, r3 = self._tarjeta()
        self.c.post(f"/api/pcb/{r3}/aprobar", json={})
        self.assertEqual(self.c.post(f"/api/pcb/{r3}/falla", json={"motivo": "prueba"}).status_code, 200)
        self.assertFalse(self.c.get(f"/api/pcb/{r3}").json()["aprobada"])

    def test_listado_incluye_aprobada(self):
        tid, _, _, r3 = self._tarjeta()
        self.c.post(f"/api/pcb/{r3}/aprobar", json={})
        items = self.c.get("/api/pcb?tipo=R3&limit=500").json()["items"]
        self.assertTrue(next(i for i in items if i["id"] == r3)["aprobada"])
        t = self._tarjeta_api(tid)
        self.assertTrue(t["r3"]["aprobada"])
        self.assertTrue(t["r3"]["aprobada_en"])
        self.assertFalse(t["r1"]["aprobada"])

    # ---- tarjeta finalizada
    def test_finalizada_solo_con_todas_las_condiciones(self):
        tid, _, _, r3 = self._tarjeta()
        t = self._tarjeta_api(tid)
        self.assertFalse(t["finalizada"]); self.assertFalse(t["aprobada"]); self.assertFalse(t["skytec"])
        self._skytec(tid)
        self.assertFalse(self._tarjeta_api(tid)["finalizada"])          # falta TQT aprobada y R3 aprobada
        self._prueba_tqt(tid)
        t = self._tarjeta_api(tid)
        self.assertTrue(t["aprobada"]); self.assertFalse(t["finalizada"])   # falta R3 aprobada
        self.c.post(f"/api/pcb/{r3}/aprobar", json={})
        self.assertTrue(self._tarjeta_api(tid)["finalizada"])
        # el filtro del backend coincide con el campo
        ids = {x["id"] for x in db.list_tarjetas(estado="finalizada", limit=500)[0]}
        self.assertIn(tid, ids)
        # una prueba TQT posterior reprobada quita la finalización
        self._prueba_tqt(tid, result="reprobado", created=9e9)
        t = self._tarjeta_api(tid)
        self.assertFalse(t["aprobada"]); self.assertFalse(t["finalizada"])
        self.assertNotIn(tid, {x["id"] for x in db.list_tarjetas(estado="finalizada", limit=500)[0]})

    def test_finalizada_se_pierde_si_cambia_firmware_de_r3(self):
        tid, _, _, r3 = self._tarjeta()
        self._skytec(tid); self._prueba_tqt(tid)
        self.c.post(f"/api/pcb/{r3}/aprobar", json={})
        self.assertTrue(self._tarjeta_api(tid)["finalizada"])
        self.c.put(f"/api/pcb/{r3}/firmware", json={"firmware": "3.3"})
        self.assertFalse(self._tarjeta_api(tid)["finalizada"])

    def test_sin_skytec_o_sin_mac_no_finaliza(self):
        tid, _, _, r3 = self._tarjeta(mac_ok=False)
        self._prueba_tqt(tid); self.c.post(f"/api/pcb/{r3}/aprobar", json={})
        t = self._tarjeta_api(tid)
        self.assertFalse(t["finalizada"])   # sin MAC (ni Skytec)


if __name__ == "__main__":
    unittest.main()
