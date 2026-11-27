import _aislamiento  # noqa: F401  (debe ser lo primero)
"""Etiquetas DYMO del gabinete Skudo AntiJammer (v1.4.104): solo número de pareja y RX/TX, se imprimen por pareja."""
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
        for s in ("8052", "8053", "8054"):
            assert cls.c.post("/api/antijammer/pcb/manual", json={"version": "1", "serie": s, "lote": "L-ETQ"}).status_code == 201
        r = cls.c.post("/api/antijammer/parejas", json={"rx": "8053", "tx": "8052", "numero": 77})
        assert r.status_code == 201, r.text

    def test_modulo_y_sesion(self):
        self.assertEqual(modulo_de_ruta("/api/antijammer/etiquetas/vista"), ANTIJAMMER)
        self.assertIn(self.sin.get("/api/antijammer/etiquetas/estado").status_code, (401, 403))

    def test_vista_previa_por_pareja(self):
        r = self.c.get("/api/antijammer/etiquetas/vista", params={"codigos": "SJ-V1-8052,SJ-V1-8054,SJ-V1-9999,TPMS_V1_0004"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        # pedir la TX trae también su RX (RX primero); la placa sin número y las ajenas no se imprimen
        self.assertEqual([(i["nombre"], i["tipo"], i["numero"]) for i in d["items"]],
                         [("SJ-V1-8053", "RX", 77), ("SJ-V1-8052", "TX", 77)])
        self.assertEqual(len(d["faltan"]), 3)
        self.assertTrue(any("no tiene número de pareja" in e["detail"] for e in d["errores"]))
        a = d["items"][0]["svg"]
        self.assertIn('width="57mm" height="32mm"', a)
        self.assertIn(">SKUDO 77<", a)
        self.assertIn(">RX<", a)
        self.assertIn("<rect x=", a)   # v1.4.106: lleva QR
        for fuera in ("PAREJA", ">SJ-V1-8053<", "Lote"):   # el nombre va solo dentro del QR, no como texto
            self.assertNotIn(fuera, a)

    def test_diseno_dentro_de_zona_segura(self):
        f, qr, ppm, lineas = etq.diseno({"nombre": "SJ-V1-0001", "numero": 9999, "tipo": "TX"})
        m = 1.5
        self.assertEqual([t for t, *_ in lineas], ["SKUDO 9999", "TX"])
        # QR dentro de la zona segura, a la izquierda y legible (>= 4 puntos por módulo); el texto a su derecha
        self.assertGreaterEqual(ppm, 4)
        self.assertGreaterEqual(qr.x, m - 1e-6)
        self.assertGreaterEqual(qr.y, m - 1e-6)
        self.assertLessEqual(qr.y + qr.h, f.alto_mm - m + 1e-6)
        for _t, c, pt, _b in lineas:
            self.assertGreaterEqual(c.x, qr.x + qr.w)
            self.assertGreaterEqual(c.y, m - 1e-6)
            self.assertLessEqual(c.y + c.h, f.alto_mm - m + 1e-6)
            self.assertLessEqual(c.x + c.w, f.ancho_mm - m + 1e-6)
            self.assertLessEqual(len(_t) * 0.55 * pt * 25.4 / 72, c.w + 1e-6)
        self.assertGreater(lineas[1][2], lineas[0][2])   # RX/TX más grande que el número

    def test_xml_dymo_connect(self):
        r = self.c.get("/api/antijammer/etiquetas/SJ-V1-8052/xml")
        self.assertEqual(r.status_code, 200, r.text)
        x = r.text
        self.assertIn("<BarcodeFormat>QRCode</BarcodeFormat>", x)
        self.assertIn("<DataString>SJ-V1-8052</DataString>", x)   # el QR abre la ficha de esa placa en Consultar
        self.assertIn("<Text>SKUDO 77</Text>", x)
        q = self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": "SJ-V1-8052"}).json()   # lo que hace Consultar al leerlo
        self.assertEqual(q["pareja"], {"numero": 77, "tipo": "TX", "socio": "SJ-V1-8053"})
        self.assertIn("<Text>TX</Text>", x)
        self.assertEqual(len(re.findall("<TextObject>", x)), 2)
        self.assertEqual(self.c.get("/api/antijammer/etiquetas/SJ-V1-9999/xml").status_code, 404)
        self.assertEqual(self.c.get("/api/antijammer/etiquetas/SJ-V1-8054/xml").status_code, 422)

    def test_imprimir_compartida_por_pareja(self):
        with db.get_db() as conn:
            dymo_remoto.init()
            conn.execute("UPDATE dymo_trabajos SET estado='cancelada' WHERE estado IN ('pendiente','enviada')")
            conn.execute("DELETE FROM dymo_agentes")   # agentes que dejaron otros módulos de la suite
        r = self.c.post("/api/antijammer/etiquetas/imprimir", json={"codigos": ["SJ-V1-8052"]})
        self.assertEqual(r.status_code, 503, r.text)
        ag = dymo_remoto.agente_crear("Raspberry AJ")
        dymo_remoto.latido(ag["id"], {"impresora_ok": True})
        self.assertTrue(self.c.get("/api/antijammer/etiquetas/estado").json()["disponible"])
        r = self.c.post("/api/antijammer/etiquetas/imprimir", json={"codigos": ["8052", "SJ-V1-9999"], "copias": 2})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual([t["nombre"] for t in d["trabajos"]], ["SJ-V1-8053", "SJ-V1-8052"])   # el par completo
        self.assertEqual(len(d["errores"]), 1)
        j = dymo_remoto.tomar(ag["id"])
        self.assertEqual((j["tipo"], j["copias"], j["params"]), ("antijammer", 2, {"nombre": "SJ-V1-8053"}))
        cab = {"Authorization": "Bearer " + ag["token"]}
        s = self.c.get(f"/api/dymo/remoto/agente/trabajos/{j['id']}/svg", headers=cab)
        self.assertEqual(s.status_code, 200, s.text)
        self.assertIn(">SKUDO 77<", s.text)
        self.assertEqual(self.c.post("/api/antijammer/etiquetas/imprimir", json={"codigos": []}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
