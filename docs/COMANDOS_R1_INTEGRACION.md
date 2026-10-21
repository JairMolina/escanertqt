# Comandos en Gestión

Sección nativa de la consola: `/monitor#/comandos`. También se abre desde
«Más opciones → Comandos» en la vista móvil. Usa la sesión, roles, menú,
tipografías locales y tokens claro/oscuro del proyecto. La sección prepara
y copia texto; no abre puertos ni envía órdenes a tarjetas.

## Archivos y ampliación del catálogo

- `app/static/catalogos/comandos_r1.json`: comandos, metadatos de interfaz,
  versiones comprobadas y 28 valores/estados iniciales. Los `id` son permanentes,
  independientes del orden del arreglo: asignar un ID nuevo sin reciclarlo al
  agregar un comando. Así se conservan favoritos y enlaces existentes.
- `app/static/js/comandos_core.js`: funciones puras de filtros, validación,
  conversión de formatos y comparación. Los tipos de parámetros están en
  `validateValue`; las relaciones y notas particulares de comandos existentes
  se vinculan por ID permanente. Un tipo de parámetro nuevo requiere añadir
  validación y su control en `parameterControl` de la sección.
- `app/static/js/sec_comandos.js`: registro/montaje/desmontaje, constructor,
  favoritos y parámetros del router. Consulta el JSON cuando se abre la sección.
- `app/static/css/sec_comandos.css`: estilos bajo `.tqt-comandos`; sin reglas
  globales para `body`, navegación o variables de la aplicación.
- `app/static/catalogos/COMANDOS_R1.md`: documentación técnica descargable.

Para incorporar un firmware: añadirlo en `firmware_versions`, actualizar
`supported_versions` de cada comando con evidencia del código de esa versión y
`values_by_version` de cada valor de fábrica. Las comparaciones se calculan desde
estos datos. Mantener sincronizadas las notas técnicas y las pruebas pertinentes.
Solo está documentado R1 HW3.0; otro hardware muestra «sin documentación».

## Formato y estado inicial

Plataforma es el formato inicial: `$SMSG=ON` → `AT$SMSG=1,0,"ON"`.
Los parámetros actualizan de inmediato vista previa y texto copiado.
Bluetooth conserva sus cuatro caracteres; `$OK` conserva el acuse original.
CRLF empieza desactivado, se puede activar únicamente para salida Serial/GPS,
y al copiar añade los bytes reales CR y LF. Volver a Plataforma lo desactiva.
Tiempo de fábrica: base de 4000 ms, adicional 0 s. Los ejemplos editables no
representan una lectura ni una modificación de la tarjeta.

Favoritos: clave local `tqt.comandos.r1.favorites.v1`. Los parámetros de la
sección viven dentro de `#/comandos?...`: `hw`, `fw`, `view`, `cmd`, `channel`,
`group`, `kind`, `q`, `compatible`, `favorites`, `new`, `format`, `crlf`, `value`,
`other`, `from`, `to`, `changes`, `dq`, `dtype`. Se conservan el query de la
página (como `lote`) y las claves desconocidas del hash. El router existente
atiende enlaces y cambios de parámetros; se limpia el diálogo al salir.

## Revisión local

Base de implementación: main `7fe97eb`, web 1.4.28. No se modifican firmware,
configuración de producción ni datos reales. El checkout registrado con cambios
locales se conserva; esta integración se trabaja en `codex/comandos-r1-local`.

Definir una contraseña de prueba en `TQT_COMMANDS_QA_PASSWORD` (solo entorno),
y ejecutar:

```powershell
docker compose -p tqt-comandos-qa -f compose.commands-local.yaml config --quiet
docker compose -p tqt-comandos-qa -f compose.commands-local.yaml up -d --build
docker compose -p tqt-comandos-qa -f compose.commands-local.yaml --profile tests run --rm --build tests
node --test tests/comandos_core.test.cjs
node tests/comandos_e2e.cjs
```

Instancia: `http://localhost:18086/monitor#/comandos`. Volumen independiente
`tqt-comandos-qa_commands_review`. Sin túnel ni agentes de hardware.
Playwright debe estar disponible en Node y tener Chromium de pruebas instalado.
`TQT_COMMANDS_QA_OUTPUT` permite guardar capturas/resultados fuera del repositorio.
La prueba E2E usa el backend real y portapapeles real en Chromium aislado.

Verificación de esta integración: 9 pruebas Node, 16 escenarios E2E con
Playwright y 52 pruebas Python (catálogo, consultor, versión, autenticación y
API) aprobadas. Capturas en 1440, 1024 y 390 px, claro y oscuro; sin desborde,
excepciones JS ni respuestas HTTP de error durante el recorrido E2E.
Compose validado, build completado y contenedor local saludable. Sin push,
publicación ni programación física. Capacidades usadas: ui-ux-pro-max para
adaptación al sistema visual existente; ECC E2E/verificación para las pruebas
proporcionales y revisión de cambios; CM para continuidad y originales.
