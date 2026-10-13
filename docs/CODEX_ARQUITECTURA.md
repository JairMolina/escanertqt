# Arquitectura de TQT-Web

Hechos verificados: FastAPI app/main.py; SQLite app/database/db.py e inventario.py; autenticación y roles app/services/usuarios.py; frontend HTML/JS y secciones en app/static; Dockerfile de producción conservado.

Pruebas TQT: app/routers/test_station.py aporta API de operador y API bearer de agente; app/services/test_station.py persiste ejecuciones, eventos, cola de comandos y presencia. Reutiliza tarjetas/PCB y stm32_stations, con snapshots históricos de inventario. sec_validacion.js sustituye la interfaz BLE anterior, muestra S29 y reportes dentro del diseño vigente. sec_tarjetas.js enlaza el historial por ID interno.

Windows: station/test_station/agent.py reutiliza cinco módulos originales de v0.6.3. No escucha puertos. Emite eventos/reportes por HTTP de loopback o HTTPS; guarda cola y evidencia privada local. COM y BLE nunca se abren desde Docker. La rutina original y sus tiempos permanecen intactos.

Entorno local: compose.local.yaml, compose.tests.yaml y deploy/local-tests/. Volumen cm-local-tqt-web_test_data, puerto 127.0.0.1:18080; no túnel, red privilegiada ni socket Docker en la app. Docker de pruebas sin red usa bases temporales. Ver docs/PRUEBAS_TQT_LOCAL.md para restauración reproducible y resultados.
