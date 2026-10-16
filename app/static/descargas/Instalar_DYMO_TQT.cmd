@echo off
chcp 65001 >nul
title Instalar impresion DYMO - TQT
echo.
echo  Instalando DYMO Connect (driver de la LabelWriter y servicio de impresion)...
echo  Si Windows pregunta si permites cambios, pulsa Si.
echo.
winget --version >nul 2>&1
if errorlevel 1 goto manual
winget install -e --id DYMO.DYMOConnect --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manual
echo.
echo  Listo. Se abre la prueba del servicio: si Chrome dice "La conexion no es privada",
echo  pulsa Configuracion avanzada y Continuar. Luego vuelve a la pagina de etiquetas y pulsa Actualizar.
timeout /t 8 >nul
start "" "https://127.0.0.1:41951/DYMO/DLS/Printing/Check"
goto fin
:manual
echo  No se pudo instalar automaticamente. Se abre la pagina oficial de DYMO: descarga e instala DYMO Connect for Desktop.
start "" "https://www.dymo.com/support?cfid=user-guide"
:fin
echo.
pause
