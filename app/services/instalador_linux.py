"""v1.4.64: instalador .sh autoextraíble del agente de la Raspberry (Pruebas automáticas), sin copiar ZIP ni teclear pasos.

Se usa con `curl -fsSL '<servidor>/api/stm32/agent/tests/instalar/<codigo>.sh' | sh` (código de un solo uso) o
descargando el .sh y corriendo `sh instalar_tqt_pruebas.sh`. Funciona igual por tubería que como archivo: el script
de instalación y el ZIP (base64) van en dos here-documents, así la parte de arriba los copia a un temporal y relanza
la instalación en segundo plano (setsid nohup) para que cerrar SSH no la corte. El avance va a la página con
POST /api/stm32/agent/tests/install-progress y el Bearer del config.json del ZIP; el token nunca se imprime ni va
en la línea de comandos (curl lo lee de un archivo de cabeceras 0600).
"""
import base64

MARCA_SCRIPT = "TQT_SCRIPT_FIN"
MARCA_ZIP = "TQT_ZIP_BASE64"
ARCHIVO = "instalar_tqt_pruebas.sh"
MENSAJE = ("Instalando el agente TQT en segundo plano. Sigue el avance en la página (paso 1). "
           "Registro: ~/tqt-pruebas-instalar.log")

_CABECERA = r"""#!/bin/sh
# Instalador del agente TQT de Pruebas automáticas (Raspberry, estación __ID__).
# Uso: sh instalar_tqt_pruebas.sh   (o el comando curl de la página). Se instala en ~/tqt-pruebas.
umask 077
TQT_TMP=$(mktemp -d "${TMPDIR:-/tmp}/tqt-instalar.XXXXXX") || { echo "No se pudo crear un directorio temporal."; exit 1; }
cat > "$TQT_TMP/instalar.sh" <<'TQT_SCRIPT_FIN'
"""

_PIE = r"""
if command -v setsid >/dev/null 2>&1; then
  setsid nohup sh "$TQT_TMP/instalar.sh" --fondo "$TQT_TMP" >"$HOME/tqt-pruebas-instalar.log" 2>&1 </dev/null &
else
  nohup sh "$TQT_TMP/instalar.sh" --fondo "$TQT_TMP" >"$HOME/tqt-pruebas-instalar.log" 2>&1 </dev/null &
fi
echo "__MENSAJE__"
exit 0
"""

# Instalación real (en segundo plano). POSIX sh: sin bashismos (dash en Raspberry Pi OS).
_FONDO = r"""#!/bin/sh
# Instalación en segundo plano del agente TQT (lo lanza instalar_tqt_pruebas.sh). Registro: ~/tqt-pruebas-instalar.log
umask 077
[ "${1:-}" = "--fondo" ] || { echo "Uso interno: lo lanza instalar_tqt_pruebas.sh"; exit 2; }
WORK=$2
DEST="${TQT_DEST:-$HOME/tqt-pruebas}"
AVISO=""
echo "$(date '+%F %T') Instalando el agente TQT en $DEST"

avance() {
  # Reporta la etapa a la página; si falla (sin red) se sigue igual. El token va en un archivo 0600, nunca en argv.
  [ -s "$WORK/cabecera" ] && [ -n "${SERVER:-}" ] || return 0
  if command -v python3 >/dev/null 2>&1; then
    CUERPO=$(TQT_E="$1" TQT_M="$2" python3 -c 'import json,os;print(json.dumps({"etapa":os.environ["TQT_E"],"mensaje":os.environ["TQT_M"][:490]}))')
  else
    CUERPO=$(printf '{"etapa":"%s","mensaje":"%s"}' "$1" "$(printf '%s' "$2" | tr '\n\r\t' '   ' | sed 's/\\/\\\\/g; s/"/\\"/g' | cut -c1-400)")
  fi
  URL="$SERVER/api/stm32/agent/tests/install-progress"
  if command -v curl >/dev/null 2>&1; then
    printf '%s' "$CUERPO" | curl -fsS -m 10 -o /dev/null -X POST -H @"$WORK/cabecera" \
      -H 'Content-Type: application/json; charset=utf-8' --data-binary @- "$URL" 2>/dev/null || true
  elif command -v python3 >/dev/null 2>&1; then
    TQT_URL="$URL" TQT_CUERPO="$CUERPO" TQT_CAB="$WORK/cabecera" python3 -c '
import os, urllib.request
cab = open(os.environ["TQT_CAB"]).read().strip().split(": ", 1)
rq = urllib.request.Request(os.environ["TQT_URL"], data=os.environ["TQT_CUERPO"].encode(), method="POST",
                            headers={cab[0]: cab[1], "Content-Type": "application/json; charset=utf-8"})
try:
    urllib.request.urlopen(rq, timeout=10).read()
except Exception:
    pass' || true
  fi
  return 0
}

fallar() {
  echo "$(date '+%F %T') ERROR: $1"
  avance error "$1"
  rm -rf "$WORK"
  exit 1
}

paso() { echo "$(date '+%F %T') $1"; }

# 1) Extraer en un directorio temporal y validar antes de tocar la instalación actual
paso "Extrayendo el agente"
mkdir -p "$WORK/pkg" || fallar "No se pudo crear el directorio temporal."
if command -v base64 >/dev/null 2>&1; then
  base64 -d "$WORK/agente.b64" > "$WORK/agente.zip" 2>/dev/null || rm -f "$WORK/agente.zip"
fi
if [ ! -s "$WORK/agente.zip" ] && command -v python3 >/dev/null 2>&1; then
  python3 -c 'import base64,sys;open(sys.argv[2],"wb").write(base64.b64decode(open(sys.argv[1]).read()))' \
    "$WORK/agente.b64" "$WORK/agente.zip" || rm -f "$WORK/agente.zip"
fi
[ -s "$WORK/agente.zip" ] || fallar "El instalador está incompleto; genera el comando de nuevo en la página."
if command -v python3 >/dev/null 2>&1; then
  python3 -c '
import os, sys, zipfile
dest = os.path.realpath(sys.argv[2])
with zipfile.ZipFile(sys.argv[1]) as z:
    for i in z.infolist():
        out = os.path.realpath(os.path.join(dest, i.filename))
        if not out.startswith(dest + os.sep):
            sys.exit("ruta inválida en el paquete: " + i.filename)
    z.extractall(dest)' "$WORK/agente.zip" "$WORK/pkg" || fallar "No se pudo extraer el paquete del agente."
elif command -v unzip >/dev/null 2>&1; then
  unzip -q -o "$WORK/agente.zip" -d "$WORK/pkg" || fallar "No se pudo extraer el paquete del agente."
else
  fallar "Falta python3. En la Raspberry corre: sudo apt-get install -y python3 python3-venv bluez y genera el comando de nuevo."
fi
[ -f "$WORK/pkg/agent.py" ] && [ -f "$WORK/pkg/config.json" ] || fallar "El paquete del agente está incompleto."

SERVER=$(sed -n 's/^ *"server": *"\([^"]*\)".*/\1/p' "$WORK/pkg/config.json" | head -n 1)
TOKEN=$(sed -n 's/^ *"token": *"\([^"]*\)".*/\1/p' "$WORK/pkg/config.json" | head -n 1)
SERVER=${SERVER%/}
[ -n "$TOKEN" ] && printf 'Authorization: Bearer %s\n' "$TOKEN" > "$WORK/cabecera"
TOKEN=""
avance extrayendo "Archivos del agente recibidos"

# 2) Detener el agente anterior de esta carpeta (su token ya rotó; sin matar este instalador)
if pgrep -f "[a]gent.py --config $DEST/" >/dev/null 2>&1; then
  paso "Deteniendo el agente anterior"
  pkill -f "[a]gent.py --config $DEST/" 2>/dev/null
  i=0
  while [ $i -lt 10 ] && pgrep -f "[a]gent.py --config $DEST/" >/dev/null 2>&1; do sleep 1; i=$((i + 1)); done
  pkill -9 -f "[a]gent.py --config $DEST/" 2>/dev/null
fi

# 3) Copiar sobre ~/tqt-pruebas conservando .venv, puerto_serie.txt y agent.log (no vienen en el paquete)
mkdir -p "$DEST" || fallar "No se pudo crear $DEST."
chmod 700 "$DEST"
rm -rf "$DEST/tqtstation"
cp -R "$WORK/pkg/." "$DEST/" || fallar "No se pudieron copiar los archivos a $DEST."
chmod 600 "$DEST/config.json"
paso "Archivos copiados en $DEST"

# 4) Python 3 con venv (python3-venv) y BlueZ; apt solo con sudo sin contraseña
avance python "Preparando Python"
command -v python3 >/dev/null 2>&1 || fallar "Falta python3. En la Raspberry corre: sudo apt-get install -y python3 python3-venv bluez y genera el comando de nuevo."
if [ -x "$DEST/.venv/bin/python" ] && ! "$DEST/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
  rm -rf "$DEST/.venv"   # venv a medias (p. ej. creada sin python3-venv): se rehace
fi
if [ ! -x "$DEST/.venv/bin/python" ]; then
  if ! python3 -c 'import ensurepip, venv' >/dev/null 2>&1 || ! command -v bluetoothctl >/dev/null 2>&1; then
    paso "Instalando python3-venv y bluez con sudo -n"
    sudo -n apt-get install -y python3-venv bluez >/dev/null 2>&1 \
      || { sudo -n apt-get update >/dev/null 2>&1 && sudo -n apt-get install -y python3-venv bluez >/dev/null 2>&1; }
  fi
  python3 -c 'import ensurepip, venv' >/dev/null 2>&1 \
    || fallar "Falta python3-venv. En la Raspberry corre: sudo apt-get install -y python3-venv bluez y después genera el comando de nuevo en la página."
  paso "Creando el entorno de Python"
  python3 -m venv "$DEST/.venv" || { rm -rf "$DEST/.venv"; fallar "No se pudo crear el entorno de Python en $DEST/.venv."; }
fi
command -v bluetoothctl >/dev/null 2>&1 || AVISO="$AVISO Falta BlueZ: sudo apt-get install -y bluez."
if ! id -nG 2>/dev/null | tr ' ' '\n' | grep -qx dialout; then
  AVISO="$AVISO Tu usuario no está en el grupo dialout (puerto serie): corre sudo usermod -aG dialout \$USER y reinicia la Raspberry."
  avance python "Aviso: tu usuario no está en el grupo dialout; corre sudo usermod -aG dialout \$USER"
fi

# 5) Dependencias
avance dependencias "Instalando bleak y pyserial"
paso "Instalando dependencias (bleak, pyserial)"
"$DEST/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$DEST/requirements.txt" \
  || fallar "No se pudieron instalar bleak y pyserial. Revisa la conexión a internet de la Raspberry y genera el comando de nuevo."

# 6) Arranque al encender (idempotente)
if command -v crontab >/dev/null 2>&1; then
  { crontab -l 2>/dev/null | grep -v 'tqt-pruebas/iniciar.sh'; echo '@reboot sh $HOME/tqt-pruebas/iniciar.sh'; } | crontab - \
    || AVISO="$AVISO No se pudo registrar el arranque automático (crontab)."
else
  AVISO="$AVISO Sin crontab: el agente no arrancará solo al encender."
fi

# 7) Arrancar y comprobar que sigue vivo
avance arrancando "Arrancando el agente"
paso "Arrancando el agente"
cd "$DEST" || fallar "No se pudo entrar a $DEST."
if command -v setsid >/dev/null 2>&1; then
  setsid nohup "$DEST/.venv/bin/python" -u agent.py --config "$DEST/config.json" --background >/dev/null 2>&1 </dev/null &
else
  nohup "$DEST/.venv/bin/python" -u agent.py --config "$DEST/config.json" --background >/dev/null 2>&1 </dev/null &
fi
sleep 6
if ! pgrep -f "[a]gent.py --config $DEST/" >/dev/null 2>&1; then
  ULTIMAS=$(tail -n 8 "$DEST/agent.log" 2>/dev/null | tr '\n' ' ')
  fallar "El agente no quedó en marcha. Últimas líneas de agent.log: ${ULTIMAS:-(vacío)}"
fi
paso "Agente instalado y en marcha.$AVISO"
avance listo "Agente instalado y en marcha.$AVISO"
rm -rf "$WORK"
exit 0
"""


def construir(zip_bytes, station_id):
    """Devuelve (nombre_archivo, bytes) del .sh con LF. El token solo viaja dentro del ZIP (config.json)."""
    sid = "".join(ch for ch in str(station_id) if ch.isalnum())
    b64 = base64.b64encode(zip_bytes).decode("ascii")
    lineas = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
    texto = (_CABECERA.replace("__ID__", sid) + _FONDO.strip("\n") + "\n" + MARCA_SCRIPT + "\n"
             + "cat > \"$TQT_TMP/agente.b64\" <<'" + MARCA_ZIP + "'\n" + lineas + "\n" + MARCA_ZIP + "\n"
             + _PIE.lstrip("\n").replace("__MENSAJE__", MENSAJE))
    return ARCHIVO, texto.replace("\r\n", "\n").encode("utf-8")


def _entre(texto, inicio, fin):
    a = texto.index(inicio) + len(inicio)
    return texto[a:texto.index("\n" + fin + "\n", a)]


def extraer_zip(sh_bytes):
    """Para pruebas: recupera el ZIP embebido (here-document tras el marcador)."""
    texto = sh_bytes.decode("utf-8")
    return base64.b64decode("".join(_entre(texto, "<<'" + MARCA_ZIP + "'\n", MARCA_ZIP).split()))


def script_fondo(sh_bytes):
    """Para pruebas: el script de instalación en segundo plano tal como queda en $TQT_TMP/instalar.sh."""
    return _entre(sh_bytes.decode("utf-8"), "<<'" + MARCA_SCRIPT + "'\n", MARCA_SCRIPT) + "\n"
