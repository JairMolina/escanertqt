"""QA de Recibir: formatos del QR, duplicados, concurrencia, huecos/avisos, confirmar, manual, editar, versión, eliminar, ajustes."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import db, inventario as inv
from app.main import app

from _aislamiento import verificar_aislamiento


class Base(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "qa.db"
        db.init_db(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def esc(self, codigo, **kw):
        return inv.escanear_pcb(codigo, db_path=self.path, **kw)


class TestFormatosQR(Base):
    def test_formatos_validos(self):
        for crudo, nombre in (("TQT-R3-V30-0084", "TQT-R3-V30-0084"), ("tqt-r3-v30-0085", "TQT-R3-V30-0085"),
                              ("  TQT R1 V30 0021 ", "TQT-R1-V30-0021"), ("TQT_R2_V5_7", "TQT-R2-V5-0007"),
                              ("TQT-R1-V999-9999", "TQT-R1-V999-9999"), ("TQT-R1-V30-0013\x00", "TQT-R1-V30-0013"),
                              ("TQT-R1-V030-0001", "TQT-R1-V30-0001")):
            r = self.esc(crudo)
            self.assertEqual((r["resultado"], r["pcb"]["nombre"]), ("AGREGADA", nombre), crudo)

    def test_formatos_invalidos(self):
        for crudo in ("TQT-R1-V1234-0001", "TQT-R1-V30-00001", "TQT-R4-V30-0001", "   ", "x" * 200, "0084",
                      "' OR 1=1 --", "<script>alert(1)</script>", "TQT-R1-V-0010", "TQT-R1V300009",
                      "TQT-R1-V30-０００２", "TQT-R1-V30-٠٠١١",  # dígitos Unicode no son series
                      "TQT-R1-V30-0000", "TQT-R1-V0-0001", "TQT-R1-V000-0001"):  # serie 0 y versión 0 no existen
            r = self.esc(crudo)
            self.assertEqual(r["resultado"], "INVALIDA", crudo)
            self.assertIsNone(r["pcb"])
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["total"], 0)

    def test_inyeccion_no_rompe_nada(self):
        r = self.esc("TQT-R1-V30-0003'; DROP TABLE pcb_inventario;--")
        self.assertEqual(r["resultado"], "AGREGADA")
        self.assertEqual(self.esc("x'); DROP TABLE pcb_inventario;--")["resultado"], "INVALIDA")
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["total"], 1)

    def test_version_normalizada_no_duplica(self):
        self.assertEqual(self.esc("TQT-R1-V30-0001")["resultado"], "AGREGADA")
        self.assertEqual(self.esc("TQT-R1-V030-0001")["resultado"], "DUPLICADA")

    def test_tipo_forzado_y_version(self):
        r = self.esc("84", tipo_forzado="r2")
        self.assertEqual(r["pcb"]["nombre"], "TQT-R2-V30-0084")
        inv.set_version_defecto("31", db_path=self.path)
        self.assertEqual(self.esc("85", tipo_forzado="R2")["pcb"]["nombre"], "TQT-R2-V31-0085")   # defecto
        self.assertEqual(self.esc("86", tipo_forzado="R2", version="V32")["pcb"]["nombre"], "TQT-R2-V32-0086")
        self.assertEqual(self.esc("TQT-R1-V33-0090", tipo_forzado="R2", version="31")["pcb"]["nombre"], "TQT-R1-V33-0090")  # el QR manda
        for cod, kw in (("84", {}), ("12345", {"tipo_forzado": "R1"}), ("0", {"tipo_forzado": "R1"}),
                        ("5", {"tipo_forzado": "X"}), ("5", {"tipo_forzado": "R1", "version": "abc"})):
            self.assertEqual(self.esc(cod, **kw)["resultado"], "INVALIDA", (cod, kw))

    def test_duplicada_en_cada_estado(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        self.assertIn("recepción", self.esc("TQT-R1-V30-0001")["mensaje"])
        inv.confirmar_recepcion([a], db_path=self.path)
        r = self.esc("TQT-R1-V30-0001")
        self.assertEqual((r["resultado"], r["pcb"]["estado_ciclo"]), ("DUPLICADA", "DISPONIBLE"))
        b = self.esc("TQT-R2-V30-0001")["pcb"]["id"]
        inv.confirmar_recepcion([b], db_path=self.path)
        lote = db.get_active_lote(db_path=self.path)["id"]
        inv.crear_tarjeta(lote, None, a, b, None, db_path=self.path)
        r = self.esc("TQT-R1-V30-0001")
        self.assertEqual((r["resultado"], r["pcb"]["estado_ciclo"], r["pcb"]["ranura"]), ("DUPLICADA", "ASIGNADA", "R1"))
        c = self.esc("TQT-R3-V30-0001")["pcb"]["id"]
        inv.eliminar_pcb(c, db_path=self.path)                       # borrada de verdad: vuelve a poder escanearse
        self.assertEqual(self.esc("TQT-R3-V30-0001")["resultado"], "AGREGADA")
        d = self.esc("TQT-R3-V30-0002")["pcb"]["id"]
        with db.transaction(self.path) as cx:
            cx.execute("UPDATE pcb_inventario SET estado_ciclo='BAJA' WHERE id=?", (d,))
        r = self.esc("TQT-R3-V30-0002")
        self.assertEqual((r["resultado"], r["pcb"]["estado_ciclo"]), ("DUPLICADA", "BAJA"))


class TestConcurrencia(Base):
    def test_mismo_qr_20_hilos(self):
        with ThreadPoolExecutor(20) as ex:
            res = list(ex.map(lambda _: self.esc("TQT-R1-V30-0042"), range(20)))
        self.assertEqual(sum(r["resultado"] == "AGREGADA" for r in res), 1)
        self.assertEqual(sum(r["resultado"] == "DUPLICADA" for r in res), 19)
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["total"], 1)

    def test_qr_distintos_y_repetidos_en_paralelo(self):
        codigos = [f"TQT-R{1 + i % 3}-V30-{i // 3 + 1:04d}" for i in range(45)] * 2   # 45 únicos, cada uno dos veces
        with ThreadPoolExecutor(16) as ex:
            res = list(ex.map(self.esc, codigos))
        self.assertEqual(sum(r["resultado"] == "AGREGADA" for r in res), 45)
        self.assertEqual(sum(r["resultado"] == "DUPLICADA" for r in res), 45)
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"], {"R1": 15, "R2": 15, "R3": 15, "total": 45})

    def test_api_concurrente_sin_locked(self):
        client = TestClient(app)
        codigos = [f"TQT-R1-V77-{i:04d}" for i in range(1, 13)] * 2
        with ThreadPoolExecutor(12) as ex:
            res = list(ex.map(lambda c: client.post("/api/pcb/escanear", json={"codigo": c}), codigos))
        self.assertTrue(all(r.status_code == 200 for r in res), [r.text for r in res if r.status_code != 200][:2])
        res = [r.json()["resultado"] for r in res]
        self.assertEqual((res.count("AGREGADA"), res.count("DUPLICADA")), (12, 12))
        ids = [r["id"] for r in client.get("/api/pcb", params={"q": "V77-", "limit": 100}).json()["items"]]
        for i in ids:
            client.delete(f"/api/pcb/{i}")


class TestRecepcionLogica(Base):
    def test_huecos_y_avisos(self):
        for c in ("TQT-R1-V30-0001", "TQT-R1-V30-0004", "TQT-R1-V30-0005", "TQT-R2-V30-0002", "TQT-R2-V30-0003",
                  "TQT-R3-V30-0007"):
            self.esc(c)
        d = inv.listar_recepcion(db_path=self.path)
        self.assertEqual(d["conteos"], {"R1": 3, "R2": 2, "R3": 1, "total": 6})
        self.assertEqual(d["huecos"], {"R1": ["0002", "0003"], "R2": [], "R3": []})
        self.assertTrue(any("Desbalance" in a for a in d["avisos"]))
        self.assertTrue(any(a.startswith("R1: faltan 2") for a in d["avisos"]))
        self.assertEqual(len(d["items"]), 6)

    def test_hueco_no_cuenta_series_ya_existentes_fuera_del_borrador(self):
        a = self.esc("TQT-R1-V30-0002")["pcb"]["id"]
        inv.confirmar_recepcion([a], db_path=self.path)               # 0002 ya recibida antes
        self.esc("TQT-R1-V30-0001")
        self.esc("TQT-R1-V30-0003")
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["huecos"]["R1"], [])

    def test_huecos_recortados_avisan_que_son_mas(self):
        self.esc("TQT-R1-V30-0001")
        self.esc("TQT-R1-V30-0500")
        d = inv.listar_recepcion(db_path=self.path)
        self.assertEqual(len(d["huecos"]["R1"]), 200)
        self.assertTrue(any("faltan 200+" in a for a in d["avisos"]), d["avisos"])

    def test_balanceado_sin_avisos_y_vacio(self):
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["avisos"], [])
        for t in ("R1", "R2", "R3"):
            for n in (1, 2):
                self.esc(f"TQT-{t}-V30-{n:04d}")
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["avisos"], [])

    def test_confirmar_todo_parcial_doble_y_ajenos(self):
        ids = [self.esc(f"TQT-R1-V30-{n:04d}")["pcb"]["id"] for n in (1, 2, 3)]
        r = inv.confirmar_recepcion(ids[:1], db_path=self.path)
        self.assertEqual((r["confirmadas"], r["omitidas"]), (1, []))
        r = inv.confirmar_recepcion(ids[:2], db_path=self.path)     # el 1 ya no es borrador
        self.assertEqual((r["confirmadas"], r["omitidas"]), (1, [ids[0]]))
        r = inv.confirmar_recepcion([99999], db_path=self.path)
        self.assertEqual((r["confirmadas"], r["omitidas"]), (0, [99999]))
        r = inv.confirmar_recepcion(None, db_path=self.path)
        self.assertEqual(r["confirmadas"], 1)
        r = inv.confirmar_recepcion(None, db_path=self.path)        # doble confirmación
        self.assertEqual((r["confirmadas"], r["ids"]), (0, []))
        self.assertEqual(r["disponibles"]["R1"], 3)

    def test_no_confirma_pcb_de_otros_estados(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        b = self.esc("TQT-R2-V30-0001")["pcb"]["id"]
        inv.confirmar_recepcion(None, db_path=self.path)
        lote = db.get_active_lote(db_path=self.path)["id"]
        inv.crear_tarjeta(lote, None, a, b, None, db_path=self.path)
        r = inv.confirmar_recepcion([a, b], db_path=self.path)
        self.assertEqual((r["confirmadas"], sorted(r["omitidas"])), (0, sorted([a, b])))
        self.assertEqual(inv.get_pcb(a, db_path=self.path)["estado_ciclo"], "ASIGNADA")


class TestManual(Base):
    def man(self, **kw):
        return inv.registrar_manual(db_path=self.path, **kw)

    def test_siguiente_serie_y_cantidad(self):
        self.esc("TQT-R1-V30-0010")
        r = self.man(tipo="R1", cantidad=3)
        self.assertEqual([p["serie"] for p in r["pcbs"]], ["0011", "0012", "0013"])
        self.assertTrue(all(p["origen"] == "MANUAL" and p["estado_ciclo"] == "RECIBIDA" for p in r["pcbs"]))
        self.assertEqual([p["serie"] for p in self.man(tipo="R2")["pcbs"]], ["0001"])   # otro tipo arranca en 1

    def test_serie_indicada_y_conflicto_todo_o_nada(self):
        self.man(tipo="R1", serie="5")
        with self.assertRaises(db.ConflictoError):
            self.man(tipo="R1", serie="4", cantidad=3)               # 4,5,6: choca el 5
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["R1"], 1)

    def test_topes(self):
        for kw in ({"tipo": "R1", "cantidad": 0}, {"tipo": "R1", "cantidad": 201}, {"tipo": "R1", "serie": "9999", "cantidad": 2},
                   {"tipo": "R9"}, {"tipo": "R1", "serie": "0"}, {"tipo": "R1", "serie": "12345"}, {"tipo": "R1", "version": "0"},
                   {"tipo": "R1", "version": "1000"}):
            with self.assertRaises(ValueError, msg=kw):
                self.man(**kw)
        self.assertEqual(len(self.man(tipo="R1", cantidad=200)["pcbs"]), 200)

    def test_version_defecto_y_explicita(self):
        self.assertEqual(self.man(tipo="R1")["pcbs"][0]["version"], "30")
        inv.set_version_defecto("V45", db_path=self.path)
        self.assertEqual(self.man(tipo="R1")["pcbs"][0]["version"], "45")
        self.assertEqual(self.man(tipo="R1", version="v46")["pcbs"][0]["version"], "46")


class TestEditarYEliminar(Base):
    def test_editar_y_choques(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        b = self.esc("TQT-R1-V30-0002")["pcb"]["id"]
        p = inv.editar_pcb(a, tipo="R2", version="31", serie="7", db_path=self.path)
        self.assertEqual(p["nombre"], "TQT-R2-V31-0007")
        with self.assertRaises(db.ConflictoError):
            inv.editar_pcb(b, tipo="R2", version="31", serie="7", db_path=self.path)
        for kw in ({"serie": "0"}, {"serie": "abc"}, {"version": "0"}, {"tipo": "R7"}):
            with self.assertRaises(ValueError, msg=kw):
                inv.editar_pcb(b, db_path=self.path, **kw)
        self.assertEqual(inv.editar_pcb(b, db_path=self.path)["nombre"], "TQT-R1-V30-0002")   # sin cambios
        with self.assertRaises(db.NoEncontradoError):
            inv.editar_pcb(9999, serie="1", db_path=self.path)

    def test_editar_asignada_actualiza_tarjeta_y_no_deja_cambiar_tipo(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        b = self.esc("TQT-R2-V30-0001")["pcb"]["id"]
        inv.confirmar_recepcion(None, db_path=self.path)
        lote = db.get_active_lote(db_path=self.path)["id"]
        t = inv.crear_tarjeta(lote, None, a, b, None, db_path=self.path)
        inv.editar_pcb(a, version="31", db_path=self.path)
        self.assertEqual(db.get_tarjeta_by_id(t["id"], db_path=self.path)["nombre_r1"], "TQT-R1-V31-0001")
        with self.assertRaises(db.ConflictoError):
            inv.editar_pcb(a, tipo="R3", db_path=self.path)

    def test_version_masiva_todo_o_nada(self):
        ids = [self.esc(f"TQT-R1-V30-{n:04d}")["pcb"]["id"] for n in (1, 2, 3)]
        self.esc("TQT-R1-V31-0003")
        with self.assertRaises(db.ConflictoError):
            inv.cambiar_version_masiva(ids, "31", db_path=self.path)
        self.assertEqual([inv.get_pcb(i, db_path=self.path)["version"] for i in ids], ["30"] * 3)
        with self.assertRaises(db.NoEncontradoError):
            inv.cambiar_version_masiva(ids[:2] + [9999], "32", db_path=self.path)
        r = inv.cambiar_version_masiva(ids[:2], "032", db_path=self.path)
        self.assertEqual((r["actualizadas"], r["version"]), (2, "32"))
        with self.assertRaises(ValueError):
            inv.cambiar_version_masiva(ids[:2], "0", db_path=self.path)

    def test_eliminar_por_estado(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        self.assertEqual(inv.eliminar_pcb(a, db_path=self.path)["accion"], "ELIMINADA")
        self.assertIsNone(inv.get_pcb(a, db_path=self.path))
        b = self.esc("TQT-R1-V30-0002")["pcb"]["id"]
        inv.confirmar_recepcion([b], db_path=self.path)
        self.assertEqual(inv.eliminar_pcb(b, db_path=self.path)["accion"], "ELIMINADA")
        c = self.esc("TQT-R1-V30-0003")["pcb"]["id"]
        d = self.esc("TQT-R2-V30-0003")["pcb"]["id"]
        inv.confirmar_recepcion(None, db_path=self.path)
        lote = db.get_active_lote(db_path=self.path)["id"]
        inv.crear_tarjeta(lote, None, c, d, None, db_path=self.path)
        with self.assertRaises(db.ConflictoError):
            inv.eliminar_pcb(c, db_path=self.path)
        with self.assertRaises(db.NoEncontradoError):
            inv.eliminar_pcb(c + 999, db_path=self.path)


class TestAPIRecepcion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.c = TestClient(app)

    def test_ajustes_valores_raros(self):
        antes = self.c.get("/api/ajustes").json()["version_defecto"]
        try:
            for v in ("", "abc", "V", "-1", "0", "000", "1000", "3 0", "1e2", "3.0", "٣٠", "３０", "x" * 6):
                self.assertIn(self.c.put("/api/ajustes", json={"version_defecto": v}).status_code, (400, 422), repr(v))
            for v in (None, 30, [], {}):
                self.assertEqual(self.c.put("/api/ajustes", json={"version_defecto": v}).status_code, 422)
            self.assertEqual(self.c.get("/api/ajustes").json()["version_defecto"], antes)
            self.assertEqual(self.c.put("/api/ajustes", json={"version_defecto": "v031"}).json()["version_defecto"], "31")
        finally:
            self.c.put("/api/ajustes", json={"version_defecto": antes})

    def test_escanear_mal_formado_es_422_y_negocio_es_200(self):
        for body in ({}, {"codigo": ""}, {"codigo": None}, {"codigo": 5}, {"codigo": "x" * 301}):
            self.assertEqual(self.c.post("/api/pcb/escanear", json=body).status_code, 422, body)
        r = self.c.post("/api/pcb/escanear", json={"codigo": "basura"})
        self.assertEqual((r.status_code, r.json()["resultado"]), (200, "INVALIDA"))

    def test_flujo_api(self):
        r = self.c.post("/api/pcb/manual", json={"tipo": "R3", "version": "88", "serie": "10", "cantidad": 2})
        self.assertEqual(r.status_code, 200)
        ids = [p["id"] for p in r.json()["pcbs"]]
        self.assertEqual(self.c.post("/api/pcb/manual", json={"tipo": "R3", "version": "88", "serie": "11"}).status_code, 409)
        self.assertEqual(self.c.post("/api/pcb/manual", json={"tipo": "R3", "cantidad": 201}).status_code, 422)
        self.assertEqual(self.c.post("/api/pcb/manual", json={"tipo": "R3", "serie": "0"}).status_code, 400)
        self.assertEqual(self.c.patch(f"/api/pcb/{ids[0]}", json={"serie": "11"}).status_code, 409)
        self.assertEqual(self.c.patch(f"/api/pcb/{ids[0]}", json={"serie": "zz"}).status_code, 400)
        self.assertEqual(self.c.patch("/api/pcb/999999", json={"serie": "5"}).status_code, 404)
        self.assertEqual(self.c.post("/api/pcb/version", json={"ids": ids, "version": "89"}).json()["actualizadas"], 2)
        self.assertEqual(self.c.post("/api/pcb/version", json={"ids": [], "version": "89"}).status_code, 422)
        rc = self.c.post("/api/recepcion/confirmar", json={"ids": ids + [999999]}).json()
        self.assertEqual((rc["confirmadas"], rc["omitidas"]), (2, [999999]))
        self.assertEqual(self.c.post("/api/recepcion/confirmar", json={"ids": ids}).json()["confirmadas"], 0)
        for i in ids:
            self.assertEqual(self.c.delete(f"/api/pcb/{i}").status_code, 204)
        self.assertEqual(self.c.delete(f"/api/pcb/{ids[0]}").status_code, 404)
        self.assertEqual(self.c.delete("/api/pcb/abc").status_code, 422)


if __name__ == "__main__":
    unittest.main()
