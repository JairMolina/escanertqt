@echo off
setlocal
cd /d "%~dp0"
title Escaner TQT

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv || goto :error
)
call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements.txt || goto :error

rem Abre el puerto en el firewall (solo funciona si se ejecuta como administrador; si falla, se ignora)
netsh advfirewall firewall show rule name="Escaner TQT 8443" >nul 2>&1 || ^
netsh advfirewall firewall add rule name="Escaner TQT 8443" dir=in action=allow protocol=TCP localport=8443 >nul 2>&1

python run_server.py
goto :eof

:error
echo.
echo Ocurrio un error durante la preparacion.
pause
