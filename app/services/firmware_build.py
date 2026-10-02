"""Compila el firmware ESP32 de una R1/R2 con arduino-cli para flashearla por USB desde el navegador
(ver `firmware/README.md`). No toca la base de datos ni el firmware STM32 de R1 "Principal" (ese sigue
siendo manual con STM32CubeIDE)."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

FQBN = "esp32:esp32:esp32doit-devkit-v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SKETCHES = {
    "R1": REPO_ROOT / "firmware" / "esp32_r1" / "ESP32_BLE_SERIAL",
    "R2": REPO_ROOT / "firmware" / "esp32_r2" / "TQT2_RESPALDO_V2_1_CORREGIDO",
}
# Solo se parcha el grupo final de 4 dígitos, dejando el resto de la cadena (prefijo/versión) intacto.
NOMBRE_DEFINE_RE = re.compile(r'(#define\s+Nombre_Del_Ble\s+")([A-Za-z0-9_]*?)(\d{4})(")')

COMPILE_TIMEOUT_S = 240


class FirmwareBuildError(Exception):
    """Error de negocio (config/compilación); se traduce a HTTP 400 en el router."""


def _arduino_cli() -> str:
    return os.environ.get("TQT_ARDUINO_CLI", "/opt/arduino-cli/bin/arduino-cli")


def _data_dir() -> str:
    return os.environ.get("TQT_ARDUINO_DATA_DIR", "/opt/arduino-cli/data")


def _env() -> dict:
    data_dir = _data_dir()
    env = os.environ.copy()
    env["ARDUINO_DIRECTORIES_DATA"] = data_dir
    env["ARDUINO_DIRECTORIES_DOWNLOADS"] = str(Path(data_dir) / "downloads")
    env["ARDUINO_DIRECTORIES_USER"] = str(Path(data_dir) / "user")
    return env


def _numero_formateado(numero: Optional[str]) -> str:
    digitos = re.sub(r"\D", "", numero or "")
    if not digitos:
        raise FirmwareBuildError("Falta el número de tarjeta para compilar el firmware de R2.")
    return digitos.zfill(4)[-4:]


def compilar_firmware(tipo: str, numero: Optional[str] = None) -> bytes:
    """Devuelve los bytes del binario combinado (bootloader+particiones+app, offset 0x0) listo para flashear."""
    tipo = (tipo or "").strip().upper()
    src_dir = SKETCHES.get(tipo)
    if not src_dir:
        raise FirmwareBuildError(f"Tipo de placa no soportado para flasheo por USB: '{tipo}' (solo R1 o R2; la R3 no lleva firmware).")
    if not src_dir.is_dir():
        raise FirmwareBuildError(f"No se encontró el firmware fuente de {tipo} en el servidor ({src_dir}).")

    numero_fmt = _numero_formateado(numero) if tipo == "R2" else None

    with tempfile.TemporaryDirectory(prefix="tqt_fw_") as tmp:
        tmp_path = Path(tmp)
        sketch_name = src_dir.name
        dest_dir = tmp_path / sketch_name
        shutil.copytree(src_dir, dest_dir)
        ino_path = dest_dir / f"{sketch_name}.ino"

        if tipo == "R2":
            texto = ino_path.read_text(encoding="utf-8")
            nuevo_texto, n = NOMBRE_DEFINE_RE.subn(rf"\g<1>\g<2>{numero_fmt}\g<4>", texto)
            if n != 1:
                raise FirmwareBuildError(
                    "No se encontró el #define Nombre_Del_Ble esperado en el firmware de R2; "
                    "no se compiló para no arriesgar un binario con el número equivocado."
                )
            ino_path.write_text(nuevo_texto, encoding="utf-8")

        out_dir = tmp_path / "build"
        out_dir.mkdir()
        cli = _arduino_cli()
        cmd = [cli, "compile", "--fqbn", FQBN, str(dest_dir), "--export-binaries", "--output-dir", str(out_dir)]
        try:
            proc = subprocess.run(cmd, env=_env(), capture_output=True, text=True, timeout=COMPILE_TIMEOUT_S)
        except FileNotFoundError:
            raise FirmwareBuildError(f"No se encontró arduino-cli en '{cli}' (variable TQT_ARDUINO_CLI).")
        except subprocess.TimeoutExpired:
            raise FirmwareBuildError(f"La compilación de {tipo} tardó demasiado (más de {COMPILE_TIMEOUT_S}s).")

        if proc.returncode != 0:
            detalle = (proc.stderr or proc.stdout or "").strip()[-4000:]
            raise FirmwareBuildError(f"arduino-cli falló al compilar {tipo}: {detalle or 'sin detalle'}")

        binarios = list(out_dir.glob("*.merged.bin"))
        if not binarios:
            raise FirmwareBuildError("La compilación terminó pero no generó el binario combinado (.merged.bin).")
        return binarios[0].read_bytes()
