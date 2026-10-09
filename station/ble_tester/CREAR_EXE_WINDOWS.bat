@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ========================================================
echo   TQT BLE Tester - GENERAR EXE PARA WINDOWS
echo ========================================================
echo.

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% NEQ 0 goto NO_PYTHON
    set "PYTHON=python"
)

echo [1/4] Preparando entorno virtual...
%PYTHON% -m venv .venv
if errorlevel 1 goto FAILED
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto FAILED

echo [2/4] Instalando bibliotecas...
python -m pip install --upgrade pip
if errorlevel 1 goto FAILED
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto FAILED

echo [3/4] Creando aplicacion Windows...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name TQT_BLE_Tester ^
  --hidden-import bleak.backends.winrt.scanner ^
  --hidden-import bleak.backends.winrt.client ^
  TQT_BLE_Tester.py
if errorlevel 1 goto FAILED

echo [4/4] Proceso terminado.
echo.
echo Ejecutable creado en:
echo %CD%\dist\TQT_BLE_Tester.exe
echo.
explorer "%CD%\dist"
pause
exit /b 0

:NO_PYTHON
echo.
echo ERROR: No se encontro Python 3.
echo Instala Python desde https://www.python.org/downloads/windows/
echo Durante la instalacion activa 'Add python.exe to PATH'.
goto FAILED

:FAILED
echo.
echo No se pudo generar el EXE. Revisa los mensajes de arriba.
pause
exit /b 1
