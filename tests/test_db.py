"""SQLite nativa: pragmas, lotes, esquema v2, unicidad, estadísticas y migración de bases heredadas (v0/v1 -> v2)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database import db, inventario as inv
from app.database.db import ConflictoError
from app.database.models import is_valid_mac, normalize_mac

from _aislamiento import crear_par, mac_unica, verificar_aislamiento

SCHEMA_HEREDADO = """
CREATE TABLE lotes_mensuales (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo_lote TEXT NOT NULL UNIQUE, mes INTEGER NOT NULL,
    anio INTEGER NOT NULL, ruta_excel TEXT, activo INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE tarjetas_produccion (id INTEGER PRIMARY KEY AUTOINCREMENT, lote_id INTEGER NOT NULL REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    id_tarjeta_num TEXT NOT NULL, nombre_r1 TEXT NOT NULL, mac_r1 TEXT NOT NULL, firmware_r1 TEXT DEFAULT 'v1.0.0',
    nombre_r2 TEXT NOT NULL, mac_r2 TEXT NOT NULL, firmware_r2 TEXT DEFAULT 'v1.0.0', semana_produccion INTEGER,
    fecha_proyectada TEXT, fecha_real TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_lote_tarjeta UNIQUE (lote_id, id_tarjeta_num));
CREATE TABLE catalogo_pcb (id INTEGER PRIMARY KEY AUTOINCREMENT, lote_id INTEGER NOT NULL REFERENCES lotes_mensuales(id) ON DELETE CASCADE,
    tipo_pcb TEXT NOT NULL CHECK(tipo_pcb IN ('R1','R2')), nombre_pcb TEXT NOT NULL, mac_address TEXT,
    estado_pcb TEXT NOT NULL DEFAULT 'FUNCIONAL' CHECK(estado_pcb IN ('FUNCIONAL','DEFECTUOSA','EN_REVISION','PENDIENTE','FALLA')),
    asignada_a_id INTEGER REFERENCES tarjetas_produccion(id) ON DELETE SET NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE pruebas_historial (id INTEGER PRIMARY KEY AUTOINCREMENT, tarjeta_id INTEGER NOT NULL UNIQUE REFERENCES tarjetas_produccion(id) ON DELETE CASCADE,
    soldadura TEXT NOT NULL DEFAULT 'APROBADO', programacion TEXT NOT NULL DEFAULT 'APROBADO', prueba_pcb TEXT NOT NULL DEFAULT 'APROBADO',
    integracion TEXT NOT NULL DEFAULT 'APROBADO', prueba_final TEXT NOT NULL DEFAULT 'APROBADO', estado_general TEXT NOT NULL DEFAULT 'FUNCIONAL',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE meses_lote (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
CREATE TABLE pcb (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
"""


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "test_db.db"
        db.init_db(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _tarjeta(self, lote_id, **kw):
        return crear_par(lote_id, path=self.path, **kw)

    def test_01_pragmas_y_esquema_v2(self):
        conn = db.connect(self.path)
        try:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 10000)
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for t in ("lotes_mensuales", "pcb_inventario", "tarjetas_produccion", "pruebas_historial", "escaneos", "ajustes"):
                self.assertIn(t, tablas)
            for viejo in ("catalogo_pcb", "meses_lote", "pcb"):
                self.assertNotIn(viejo, tablas)
        finally:
            conn.close()

    def test_02_init_db_es_idempotente(self):
        db.init_db(self.path)
        db.init_db(self.path)
        with db.get_db(self.path) as c:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM lotes_mensuales").fetchone()[0], 1)

    def test_03_lotes_activacion(self):
        l1 = db.create_lote("2027-10", 10, 2027, activo=True, db_path=self.path)
        l2 = db.create_lote("2027-11", 11, 2027, activo=True, db_path=self.path)
        self.assertEqual(l2["activo"], 1)
        self.assertEqual(db.get_lote_by_id(l1["id"], db_path=self.path)["activo"], 0)
        self.assertEqual(db.set_active_lote(l1["id"], db_path=self.path)["activo"], 1)
        self.assertEqual(db.get_active_lote(db_path=self.path)["id"], l1["id"])
        self.assertIsNone(db.set_active_lote(987654, db_path=self.path))

    def test_04_mac_unica_en_toda_la_bd(self):
        lote = db.create_lote("2026-12", 12, 2026, activo=True, db_path=self.path)
        a = self._tarjeta(lote["id"])
        b = self._tarjeta(lote["id"])
        with self.assertRaises(ConflictoError) as ctx:  # misma MAC (en minúsculas) en otra PCB
            inv.set_mac(b["pcb_r1_id"], a["mac_r1"].lower(), db_path=self.path)
        self.assertIn("ya pertenece", str(ctx.exception))
        # R2 de una == R1 de otra: también choca
        with self.assertRaises(ConflictoError):
            inv.set_mac(b["pcb_r2_id"], a["mac_r1"], db_path=self.path)
        # El índice único frena el duplicado aunque el código falle
        conn = db.connect(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE pcb_inventario SET mac = ? WHERE id = ?", (a["mac_r1"], b["pcb_r1_id"]))
        finally:
            conn.close()

    def test_05_normalizacion_mac(self):
        self.assertEqual(normalize_mac("aabbccddeeff"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(normalize_mac("aa-bb-cc-dd-ee-ff"), "AA:BB:CC:DD:EE:FF")
        self.assertTrue(is_valid_mac("112233445566"))
        self.assertFalse(is_valid_mac("INVALID-MAC"))

    def test_06_stats_por_estado_derivado_e_incompletas(self):
        lote = db.create_lote("2026-08", 8, 2026, activo=True, db_path=self.path)
        t1, t2, _ = (self._tarjeta(lote["id"]) for _ in range(3))
        for etapa in ("soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final"):
            db.set_prueba(t1["id"], etapa, "OK", db_path=self.path)
        db.set_prueba(t2["id"], "soldadura", "FALLA", db_path=self.path)

        s = db.get_stats(lote["id"], db_path=self.path)
        self.assertEqual((s["total_tarjetas"], s["funcionales"], s["defectuosas"], s["pendientes"]), (3, 1, 1, 1))
        self.assertEqual(round(s["porcentaje_aprobacion"], 2), 33.33)
        self.assertEqual((s["total_r1_escaneados"], s["total_r2_escaneados"], s["total_r3_escaneados"], s["incompletas"]), (3, 3, 0, 0))

        inv.asignar_pcb(t1["id"], "R2", None, db_path=self.path)  # sacar R2 de una tarjeta LIBERADA
        s = db.get_stats(lote["id"], db_path=self.path)
        self.assertEqual(s["incompletas"], 1)
        self.assertEqual(s["funcionales"], 0)  # sin R2 ya no puede estar LIBERADA

    def test_07_una_tarjeta_por_pcb_y_por_numero(self):
        lote = db.create_lote("2026-06", 6, 2026, db_path=self.path)
        t = self._tarjeta(lote["id"])
        conn = db.connect(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):  # la misma PCB en dos tarjetas
                conn.execute("INSERT INTO tarjetas_produccion (lote_id, id_tarjeta_num, pcb_r1_id) VALUES (?,?,?)",
                             (lote["id"], "9999", t["pcb_r1_id"]))
            with self.assertRaises(sqlite3.IntegrityError):  # mismo número en el lote
                conn.execute("INSERT INTO tarjetas_produccion (lote_id, id_tarjeta_num) VALUES (?,?)", (lote["id"], t["id_tarjeta_num"]))
        finally:
            conn.close()

    # ------------------------------------------------------------------ migración
    def _legacy(self, nombre):
        ruta = Path(self.tmp.name) / nombre
        c = sqlite3.connect(ruta)
        c.executescript(SCHEMA_HEREDADO)
        c.execute("INSERT INTO lotes_mensuales (codigo_lote, mes, anio, activo) VALUES ('2026-09', 9, 2026, 1)")
        return ruta, c

    def test_08_migracion_v1_a_v2_conserva_todo(self):
        ruta, c = self._legacy("legacy.db")
        macs = {}
        for i, (sold, gen) in enumerate((("APROBADO", "FUNCIONAL"), ("DEFECTUOSO", "DEFECTUOSA")), start=1):
            macs[i] = (mac_unica(), mac_unica())
            c.execute("INSERT INTO tarjetas_produccion (lote_id,id_tarjeta_num,nombre_r1,mac_r1,nombre_r2,mac_r2,semana_produccion) VALUES (1,?,?,?,?,?,38)",
                      (f"000{i}", f"TQT-R1-V30-000{i}", macs[i][0], f"TQT-R2-V30-000{i}", macs[i][1]))
            c.execute("INSERT INTO pruebas_historial (tarjeta_id, soldadura, estado_general) VALUES (?,?,?)", (i, sold, gen))
        c.execute("UPDATE pruebas_historial SET programacion='PENDIENTE' WHERE tarjeta_id=1")
        # PCB suelta del catálogo con MAC (no está en ninguna tarjeta) y una repetida por importaciones
        c.execute("INSERT INTO catalogo_pcb (lote_id,tipo_pcb,nombre_pcb,mac_address,estado_pcb) VALUES (1,'R1','TQT-R1-V30-0077',?,'FUNCIONAL')", (mac_unica(),))
        c.execute("INSERT INTO catalogo_pcb (lote_id,tipo_pcb,nombre_pcb,estado_pcb) VALUES (1,'R1','TQT-R1-V30-0001','DEFECTUOSA')")
        c.execute("INSERT INTO catalogo_pcb (lote_id,tipo_pcb,nombre_pcb,estado_pcb) VALUES (1,'R1','TQT-R1-V30-0001','EN_REVISION')")
        c.commit()
        c.close()

        db.init_db(ruta)
        db.init_db(ruta)  # idempotente

        conn = db.connect(ruta)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for viejo in ("catalogo_pcb", "meses_lote", "pcb"):
                self.assertNotIn(viejo, tablas)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

        ts = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=1, db_path=ruta)[0]}
        self.assertEqual(set(ts), {"0001", "0002"})
        for i, num in ((1, "0001"), (2, "0002")):
            t = ts[num]
            self.assertEqual((t["nombre_r1"], t["mac_r1"], t["nombre_r2"], t["mac_r2"]),
                             (f"TQT-R1-V30-000{i}", macs[i][0], f"TQT-R2-V30-000{i}", macs[i][1]))
            self.assertEqual((t["r1"]["estado_ciclo"], t["completa"], t["semana_produccion"]), ("ASIGNADA", True, 38))
        # pruebas: vocabulario canónico y estado derivado
        self.assertEqual((ts["0001"]["soldadura"], ts["0001"]["programacion"], ts["0001"]["estado_general"]), ("OK", "PENDIENTE", "EN PROCESO"))
        self.assertEqual((ts["0002"]["soldadura"], ts["0002"]["estado_general"]), ("FALLA", "DETENIDO"))
        # la PCB suelta del catálogo pasó al inventario como DISPONIBLE con su MAC
        sueltas = inv.listar_pcb(estado_ciclo="DISPONIBLE", db_path=ruta)["items"]
        self.assertEqual([p["nombre"] for p in sueltas], ["TQT-R1-V30-0077"])
        self.assertIsNotNone(sueltas[0]["mac"])
        self.assertEqual(inv.get_version_defecto(db_path=ruta), "30")

    def test_09_migracion_avisa_si_hay_macs_duplicadas_heredadas(self):
        ruta, c = self._legacy("legacy_dup.db")
        m = mac_unica()
        for i in (1, 2):
            c.execute("INSERT INTO tarjetas_produccion (lote_id,id_tarjeta_num,nombre_r1,mac_r1,nombre_r2,mac_r2) VALUES (1,?,?,?,?,?)",
                      (f"000{i}", f"TQT-R1-V30-000{i}", m, f"TQT-R2-V30-000{i}", mac_unica()))
        c.commit()
        c.close()
        antes = len(db.MIGRATION_WARNINGS)
        db.init_db(ruta)  # no debe romper el arranque
        self.assertGreater(len(db.MIGRATION_WARNINGS), antes)
        self.assertIn(m, db.MIGRATION_WARNINGS[-1])
        ts = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=1, db_path=ruta)[0]}
        self.assertEqual(ts["0001"]["mac_r1"], m)
        self.assertIsNone(ts["0002"]["mac_r1"])  # la segunda quedó sin MAC, no se perdió la tarjeta

    def test_10_migracion_de_pcb_con_nombre_no_canonico(self):
        ruta, c = self._legacy("legacy_nombres.db")
        c.execute("INSERT INTO tarjetas_produccion (lote_id,id_tarjeta_num,nombre_r1,mac_r1,nombre_r2,mac_r2) VALUES (1,'0042','PCB-R1-0042',?,'TQT-R2-V31-0042',?)",
                  (mac_unica(), mac_unica()))
        c.commit()
        c.close()
        db.init_db(ruta)
        t = db.list_tarjetas(lote_id=1, db_path=ruta)[0][0]
        self.assertEqual((t["nombre_r1"], t["nombre_r2"]), ("TQT-R1-V30-0042", "TQT-R2-V31-0042"))


if __name__ == "__main__":
    unittest.main()
