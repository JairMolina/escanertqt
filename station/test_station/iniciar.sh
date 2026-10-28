#!/bin/sh
# v1.4.51: arranque en Linux (Raspberry del banco de resistencia). Crea la venv, instala pyserial/bleak y deja el agente
# en segundo plano; diagnóstico en agent.log. Requisitos: python3-venv, BlueZ y el usuario en el grupo dialout.
# v1.4.64: lo usa el @reboot del crontab; sin red al encender, pip falla pero el agente arranca si ya tiene sus módulos.
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv || { echo "Instala python3-venv (sudo apt install python3-venv)."; exit 1; }
.venv/bin/python -m pip install -q -r requirements.txt || .venv/bin/python -c "import serial, bleak" 2>/dev/null \
  || { echo "No se pudieron instalar pyserial y bleak."; exit 1; }
if command -v setsid >/dev/null 2>&1; then
  setsid nohup .venv/bin/python -u agent.py --config "$PWD/config.json" --background >/dev/null 2>&1 </dev/null &
else
  nohup .venv/bin/python -u agent.py --config "$PWD/config.json" --background >/dev/null 2>&1 </dev/null &
fi
echo "Agente iniciado en segundo plano (PID $!). Usa la web; diagnóstico en agent.log."
