# Indicador de vigencia STM32 — 1.4.48, 2026-10-27

Problema: el panel derecho se ponía verde por existir una grabación verificada, incluso si esa grabación llevaba FW4.3 y ya había FW4.4 aprobado. La lista sí avisaba «Desactualizada». La evidencia histórica era correcta; el color confundía verificación con vigencia.

R1/R3 usan ahora la misma comparación numérica para lista y panel: instalada frente a la versión aprobada más alta del mismo hardware. Historial verificado vigente: verde. Firmware anterior: naranja con texto «Desactualizada». Se muestran las versiones instalada/vigente. Sin catálogo confirmado no se asegura vigencia; sin firmware sigue rojo. Intentos posteriores sin verificar y errores conservan sus advertencias.

Elegir otro firmware a programar no cambia el contenido histórico ni el estado de actualización. Las imágenes beta y las de otro HW no elevan la versión vigente. No se cambia la API, el inventario, el agente, los trabajos ni los firmwares.

Evidencia aislada: 8 grupos nuevos Playwright (colores CSS renderizados naranja/verde, instalado/vigente, selector independiente, beta/otroHW, resultado incierto, catálogo caído, sinFW y R3), 5 grupos de estado histórico y 6 de agente fijo; todos PASS, sin erroresJS y móvil390 sin desborde. Solo los dos trabajos simulados de la regresión histórica; ninguna escritura a hardware real. 11 pruebas Python de versión/estado PASS, sintaxisJS, revisión de diff y ComposeQA correctos. ui-ux-pro-max: color acompañado de texto usando los componentes existentes; ECCverificación y suitePlaywright existente.

Base GitHub/producción comprobada: main454add0, web1.4.47, árbol limpio. Rama de esta corrección: codex/stm32-fw-indicador-20261027. Preparada1.4.48; pendiente autorización expresa de despliegue según AGENTS.md. No se aprueba firmware ni se programa ninguna tarjeta.
