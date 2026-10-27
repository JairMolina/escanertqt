# Plataforma I+D · Escáner TQT

Aplicación web del área de I+D para controlar la producción de tarjetas electrónicas. Empezó como el **Escáner TQT** (placas R1 + R2 + R3) y hoy es una plataforma con un portal (`/inicio`) desde el que se entra a cada módulo: registro de placas por QR con la cámara del celular, programación de firmware, etiquetas DYMO, costos e inventario de materiales, activos de la empresa y documentación del equipo.

**Versión actual: v1.4.46** · historial en [`CHANGELOG.md`](CHANGELOG.md) (la versión también se muestra en la app).

## Módulos

| Módulo | Ruta | Qué hace |
|---|---|---|
| **Escáner TQT** | `/` · `/monitor` | Recibir, emparejar R1 + R2 (+ R3), programar R1/R2 (ESP32 y STM32/J-Link), MAC, fechas de entrega, etiquetas DYMO, Excel mensual, Inventario TQTR con consumo y pedidos |
| **TPMS** | `/tpms` | Sensores de presión de llantas: alta por QR, pruebas y seguimiento |
| **Skudo AntiJammer** | `/antijammer` | Tarjetas RX y TX: alta por QR, pruebas y seguimiento |
| **SpeedLocker** | `/speedlocker` | Limitador de velocidad: alta por QR y seguimiento |
| **Skudo Sigfox** | `/sigfox` | Equipos con red Sigfox: alta y validación |
| **Caiquén** | `/caiquen` | Telemetría de tractocamión (J1939): alta y control |
| **Impresora** | `/impresora` | Activos de la empresa con etiqueta DYMO y QR para consultarlos con el celular |
| **Documentación TEAM HW** | `/documentacion` | Presentación pública de los proyectos y manual de usuario (`/documentacion/manual`) |

Los cinco módulos de placas (TPMS, AntiJammer, SpeedLocker, Sigfox y Caiquén) comparten la misma base:

- **Placas por QR:** cada módulo reconoce solo su propio formato de QR y rechaza los de los demás.
- **Costos:** cotizador por módulo; se importa el Excel del cotizador y se exporta con fórmulas. Calcula el costo por tarjeta y aparte los recurrentes (licencias).
- **Materiales:** existencias = entradas − salidas − consumo. Cada placa programada descuenta su lista de materiales y la devuelve si se desprograma o elimina.

## Acceso

- Toda la plataforma pide iniciar sesión con correo y contraseña, salvo **Documentación TEAM HW**, que es pública. Cada módulo tiene su pantalla de acceso (`/<módulo>/acceso`).
- Roles: **administrador** (todo), **general** y **consultor**; además, cada cuenta tiene los módulos que puede abrir.
- El panel **Cuentas y módulos** (desde «Acceso de administrador» en el portal) administra la matriz cuentas × módulos y las invitaciones por correo.
- `/admin` pide además la contraseña de supervisor. Ver [`docs/AUTENTICACION.md`](docs/AUTENTICACION.md) y [`docs/ADMIN.md`](docs/ADMIN.md).

## Uso

- **Celular** (con cámara): escanea los QR de las placas en Recibir · Emparejar · Programar · Consultar. También puede servir como **botón de escaneo** remoto vinculado a una PC.
- **PC**: consola de escritorio (`/monitor` en Escáner TQT y la vista de cada módulo).
- **Manual de usuario**: `/documentacion/manual` (también en Markdown en [`docs/manual/`](docs/manual/README.md)).

## Tecnología

Python + FastAPI · SQLite en modo WAL · WebSockets para sincronizar todas las pantallas · frontend en JavaScript sin framework ni dependencias externas · Docker · `arduino-cli` dentro de la imagen para compilar el firmware ESP32 · agente Windows para programar STM32 con J-Link · impresión DYMO local o en la DYMO compartida (Raspberry).

## Arrancar en local

```powershell
# Con Docker (recomendado): pide la contraseña de /admin, abre el firewall y levanta el contenedor
.\desplegar.ps1
# o, si ya existe .env:
docker compose build; docker compose up -d

# Sin Docker
pip install -r requirements.txt
python run_server.py
```

Después abre `https://<IP-de-la-PC>:8443` y entra con tu cuenta. Para quitar el aviso de «sitio no seguro», instala la autoridad local una vez por dispositivo: `.\instalar_certificado.ps1` en la PC y `/cert` en cada celular. Variables de entorno: [`.env.example`](.env.example). Guía completa: [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md).

**Producción:** corre en una Orange Pi detrás de Cloudflare. La configuración del sistema (red, servicios, permisos) vive en el repositorio `Lion-44-cpu/tqt-orangepi`, no aquí.

## Estructura del proyecto

```
app/
  main.py, config.py, ssl_cert.py   Arranque, rutas, configuración (APP_VERSION) y certificados
  modulos.py                        Catálogo de módulos del portal y qué ruta pertenece a cuál
  routers/                          API: núcleo TQT, auth, admin, plataforma (cuentas), un router por módulo
                                    (tpms, antijammer, speedlocker, sigfox, caiquen), costeo, activos, DYMO, ws…
  services/                         Usuarios y sesión, correo, Excel, DYMO, firmware ESP32/STM32,
                                    costeo, materiales, activos y lógica de cada módulo
  database/                         SQLite: modelos, parsers de QR, inventario y operaciones de admin
  static/                           Páginas HTML, JS, CSS e iconos; documentacion/ (pública) con el manual
firmware/                           ESP32 (R1, R2) y STM32 (R1, R3); ver firmware/README.md
station/                            Agente Windows de la estación (J-Link) y probador BLE
scripts/                            generar_manual_md.py, importar_activos_excel.py
templates/                          Plantilla del Excel mensual
tests/                              Pruebas unitarias/integración y e2e/ con navegador
docs/                               Documentación (ver abajo)
deploy/                             Configuración de servidores sin secretos
desplegar.ps1, respaldar.ps1        Despliegue y respaldo local
Dockerfile, docker-compose.yml      Imagen y contenedor (puerto 8443)
```

### Agregar un módulo de placas

Cada módulo es un clon del anterior: tablas `<slug>_pcb` / `<slug>_eventos`, acceso `/<slug>/acceso`, API `/api/<slug>`, parser de QR en `database/models.py` con su espejo en `static/js/common.js`, entrada en `app/modulos.py`, Costos y Materiales en `services/costeo.py` (`MODULOS_COSTEO`), un capítulo en `static/documentacion/documentacion.js` y su guía JSON en `static/documentacion/guias/` (después correr `python scripts/generar_manual_md.py`).

## Pruebas

```powershell
pip install -r requirements-dev.txt
cd tests
python -m unittest discover        # ~880 pruebas, usan carpetas y bases temporales
python -m unittest test_tpms       # un solo archivo
```

El arnés `tests/_aislamiento.py` inicia sesión solo en las pruebas; `cliente_sin_sesion(app)` prueba lo contrario. Las pruebas de navegador (Playwright + Chrome) están en `tests/e2e/`. `test_manual_guias` comprueba que cada módulo tenga su guía y que `docs/manual/` esté al día.

## Documentación (`docs/`)

| Documento | Contenido |
|---|---|
| [`manual/`](docs/manual/README.md) | Manual de usuario por módulo (generado desde las guías JSON) |
| [`SPEC_v2.md`](docs/SPEC_v2.md) | Flujo de planta TQT, API y reglas de negocio |
| [`AUTENTICACION.md`](docs/AUTENTICACION.md) | Cuentas, sesión, bloqueo por intentos |
| [`DESPLIEGUE.md`](docs/DESPLIEGUE.md) | Docker, red WiFi, firewall, certificado en PC y celulares |
| [`ESCRITORIO.md`](docs/ESCRITORIO.md) | Consola de PC |
| [`ADMIN.md`](docs/ADMIN.md) | Área de administración |
| [`DYMO.md`](docs/DYMO.md) | Etiquetas y configuración de DYMO |
| [`PROGRAMACION_STM32.md`](docs/PROGRAMACION_STM32.md) | Programación de R1 STM32 con J-Link y agente Windows |
| [`DISENO.md`](docs/DISENO.md) | Sistema de diseño |
| [`CODEX_ESTADO.md`](docs/CODEX_ESTADO.md) | Estado actual del desarrollo y pendientes |
| `qa/`, `capturas/` | Informes de pruebas y capturas |

## Datos y secretos (NO van al repositorio)

`.env` (contraseñas, SMTP e IP), `certs/` (llaves privadas), `*.db` (bases reales), `respaldos/`, `excel_mensual/`, `exports/`, el `config.json` de cada estación y los Excel reales de activos y cotizadores. Ver `.gitignore`. Todo lo que se ponga en `app/static/documentacion/` es público: nada de datos reales ni secretos ahí. Las contraseñas iniciales de las cuentas no se documentan: cámbialas al primer ingreso.
