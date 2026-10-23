import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.35: inventario de materiales por módulo. Cada placa programada (desde la activación) descuenta la lista de
materiales de su tarjeta; desprogramar o eliminar la devuelve; AntiJammer necesita saber si la placa es RX o TX."""
import unittest
from datetime import date

from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestMateriales(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text

    def limpiar(self, slug):
        """La BD de pruebas es compartida: otras pruebas dejan placas programadas hoy que también descontarían."""
        self.c.get(f"/api/{slug}/materiales")   # crea las tablas si faltan
        modulo = {"sigfox": "skudo-sigfox", "antijammer": "skudo-antijammer"}[slug]
        with db.transaction() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (f"{slug}_pcb",)).fetchone():   # puede no existir aún
                c.execute(f"DELETE FROM {slug}_pcb")
            for tabla in ("costeo_componentes", "costeo_consumos", "costeo_movimientos", "costeo_pcb_tarjeta", "costeo_minimos", "costeo_meta"):
                c.execute(f"DELETE FROM {tabla} WHERE modulo=?", (modulo,))

    def material(self, slug, desc, cant, tarjeta=None):
        body = {"descripcion": desc, "cantidad": cant, "costo_unitario": 1, "unidad": "pza"}
        if tarjeta:
            body["tarjeta"] = tarjeta
        r = self.c.post(f"/api/{slug}/costos", json=body)
        self.assertIn(r.status_code, (201, 422), r.text)

    def placa(self, slug, serie, programar=True):
        r = self.c.post(f"/api/{slug}/pcb/manual", json={"version": "1", "serie": serie, "lote": ""})
        self.assertEqual(r.status_code, 201, r.text)
        pid = r.json()["id"] if "id" in r.json() else r.json()["pcb"]["id"]
        if programar:
            self.assertEqual(self.c.put(f"/api/{slug}/pcb/{pid}/firmware", json={"firmware": "FW1"}).status_code, 200)
        return pid

    def disp(self, d, desc):
        return next(m for m in d["materiales"] if m["descripcion"] == desc)["disponible"]

    def test_sigfox_descuenta_al_programar_y_devuelve(self):
        b = "/api/sigfox/materiales"
        self.limpiar("sigfox")
        self.material("sigfox", "Arduino Nano", 1)
        self.material("sigfox", "Capacitor 100 uF", 6)
        antes = self.placa("sigfox", "901")   # programada antes de activar: no descuenta
        d = self.c.get(b).json()
        self.assertFalse(d["activo"])
        self.assertEqual(self.disp(d, "Arduino Nano"), 0)
        self.assertEqual(self.c.post(f"{b}/movimientos", json={"descripcion": "Arduino Nano", "tipo": "entrada", "cantidad": 10}).status_code, 201)
        self.c.post(f"{b}/movimientos", json={"descripcion": "Capacitor 100 uF", "tipo": "entrada", "cantidad": 30})
        d = self.c.post(f"{b}/activar", json={"desde": date.today().isoformat()}).json()
        # la placa de hoy cuenta (activación con fecha de hoy): 1 descontada
        self.assertEqual(d["realizadas"]["Sigfox"], 1)
        self.assertEqual(self.disp(d, "Arduino Nano"), 9)
        pid = self.placa("sigfox", "902")
        d = self.c.get(b).json()
        self.assertEqual(self.disp(d, "Capacitor 100 uF"), 30 - 12)
        self.assertEqual(d["posibles"]["Sigfox"], 3)   # 18 capacitores / 6 por tarjeta
        # desprogramar devuelve; volver a programar reactiva sin duplicar
        self.c.put(f"/api/sigfox/pcb/{pid}/firmware", json={"firmware": None})
        self.assertEqual(self.disp(self.c.get(b).json(), "Arduino Nano"), 9)
        self.c.put(f"/api/sigfox/pcb/{pid}/firmware", json={"firmware": "FW2"})
        self.assertEqual(self.disp(self.c.get(b).json(), "Arduino Nano"), 8)
        # eliminar la placa devuelve su material
        self.c.delete(f"/api/sigfox/pcb/{antes}")
        d = self.c.get(b).json()
        self.assertEqual(self.disp(d, "Arduino Nano"), 9)
        # mínimo y alerta
        d = self.c.patch(f"{b}/minimo", json={"descripcion": "Arduino Nano", "minimo": 9}).json()
        self.assertGreaterEqual(d["bajo_minimo"], 1)
        # validaciones
        self.assertEqual(self.c.post(f"{b}/movimientos", json={"descripcion": "No existe", "tipo": "entrada", "cantidad": 1}).status_code, 422)
        self.assertEqual(self.c.post(f"{b}/movimientos", json={"descripcion": "Arduino Nano", "tipo": "entrada", "cantidad": -1}).status_code, 422)
        self.assertEqual(self.c.post(f"{b}/activar", json={"desde": "ayer"}).status_code, 422)

    def test_antijammer_espera_rx_o_tx(self):
        b = "/api/antijammer/materiales"
        self.limpiar("antijammer")
        self.material("antijammer", "PCB RX", 1, "RX")
        self.material("antijammer", "PCB TX", 1, "TX")
        self.material("antijammer", "Relevador", 1, "RX")
        self.c.post(f"{b}/activar", json={})
        for desc in ("PCB RX", "PCB TX", "Relevador"):
            self.c.post(f"{b}/movimientos", json={"descripcion": desc, "tipo": "entrada", "cantidad": 5})
        pid = self.placa("antijammer", "903")
        d = self.c.get(b).json()
        self.assertEqual([p["id"] for p in d["pendientes"]], [pid])
        self.assertEqual(self.disp(d, "PCB RX"), 5)
        d = self.c.post(f"{b}/asignar", json={"pcb_ids": [pid], "tarjeta": "RX"}).json()
        self.assertEqual(d["pendientes"], [])
        self.assertEqual((self.disp(d, "PCB RX"), self.disp(d, "Relevador"), self.disp(d, "PCB TX")), (4, 4, 5))
        d = self.c.post(f"{b}/asignar", json={"pcb_ids": [pid], "tarjeta": "TX"}).json()   # corrección RX → TX
        self.assertEqual((self.disp(d, "PCB RX"), self.disp(d, "Relevador"), self.disp(d, "PCB TX")), (5, 5, 4))
        self.assertEqual(self.c.post(f"{b}/asignar", json={"pcb_ids": [pid], "tarjeta": "Sigfox"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
