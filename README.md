# Escáner TQT

Aplicación web local para la planta de tarjetas electrónicas TQT. Registra las PCB con la cámara del celular, las empareja en tarjetas (R1 + R2 + R3), captura las MAC y el firmware de R1/R2, imprime etiquetas DYMO y sincroniza el Excel mensual de control de producción.

**Versión actual: v1.3.18** · historial en [`CHANGELOG.md`](CHANGELOG.md) (la versión también se muestra en la app).

## Qué hace

| Función | Dónde |
|---|---|
| **Recibir** placas por QR/código de barras y confirmar la recepción por equipo | Celular |
| **Emparejar** R1 + R2 (y R3, manual o automático) en tarjetas numeradas, incluidas las impares | Celular y consola |
| **Programar** R1/R2: compilar el firmware y flashearlo por USB (Web Serial) y guardar la MAC leída | Consola de PC |
| **Consultar** una tarjeta o placa por número, serie o código | Celular y consola |
| **Fechas y entrega**: llegada, finalizado (automáticas) y entrega; gabinete Quintalock / Translock | Consola |
| **Etiquetas DYMO** con QR (DYMO Label Software v8 o DYMO Connect), impresión por lote | Consola |
| **Excel mensual**: importar y exportar sin perder fórmulas, tablas ni validaciones | Consola |
| **Administración**: movimientos, respaldos y mantenimiento (clave de supervisor) | `/admin` |

- **Celular** (con cámara): `https://<IP-de-la-PC>:8443` → Recibir · Emparejar · Programar · Consultar.
- **PC** (sin cámara): la misma dirección abre la consola de escritorio en `/monitor`.
- **Acceso:** toda la app exige iniciar sesión con correo y contraseña. `/admin` pide además la contraseña de supervisor. Ver [`docs/AUTENTICACION.md`](docs/AUTENTICACION.md).

## Tecnología

Python + FastAPI sobre HTTPS local (certificado propio, se genera solo) · SQLite en modo WAL · WebSockets para tener todas las pantallas sincronizadas · frontend sin dependencias externas · Docker para el despliegue · `arduino-cli` dentro de la imagen para compilar el firmware ESP32.

## Arrancar

```powershell
# Con Docker (recomendado): pide la contraseña de /admin, abre el firewall y levanta el contenedor
.\desplegar.ps1

# Sin Docker
pip install -r requirements.txt
python run_server.py
```

Después abre `https://<IP-de-la-PC>:8443` y entra con tu cuenta. Para quitar el aviso de "sitio no seguro", instala la autoridad local una vez por dispositivo: `.\instalar_certificado.ps1` en la PC y `/cert` en cada celular. Guía completa: [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md).

## Estructura del proyecto

```
app/
  main.py, config.py, ssl_cert.py   Arranque, configuración (APP_VERSION) y certificados
  routers/                          API: api, auth, admin, inventario, excel_dymo, ws
  services/                         Usuarios y sesión, admin, Excel, DYMO, compilación de firmware
  database/                         SQLite: modelos, inventario y operaciones de admin
  static/                           Páginas (HTML), JS, CSS, fuentes e iconos
firmware/                           .ino de R1 y R2 (ESP32); ver firmware/README.md
templates/                          Plantilla del Excel mensual
tests/                              Pruebas unitarias/integración y e2e/ con navegador
docs/                               Documentación (ver abajo)
desplegar.ps1, respaldar.ps1        Despliegue y respaldo
Dockerfile, docker-compose.yml      Imagen y contenedor (puerto 8443)
```

## Pruebas

```powershell
pip install -r requirements-dev.txt
python -m unittest discover -s tests     # ~470 pruebas, usan carpetas temporales
```

El arnés `tests/_aislamiento.py` inicia sesión solo en las pruebas; `cliente_sin_sesion(app)` prueba lo contrario. Las pruebas de navegador (Playwright + Chrome) están en `tests/e2e/`; los scripts que hablan con la API necesitan iniciar sesión primero.

## Documentación (`docs/`)

| Documento | Contenido |
|---|---|
| [`SPEC_v2.md`](docs/SPEC_v2.md) | Flujo de planta, API y reglas de negocio |
| [`AUTENTICACION.md`](docs/AUTENTICACION.md) | Cuentas, sesión, bloqueo por intentos |
| [`DESPLIEGUE.md`](docs/DESPLIEGUE.md) | Docker, red WiFi, firewall, certificado en PC y celulares |
| [`ESCRITORIO.md`](docs/ESCRITORIO.md) | Consola de PC |
| [`ADMIN.md`](docs/ADMIN.md) | Área de administración |
| [`DYMO.md`](docs/DYMO.md) | Etiquetas y configuración de DYMO |
| [`DISENO.md`](docs/DISENO.md) | Sistema de diseño |
| `qa/`, `capturas/` | Informes de pruebas y capturas |

## Datos y secretos (NO van al repositorio)

`.env` (contraseña de admin e IP), `certs/` (llaves privadas), `*.db` (base real), `respaldos/`, `excel_mensual/`, `exports/`. Ver `.gitignore`. Las contraseñas iniciales de las cuentas no se documentan aquí: cámbialas al primer ingreso.
