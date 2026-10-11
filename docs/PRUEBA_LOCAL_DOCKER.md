# TQT en Docker local

Desde la raíz web, con Docker Desktop activo y cm instalado:

```powershell
cm docker up TQT-Web --file compose.local.yaml --service tqt
cm docker status TQT-Web --file compose.local.yaml
cm docker logs TQT-Web --file compose.local.yaml
```

Abrir http://127.0.0.1:18080. Health: http://127.0.0.1:18080/api/health. Sin cm, los equivalentes son `docker compose -p cm-local-tqt-web -f compose.local.yaml up -d --build tqt` y `docker compose -p cm-local-tqt-web -f compose.local.yaml ps`.

Este Compose usa el Dockerfile HTTP existente deploy/devsky/Dockerfile, sin arduino-cli. La aplicación utiliza una base tqt_local.db nueva en un volumen local separado; no se copian respaldos, SMTP, cuentas ni credenciales de producción y no se inicia Cloudflare. Las funciones de compilación/programación física no quedan probadas con esta imagen.

Las cuentas no se crean por defecto. Para probar acceso con cuentas de prueba, configurar credenciales locales nuevas explícitamente; nunca usar las de producción ni subirlas al repositorio.

Detener: `cm docker down TQT-Web --file compose.local.yaml`. Conserva los volúmenes de prueba; no afecta producción. GitHub almacena código y definiciones Docker. Las imágenes se reconstruyen desde esas definiciones; un registro de imágenes sería una integración adicional.
