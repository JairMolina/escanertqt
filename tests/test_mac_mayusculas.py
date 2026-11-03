"""Las MAC se ven y se guardan siempre en MAYÚSCULAS (AA:BB:CC:DD:EE:FF)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import re
import unittest

from app.database import db, inventario as inv
from app.services.dymo_service import DymoService

from _aislamiento import crear_par, nuevo_lote

MAYUS = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


_n = [0]


def mac_letras() -> str:
    """MAC unicast con letras a-f en sus octetos (para distinguir mayúsculas de minúsculas)."""
    _n[0] += 1
    return "0a:bc:de:fa:%02x:%02x" % (0xA0 + _n[0] // 16, 0xB0 + _n[0] % 16)


class MacMayusculas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.lote = nuevo_lote()["id"]

    def test_01_guardar_minusculas_se_almacena_en_mayusculas(self):
        t = crear_par(self.lote)
        for clave in ("mac_r1", "mac_r2"):
            self.assertRegex(t[clave], MAYUS)
        p = db.get_tarjeta_by_id(t["id"])
        with db.get_db() as c:
            nueva = mac_letras()
            c.execute("UPDATE pcb_inventario SET mac=NULL WHERE id=?", (p["pcb_r1_id"],))
            inv.set_mac(p["pcb_r1_id"], nueva.replace(":", "-"), "t", conn=c)
            fila = c.execute("SELECT mac FROM pcb_inventario WHERE id=?", (p["pcb_r1_id"],)).fetchone()
        self.assertEqual(fila["mac"], nueva.upper())

    def test_02_trama_dymo_en_mayusculas(self):
        t = crear_par(self.lote)
        lin = DymoService.trama_lineas(db.get_tarjeta_by_id(t["id"]))
        self.assertRegex(lin[1], MAYUS)
        self.assertRegex(lin[3], MAYUS)

    def test_03_migracion_pasa_a_mayusculas_e_idempotente(self):
        t = crear_par(self.lote)
        p = db.get_tarjeta_by_id(t["id"])
        with db.get_db() as c:
            c.execute("UPDATE pcb_inventario SET mac=? WHERE id=?", (mac_letras(), p["pcb_r1_id"]))
            r1 = c.execute("SELECT mac FROM pcb_inventario WHERE id=?", (p["pcb_r1_id"],)).fetchone()["mac"]
            self.assertEqual(r1, r1.lower())
            self.assertGreaterEqual(db.asegurar_macs_mayusculas(c)["pcb_inventario.mac"], 1)
            self.assertEqual(c.execute("SELECT mac FROM pcb_inventario WHERE id=?", (p["pcb_r1_id"],)).fetchone()["mac"], r1.upper())
            self.assertEqual(db.asegurar_macs_mayusculas(c)["pcb_inventario.mac"], 0)

    def test_04_migracion_no_toca_colisiones(self):
        a, b = crear_par(self.lote), crear_par(self.lote)
        pa, pb = db.get_tarjeta_by_id(a["id"]), db.get_tarjeta_by_id(b["id"])
        with db.get_db() as c:
            mac = mac_letras().upper()
            c.execute("UPDATE pcb_inventario SET mac=? WHERE id=?", (mac, pa["pcb_r1_id"]))
            c.execute("UPDATE pcb_inventario SET mac=LOWER(?) WHERE id=?", (mac, pb["pcb_r1_id"]))
            antes = len(db.MIGRATION_WARNINGS)
            db.asegurar_macs_mayusculas(c)
            self.assertEqual(c.execute("SELECT mac FROM pcb_inventario WHERE id=?", (pb["pcb_r1_id"],)).fetchone()["mac"], mac.lower())
            self.assertGreater(len(db.MIGRATION_WARNINGS), antes)
            c.execute("UPDATE pcb_inventario SET mac=NULL WHERE id=?", (pb["pcb_r1_id"],))

    def test_05_frontend_sin_minusculas_en_macs(self):
        from pathlib import Path
        js = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
        for nombre in ("consultar.js", "escritorio.js", "sec_inventario.js", "dymo.js", "sec_macs.js"):
            txt = (js / nombre).read_text(encoding="utf-8")
            self.assertNotRegex(txt, r"mac[^\n]{0,40}\)\.toLowerCase\(\)\s*:\s*''|\.mac\)\.toLowerCase\(\) :", nombre)
            self.assertNotIn("String(p.mac).toLowerCase()", txt, nombre)


if __name__ == "__main__":
    unittest.main()
