import _aislamiento  # noqa: F401  (debe ser lo primero)
"""Etiquetas DYMO del gabinete Skudo AntiJammer: vista previa SVG, XML de DYMO Connect y cola de la DYMO compartida."""
import re
import unittest

from app.database import db
from app.main import app
from app.modulos import ANTIJAMMER, modulo_de_ruta
from app.services import antijammer_etiqueta as etq
from app.services import dymo_remoto, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestAntijammerDymo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.sin = cliente_sin_sesion(app)
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text
        assert cls.c.post("/api/antijammer/pcb/manual", json={"version": "1", "serie": "8052", "lote": "L-ETQ"}).status_code == 201
        assert cls.c.post("/api/antijammer/pcb/manual", json={"version": "1", "serie": "8053"}).status_code == 201

    def test_modulo_y_sesion(self):
        self.assertEqual(modulo_de_ruta("/api/antijammer/etiquetas/vista"), ANTIJAMMER)
        self.assertIn(self.sin.get("/api/antijammer/etiquetas/estado").status_code, (401, 403))

    def test_vista_previa(self):
        r = self.c.get("/api/antijammer/etiquetas/vista", params={"codigos": "SJ-V1-8052,8053,SJ-V1-9999,TPMS_V1_0004"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual([i["nombre"] for i in d["items"]], ["SJ-V1-8052", "SJ-V1-8053"])
        self.assertEqual(len(d["faltan"]), 2)
        a, b = d["items"]
        self.assertEqual(a["lote"], "L-ETQ")
        self.assertRegex(a["fecha"], r"^\d{2}/\d{2}/\d{4}$")
        self.assertIn('width="57mm" height="32mm"', a["svg"])
        self.assertIn("SKUDO ANTIJAMMER", a["svg"])
        self.assertIn(">SJ-V1-8052<", a["svg"])
        self.assertIn("Lote L-ETQ", a["svg"])
        self.assertNotIn("Lote", b["svg"])   # sin lote no se imprime la línea

    def test_tipo_rx_tx(self):
        with db.get_db() as c:
            pid = c.execute("SELECT id FROM antijammer_pcb WHERE nombre='SJ-V1-8052'").fetchone()["id"]
            c.execute("CREATE TABLE IF NOT EXISTS costeo_pcb_tarjeta (modulo TEXT NOT NULL, pcb_id INTEGER NOT NULL, tarjeta TEXT NOT NULL, PRIMARY KEY (modulo, pcb_id))")
            c.execute("INSERT OR REPLACE INTO costeo_pcb_tarjeta VALUES ('skudo-antijammer', ?, 'TX')", (pid,))
        self.assertEqual(etq.datos_de("SJ-V1-8052")["tipo"], "TX")
        self.assertEqual(etq.datos_de("SJ-V1-8053")["tipo"], "")
        _f, _qr, _m, _p, lineas = etq.diseno(etq.datos_de("SJ-V1-8052"))
        self.assertEqual(lineas[0][0], "SKUDO ANTIJAMMER TX")

    def test_diseno_dentro_de_zona_segura(self):
        d = {"nombre": "SJ-V1.1-0052", "lote": "LOTE-MUY-LARGO-DE-PRUEBA-2026", "fecha": "04/11/2026"}
        f, qr, _m, _p, lineas = etq.diseno(d)
        m = 1.5
        for c in [qr] + [x[1] for x in lineas]:
            self.assertGreaterEqual(c.x, m - 1e-6); self.assertGreaterEqual(c.y, m - 1e-6)
            self.assertLessEqual(c.derecha, f.ancho_mm - m + 1e-6); self.assertLessEqual(c.y + c.h, f.alto_mm - m + 1e-6)
        self.assertTrue(lineas[2][0].endswith("…"))   # el lote largo se recorta

    def test_xml_dymo_connect(self):
        r = self.c.get("/api/antijammer/etiquetas/SJ-V1-8052/xml")
        self.assertEqual(r.status_code, 200, r.text)
        x = r.text
        self.assertIn("<BarcodeFormat>QRCode</BarcodeFormat>", x)
        self.assertIn("<DataString>SJ-V1-8052</DataString>", x)
        self.assertIn("SKUDO ANTIJAMMER", x)
        self.assertEqual(len(re.findall("<TextObject>", x)), 4)
        self.assertEqual(self.c.get("/api/antijammer/etiquetas/SJ-V1-9999/xml").status_code, 404)

    def test_imprimir_compartida(self):
        with db.get_db() as conn:
            dymo_remoto.init()
            conn.execute("UPDATE dymo_trabajos SET estado='cancelada' WHERE estado IN ('pendiente','enviada')")
        r = self.c.post("/api/antijammer/etiquetas/imprimir", json={"codigos": ["SJ-V1-8052"]})
        self.assertEqual(r.status_code, 503, r.text)
        ag = dymo_remoto.agente_crear("Raspberry AJ")
        dymo_remoto.latido(ag["id"], {"impresora_ok": True})
        self.assertTrue(self.c.get("/api/antijammer/etiquetas/estado").json()["disponible"])
        r = self.c.post("/api/antijammer/etiquetas/imprimir", json={"codigos": ["SJ-V1-8052", "8053", "SJ-V1-9999"], "copias": 2})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["encolados"], 2)
        self.assertEqual(len(d["errores"]), 1)
        j = dymo_remoto.tomar(ag["id"])
        self.assertEqual((j["tipo"], j["copias"], j["params"]), ("antijammer", 2, {"nombre": "SJ-V1-8052"}))
        cab = {"Authorization": "Bearer " + ag["token"]}
        s = self.c.get(f"/api/dymo/remoto/agente/trabajos/{j['id']}/svg", headers=cab)
        self.assertEqual(s.status_code, 200, s.text)
        self.assertIn("SKUDO ANTIJAMMER", s.text)
        self.assertEqual(self.c.post("/api/antijammer/etiquetas/imprimir", json={"codigos": []}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
