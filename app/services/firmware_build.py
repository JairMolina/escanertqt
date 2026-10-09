"""Compila el firmware ESP32 de una R1/R2 con arduino-cli para flashearla por USB desde el navegador
(ver `firmware/README.md`). No toca la base de datos ni el firmware STM32 de R1 "Principal" (ese sigue
siendo manual con STM32CubeIDE)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

FQBN = "esp32:esp32:esp32doit-devkit-v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SKETCHES = {
    "R1": REPO_ROOT / "firmware" / "esp32_r1" / "ESP32_BLE_SERIAL",
    # v1.3.62: R2 V3.1 (TQT_R2_V3_1_30_09_2026.ino). La versión anterior se conserva en firmware/esp32_r2/TQT2_RESPALDO_V2_1_CORREGIDO.
    "R2": REPO_ROOT / "firmware" / "esp32_r2" / "TQT_R2_V3_1",
}
# Solo se parcha el grupo final de 4 dígitos, dejando el resto de la cadena (prefijo/versión) intacto.
NOMBRE_DEFINE_RE = re.compile(r'(#define\s+Nombre_Del_Ble\s+")([A-Za-z0-9_]*?)(\d{4})(")')

COMPILE_TIMEOUT_S = 240

# v1.3.62 (especificación «Programador Web TQT R2 Arduino CLI», §5 y §7): solo cambia la directiva activa
# `#define Nombre_Del_Ble "..."`; el nombre sale del inventario (TQT_R2_V30_ + 4 dígitos, HW fijo V30).
R2_PREFIJO = "TQT_R2_V30_"
_R2_DEFINE_RE = re.compile(r'^([ \t]*#define[ \t]+Nombre_Del_Ble[ \t]+")([^"\r\n]*)(".*)$', re.MULTILINE)
_R2_MENCION_RE = re.compile(r'^[ \t]*#define[ \t]+Nombre_Del_Ble\b', re.MULTILINE)


def nombre_ble_r2(numero: Optional[str]) -> str:
    n = str(numero or "").strip()
    if not re.fullmatch(r"\d{4}", n) or n == "0000":
        raise FirmwareBuildError(f"Número de R2 inválido: '{n}'. Deben ser exactamente 4 dígitos (0001–9999).")
    nombre = R2_PREFIJO + n
    if len(nombre) >= 24:
        raise FirmwareBuildError("El nombre BLE excede 23 caracteres.")
    return nombre


def personalizar_r2(texto: str, numero: Optional[str]) -> Tuple[str, Dict[str, str]]:
    """Copia de trabajo con el nombre BLE de la unidad; rechaza fuentes sin la directiva, con dos o con valor dinámico,
    y aborta si cambia cualquier otra línea."""
    nombre = nombre_ble_r2(numero)
    defs = _R2_DEFINE_RE.findall(texto)
    if len(_R2_MENCION_RE.findall(texto)) != 1 or len(defs) != 1:
        raise FirmwareBuildError("El firmware de R2 debe tener exactamente un `#define Nombre_Del_Ble \"...\"` literal; no se compiló.")
    nuevo = _R2_DEFINE_RE.sub(lambda m: m.group(1) + nombre + m.group(3), texto, count=1)
    a, b = texto.splitlines(keepends=True), nuevo.splitlines(keepends=True)
    distintas = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(a) != len(b) or len(distintas) != 1 or "Nombre_Del_Ble" not in b[distintas[0]]:
        raise FirmwareBuildError("La personalización modificó algo más que Nombre_Del_Ble; se abortó.")
    return nuevo, {"nombre_ble": nombre, "anterior": defs[0][1],
                   "sha256_fuente": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                   "sha256_copia": hashlib.sha256(nuevo.encode("utf-8")).hexdigest()}


def metadatos(tipo: str) -> Dict[str, str]:
    src = SKETCHES.get((tipo or "").upper())
    meta = src.parent / f"{src.name}.json" if src else None
    return json.loads(meta.read_text(encoding="utf-8")) if meta and meta.is_file() else {}


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
    return compilar_firmware_meta(tipo, numero)[0]


def compilar_firmware_meta(tipo: str, numero: Optional[str] = None) -> Tuple[bytes, Dict[str, str]]:
    """Como `compilar_firmware`, más los datos de trazabilidad (nombre BLE esperado, hashes y versión)."""
    tipo = (tipo or "").strip().upper()
    src_dir = SKETCHES.get(tipo)
    if not src_dir:
        raise FirmwareBuildError(f"Tipo de placa no soportado para flasheo por USB: '{tipo}' (solo R1 o R2; el firmware de la R3 no se compila aquí).")
    if not src_dir.is_dir():
        raise FirmwareBuildError(f"No se encontró el firmware fuente de {tipo} en el servidor ({src_dir}).")

    info: Dict[str, str] = {"firmware": metadatos(tipo).get("version", "")}

    with tempfile.TemporaryDirectory(prefix="tqt_fw_") as tmp:
        tmp_path = Path(tmp)
        sketch_name = src_dir.name
        dest_dir = tmp_path / sketch_name
        shutil.copytree(src_dir, dest_dir)
        ino_path = dest_dir / f"{sketch_name}.ino"

        if tipo == "R2":
            texto = ino_path.read_bytes().decode("utf-8")
            nuevo_texto, datos = personalizar_r2(texto, numero)
            info.update(datos)
            ino_path.write_bytes(nuevo_texto.encode("utf-8"))   # bytes: conserva los finales de línea originales

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
        return binarios[0].read_bytes(), info
