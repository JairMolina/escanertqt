# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 00:31 UTC
Commit de referencia: `cdad30fa90f6` (puede no incluir cambios pendientes)

## Avance reportado
v1.3.72 desplegada: catalogo persistente HEX R1/R3, selector del firmware compatible mas reciente y trabajos fijados a la version elegida. Commit aplicacion cdad30f; produccion saludable y catalogo solo R1 4.3 / R3 1.0. V1.1 aportado usado solo para validar y cancelado antes de guardarlo.

## Siguiente paso
Recargar la web y usar Subir HEX > confirmar HW/FW > Guardar firmware. El usuario elegira que archivos registrar; no cargar automaticamente el V1.1 aportado para prueba.

## Evidencia
37 casos STM32/catalogo y 11 TQT correctos. Playwright valido selector, formulario, cancelacion de prueba V1.1, duplicado, persistencia tras recrear Docker y movil 390 px sin desborde. Respaldo pre-tqt-1372-20261014T002844Z, SQLite ok, 100 tarjetas y 300 PCB. ECC backend y seguridad.
