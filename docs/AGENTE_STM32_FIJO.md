# Agente STM32 fijo — web 1.4.42

## Problema y causa

El filtro local se basaba en la IP pública compartida. Cada5segundos, si la estación guardada no aparecía online, se escogía la primera online y se sobrescribía la preferencia. Varias laptops detrás del mismo módem podían alternar el destino. El campo Nombre de estación solo registra un agente nuevo; no identifica el agente activo.

## Comportamiento corregido

- Selector visible para R1/R3 con nombre, sufijo del ID y estado. Una elección explícita queda guardada en tqt.station.stm32, en este navegador y origen. R1/R3 se sincronizan por la acción del operador.
- Un agente desconectado o ausente conserva su ID; se muestra no disponible y no se permite grabar. Si no hay vínculo anterior, se exige elegir uno. Nunca se elige por orden o IP.
- La instalación desde el navegador conserva el vínculo por ID que entrega el instalador; ese ID se espera aunque aún esté offline. La web no obtiene por sí sola el nombre de Windows ni distingue laptops por una IP NAT compartida.
- Se consulta presencia cada5segundos pero no se reconstruye la lista si nada cambió. Los cambios de presencia solo afectan al estado, no a la elección.
- Selección bloqueada durante trabajo; respuestas tardías ignoran cambios posteriores y grabación/cancelación usan la estación capturada para el trabajo. Se recuperan solo los trabajos del rol correspondiente.
- Si el navegador impide localStorage, la sesión mantiene el agente y avisa que no pudo guardar la elección. Borrar datos del sitio o cambiar de navegador elimina el vínculo persistido.

## Prueba reproducible

Archivo tests/stm32_station_binding.playwright.js, sobre QA aislada localhost18089. Agentes y trabajos simulados; no abre J-Link ni genera trabajos en producción. Seis grupos comprobados: offline/ausencia con sondeo real de5segundos, selección manual/R3/recarga, móvil390sin desborde, varias laptops conmismaIP sin elección automática, respuestaobsoleta ignorada, y programación/cancelación dirigidas al mismo agente. Cero erroresJS. Sintaxis JS y revisión del diff correctas. No se repitió la batería de backend porque no cambió su código.

En la captura original se observa DEV6 elegido y error J-Link de conexión al probe. Este cambio corrige la selección; si el error persiste en el agente correcto hay que comprobar físicamente probe/USB/driver/alimentación, sin declarar el problema eléctrico solucionado por esta interfaz.

Capacidades aplicadas: ui-ux-pro-max para claridad del selector, ECCverification para regresión Playwright. CMadjuntar para el original, únicamente después de autorización expresa adicional de la captura y su destino tras el rechazo de revisión automática.

El usuario autorizó el despliegue de esta corrección sin programar tarjetas y el respaldo de la captura en la Mini PC. Ver CODEX_ESTADO/HISTORIAL para resultado real del despliegue.


## Despliegue verificado 2026-10-26

Web1.4.42 desplegada y saludable, código c1113ea0d98299f847675754a4ecea08e0a711d5. Respaldo previo /backups/predeploy_1.4.42_20261026_155549.db; sin trabajos activos al recrear solo web. El ajuste final estático del resumen de conexión se aplicó sin otro reinicio. Login público y apihealth correctos; SHA256JS local/servidor coinciden (352f999cdf8ba1eacb2be45d050575d0e6fe52f5712fbd19e6a83aaf3347d81e). Cache1442b. Firmware4.4 siguebeta; sin nuevas grabaciones por esta tarea.

El usuario autorizó explícitamente captura y destino tras rechazo automático. Original respaldado y verificado enMiniPC, SHA256prefijof00308f7f1f3; nota técnica remota y0adjuntos pendientes. Captura fuera deGit.

Usuario: recargar Ctrl+F5 cuando no haya grabación y seleccionar UNA vez el agente que tiene suJLink en AgenteWindows conectadoalJLink. El campo de instalación de abajo no cambia esa elección. Si aparece desconectado se conserva el vínculo; solo el operador puede elegir otro. Prueba física real pendiente si persiste error deprobeconelagentecorrecto.
