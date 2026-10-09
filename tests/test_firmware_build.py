"""Compilación del firmware ESP32 de R1/R2 para flasheo por USB (`POST /api/firmware/compilar`).

Compila de verdad con arduino-cli (no se mockea): es lento (~15-25s por compilación) pero es la única forma
de detectar si el `#define Nombre_Del_Ble` cambió de forma en `firmware/esp32_r2/...` y rompió el parcheo
automático. Se salta sola si no encuentra un arduino-cli utilizable (máquinas sin el toolchain instalado).
"""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import unittest
from pathlib import Path
from unittest import mock

from app.services import firmware_build

# En esta máquina de desarrollo, arduino-cli viene incluido con Arduino IDE y el core esp32:esp32 ya está
# instalado en el data dir por defecto de Arduino15. Dentro del contenedor Docker, en cambio, las variables
# TQT_ARDUINO_CLI / TQT_ARDUINO_DATA_DIR ya apuntan a lo horneado en la imagen (ver Dockerfile) y no hace
# falta este override.
_CLI_HOST = Path(r"C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe")
_DATA_HOST = Path.home() / "AppData" / "Local" / "Arduino15"


def _env_compilable() -> dict:
    if os.environ.get("TQT_ARDUINO_CLI"):
        return {}  # ya configurado por el entorno (p.ej. dentro de Docker)
    if _CLI_HOST.is_file() and _DATA_HOST.is_dir():
        return {"TQT_ARDUINO_CLI": str(_CLI_HOST), "TQT_ARDUINO_DATA_DIR": str(_DATA_HOST)}
    return None


_ENV = _env_compilable()


class TestFirmwareBuildValidaciones(unittest.TestCase):
    """No requieren compilar de verdad."""

    def test_tipo_no_soportado(self):
        with self.assertRaises(firmware_build.FirmwareBuildError):
            firmware_build.compilar_firmware("R3")

    def test_r2_sin_numero(self):
        with self.assertRaises(firmware_build.FirmwareBuildError):
            firmware_build.compilar_firmware("R2", None)

    def test_r2_numero_no_numerico(self):
        with self.assertRaises(firmware_build.FirmwareBuildError):
            firmware_build.compilar_firmware("R2", "abcd")


class TestPersonalizadorR2(unittest.TestCase):
    """v1.3.62: especificación R2 (§7 y matriz 01–04): solo cambia Nombre_Del_Ble, nombre desde inventario."""
    def setUp(self):
        self.src = (firmware_build.SKETCHES["R2"] / "TQT_R2_V3_1.ino").read_bytes().decode("utf-8")

    def test_01_nombre_y_resto_intacto(self):
        nuevo, d = firmware_build.personalizar_r2(self.src, "0025")
        self.assertEqual(d["nombre_ble"], "TQT_R2_V30_0025")
        self.assertIn('#define Nombre_Del_Ble      "TQT_R2_V30_0025"', nuevo)
        self.assertEqual(nuevo.replace("TQT_R2_V30_0025", d["anterior"], 1), self.src)
        self.assertNotEqual(d["sha256_fuente"], d["sha256_copia"])

    def test_02_ceros_iniciales(self):
        self.assertEqual(firmware_build.nombre_ble_r2("0001"), "TQT_R2_V30_0001")

    def test_03_numeros_invalidos(self):
        for n in ("", "1", "abcd", " 12", "-001", "12345", "0000", None):
            with self.assertRaises(firmware_build.FirmwareBuildError, msg=repr(n)):
                firmware_build.nombre_ble_r2(n)

    def test_04_fuente_sin_define_o_duplicada(self):
        for texto in (self.src.replace("#define Nombre_Del_Ble", "// #define Otro"),
                      self.src + '\n#define Nombre_Del_Ble "TQT_R2_V30_9999"\n',
                      self.src.replace('Nombre_Del_Ble      "TQT_R2_V30_0024"', "Nombre_Del_Ble      NOMBRE_DINAMICO")):
            with self.assertRaises(firmware_build.FirmwareBuildError):
                firmware_build.personalizar_r2(texto, "0025")

    def test_metadatos(self):
        self.assertEqual(firmware_build.metadatos("R2")["version"], "3.1.2")


@unittest.skipUnless(_ENV is not None, "arduino-cli no disponible en este entorno (ver _env_compilable)")
class TestFirmwareBuildCompilaDeVerdad(unittest.TestCase):
    def _compilar(self, tipo, numero=None):
        with mock.patch.dict(os.environ, _ENV or {}):
            return firmware_build.compilar_firmware(tipo, numero)

    def test_r2_compila_y_parcha_el_numero(self):
        binario = self._compilar("R2", "9042")
        self.assertGreater(len(binario), 1_000_000)   # imagen combinada de 4MB
        # offset 0x0-0x0FFF es relleno (0xFF) antes del bootloader; su magic byte va en 0x1000.
        self.assertEqual(binario[0x1000], 0xE9)
        fuente = (firmware_build.SKETCHES["R2"] / "TQT_R2_V3_1.ino").read_text(encoding="utf-8")
        self.assertNotIn('"TQT_R2_V30_9042"', fuente)  # el .ino original en el repo no se tocó: se parcha una copia
        self.assertIn(b"TQT_R2_V30_9042", binario)      # v1.3.62: el nombre BLE de la unidad quedó en el binario

    def test_r1_compila_sin_numero(self):
        binario = self._compilar("R1")
        self.assertGreater(len(binario), 1_000_000)
        self.assertEqual(binario[0x1000], 0xE9)


if __name__ == "__main__":
    unittest.main()
