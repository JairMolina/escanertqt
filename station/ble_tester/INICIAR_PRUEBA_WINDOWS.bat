@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
    echo Falta el entorno .venv. Ejecuta CREAR_EXE_WINDOWS.bat primero.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" TQT_BLE_Tester.py
if errorlevel 1 pause
