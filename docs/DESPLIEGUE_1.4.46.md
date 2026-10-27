# Continuidad y despliegue web 1.4.46 — 2026-10-27

Se revisó GitHub y producción antes de trabajar. Ambos estaban en 1.4.45,
`1bb98bd`; Comandos y las integraciones recientes ya estaban en main. Los
pendientes documentales que todavía decían «preparada 1.4.41 sin desplegar»
eran anteriores al estado real. Esta versión alinea servidor, README,
changelog y prueba de versión sobre esa base, conservando sus funciones.

## Publicación y aplicación

- Commit de código: `000a30b`, publicado en main y etiquetado `v1.4.46`.
- Servidor verificado: `orangepizero3`, `/home/orangepi/escanertqt`.
- Acceso utilizado: SSH por MiniPc hacia `orangepi@192.168.4.70`. El alias
  directo Tailscale de OrangePi no respondió. No se cambiaron rutas de red.
- Repositorio de servidor limpio; actualización por fast-forward a la etiqueta.
- Compose vigente: `servidor/compose.yml`; solo se recreó `tqt` con
  `up -d --no-deps --force-recreate tqt`. La aplicación está montada en lectura
  desde el checkout. No había cambios de dependencias que exigieran otra imagen.
- `cloudflared` permaneció activo (5 días de ejecución al comprobar).

## Respaldo y verificaciones

- Trabajos activos antes de aplicar: 0 STM32, 0 pruebas, 0 comandos recientes,
  0 verificaciones R2. No se abrió una sonda ni se enviaron órdenes a tarjetas.
- Respaldo SQLite mediante `backup`, con `integrity_check=ok`:
  `/backups/predeploy_1.4.46_20261027_151013.db`.
- SHA256 del respaldo:
  `403b25b8b44903eb383f80dd3acdefd05f8def41ff22c9dff0d18a7c02766f9e`.
- 115 pruebas Python, 9 pruebas Node y 16 recorridos Playwright aprobados
  sobre base QA aislada, incluyendo portapapeles real, filtros y navegación.
  Capturas a 1440/1024/390 en ambos temas; sin errores JS/HTTP ni desborde.
- Compose y build locales correctos; contenedor de producción `running healthy`.
- Comprobación interna: APP_VERSION=1.4.46, `quick_check=ok`, `/api/health`
  devuelve `{"ok":true}`. Login público HTTP200 y versión1.4.46 visible.
- Una consulta inicial de urllib sin User-Agent de navegador recibió HTTP403;
  se contrastó con salud interna y acceso público normal antes de cerrar.

## Pendientes vigentes

El banco físico del FW4.4 beta continúa pendiente. Esta publicación no aprueba
firmware, programa placas ni ejecuta limpiezas de agentes o inventario.
Las notas históricas de mantenimiento requieren volver a comprobar el estado
real antes de aplicar acciones destructivas.

CM se utilizó para continuidad, Git y sincronización documental. El plan de
`cm deploy` del proyecto registrado en MiniPc no representaba este host de
producción; se ejecutó el procedimiento SSH/Docker vigente en OrangePi con la
autorización expresa de despliegue del usuario. ECC verificación y la suite
E2E existente aportaron las comprobaciones proporcionales al cambio.
