# Decisiones verificadas

- 2026-10-13: conservar la arquitectura FastAPI/SQLite y sustituir la sección validacion, sin duplicar navegación.
- Reutilizar el motor original 0.6.3 en Windows; adaptador saliente independiente para hardware, sin acceso COM desde Docker ni puerto de control público.
- Copia local aislada de un respaldo verificado; migraciones agregan tablas de evidencia y no actualizan inventario/fabricación. La restricción inicial de publicación quedó revocada el 2026-10-13 por la petición expresa del usuario de subir Git y desplegar en la web.
- Comparar nombre/serie R1, IDR R2 y MAC de firmware/BLE contra snapshot real. Discrepancias no se asocian automáticamente a otra tarjeta y nunca se ocultan tras aprobación funcional.
- Mantener eventos y reportes permanentes, con cola de reintentos que no repite movimientos. Aprobación de pruebas y liberación al almacén son independientes.
- Conservar LOG como texto íntegro y escapado visualmente, después del resumen y las 14 etapas. Exportación JSON incluye eventos; PDF se obtiene mediante impresión del reporte integrado.
- Producción se actualiza con avance directo de Git, respaldo SQLite en caliente y reinicio exclusivo del contenedor de aplicación. Preservar el Compose y el túnel del servidor; no copiar la base ni las pruebas de desarrollo a producción.
