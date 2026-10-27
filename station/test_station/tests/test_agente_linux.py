"""v1.4.51: agente en la Raspberry. Si se desconecta el USB, el puerto deja de contar como conectado y se reconecta solo."""
import sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent


class SerialFalso:
    def __init__(self):
        self._running = threading.Event(); self.abierto = False; self.port_name = ""; self.conexiones = 0
    @property
    def connected(self): return self.abierto
    def connect(self, port, baud):
        self.abierto = True; self.port_name = port; self._running.set(); self.conexiones += 1
    def disconnect(self):
        self.abierto = False; self._running.clear()


class Motor:
    running = False


def puente(puerto="/dev/serial/by-id/usb-FTDI-if00"):
    b = object.__new__(agent.Bridge)
    b.cfg, b.serial, b.engine, b.command_thread = {}, SerialFalso(), Motor(), None
    b.auto_port, b.latest, b.ready = puerto, {}, ""
    return b


class AgenteLinux(unittest.TestCase):
    def test_conecta_solo_al_puerto_recordado(self):
        b = puente(); b.auto_serial()
        self.assertTrue(b.serial_alive()); self.assertEqual(b.serial.port_name, "/dev/serial/by-id/usb-FTDI-if00")

    def test_usb_desconectado_no_cuenta_y_reconecta(self):
        b = puente(); b.auto_serial()
        b.serial._running.clear()                 # el hilo RX murió (USB fuera) pero pyserial sigue "abierto"
        self.assertFalse(b.serial_alive())
        b._auto_try = 0; b.auto_serial()
        self.assertTrue(b.serial_alive()); self.assertEqual(b.serial.conexiones, 2)

    def test_sin_puerto_recordado_no_conecta(self):
        b = puente(""); b.auto_serial()
        self.assertFalse(b.serial.connected)

    def test_no_toca_el_puerto_durante_una_prueba(self):
        b = puente(); b.auto_serial(); b.serial._running.clear(); b.engine.running = True
        b._auto_try = 0; b.auto_serial()
        self.assertEqual(b.serial.conexiones, 1)


if __name__ == "__main__":
    unittest.main()
