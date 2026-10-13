# Memoria de TQT-Web

Aplicación Inventario TQT (JairMolina/escanertqt): FastAPI, SQLite, WebSockets y HTML/JS. Mantener separada de TQT-OrangePi, que contiene infraestructura del servidor.

## Estado confirmado 2026-10-13

Rama local codex/tqt-test-station basada en 4bfbc88 (v1.3.69). Integración real TQT Test Station 0.6.3 en la sección existente validacion. Docker local de esta laptop, puerto loopback 18080; volumen independiente con copia íntegra del inventario: 100 tarjetas y 300 PCB. Agente Windows saliente para COM/BLE; cinco módulos originales idénticos en SHA256, tiempos y 14 etapas conservados.

Dos pruebas físicas R1 0036 / COM10 / R2 0077 finalizaron 14/14 aprobadas, cada una con ID e historial independiente. Reportes con cotejo de inventario, JSON y LOG íntegro; las pruebas no autorizan liberar tarjetas. Datos originales de tarjetas, PCB e historial de fabricación permanecen idénticos.

## Accesos y límites

Web local http://localhost:18080/monitor#/validacion. Instrucciones y evidencias en docs/PRUEBAS_TQT_LOCAL.md. Base, respaldo, credenciales y reportes reales fuera de Git. CM preservó los originales aportados en almacenamiento privado central; no se indexan binarios ni bases.

No hubo push ni despliegue de aplicación, cambios en producción, Cloudflare o servicios de otros proyectos. Hay deuda de regresión preexistente en pruebas Linux; la comparación con GitHub no encontró fallos nuevos. Consulte la guía local antes de reiniciar/restaurar y revise la tarjeta físicamente antes de repetir una ejecución interrumpida.
