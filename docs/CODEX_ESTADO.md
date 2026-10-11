# Estado TQT Web

Verificado el 2026-10-11: versión 1.3.63; GitHub main y producción tienen commit de aplicación 803a3a1feb8410f9c42e7e21f6d206af78ce4bb7.

FastAPI, SQLite, WebSockets y frontend HTML/JS. Entradas: app/config.py, app/routers/, app/services/, app/static/. Docker de aplicación: Dockerfile, docker-compose.yml y deploy/.
Las pruebas y comandos están en README.md; consulta docs/PROGRAMACION_STM32.md para R1 y docs/AUTENTICACION.md para accesos.

La configuración y recuperación del servidor se mantienen en el proyecto separado tqt-orangepi. Este documento contiene solo contexto de desarrollo de la aplicación.

Pendiente confirmado por la documentación: prueba física de programación STM32; no considerar generación del HEX como prueba de flasheo real.
En esta separación no se modificó la lógica de la web ni se desplegó código.
