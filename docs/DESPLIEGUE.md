# Despliegue de Escaner TQT en la red WiFi local (Docker)

Objetivo: la PC del taller corre el servidor; los celulares conectados al **mismo módem** abren `https://<IP-de-la-PC>:8443`.
La cámara del celular solo funciona con **HTTPS**, por eso el servidor usa un certificado propio (se genera solo).

## Antes de empezar (una sola vez)
1. **Docker Desktop** instalado y abierto (Ajustes → General: *Start Docker Desktop when you sign in*, y *Use WSL 2 based engine*).
2. **IP fija para la PC.** En el panel del módem (normalmente `192.168.1.1` o `192.168.0.1`) → DHCP → *Reserva de direcciones / Static lease*: asigna siempre la misma IP a la PC (busca por su MAC con `ipconfig /all`). Si la IP cambia, el certificado y el enlace de los celulares dejan de servir.
3. **Aislamiento de clientes desactivado.** En el WiFi del módem, apaga *AP Isolation / Client Isolation* (si está activo, los celulares no ven a la PC). Todos los celulares deben estar en el WiFi del módem, no en datos móviles ni en un WiFi de invitados.
4. **PC siempre encendida** en el taller, con inicio de sesión automático si se quiere que arranque sola tras un corte de luz (`netplwiz`).

## Desplegar (2 minutos)
1. Copia la carpeta del proyecto a la PC del taller (p. ej. `C:\EscanerTQT`).
2. Clic derecho en PowerShell → **Ejecutar como administrador**, y:
   ```powershell
   cd C:\EscanerTQT
   Set-ExecutionPolicy -Scope Process Bypass
   .\desplegar.ps1
   ```
   Te pide una **contraseña para el área `/admin`** (mín. 8 caracteres; Enter = sin admin) y la guarda en `.env` (entre comillas simples, así `$`, `#` o espacios no se interpretan; solo se prohíbe la comilla simple). Para cambiarla, edita `TQT_ADMIN_PASSWORD` en `.env` y ejecuta `docker compose up -d`. Detalles del área de administración: `docs/ADMIN.md`.
   El script: detecta la IP de la PC, la guarda en `.env`, abre el puerto **8443** en el Firewall de Windows (regla `Escaner TQT 8443`, **solo red local**: `-RemoteAddress LocalSubnet`, requiere administrador), construye la imagen, levanta el contenedor, espera a `healthy` y muestra las URLs.
   `.\desplegar.ps1 -WhatIf` simula todo (muestra la IP y lo que haría) sin escribir `.env`, sin tocar el firewall y sin levantar nada.
   Si `TQT_HOST_IP` no está definida al usar `docker compose` a mano, falla con el mensaje "Ejecuta .\desplegar.ps1 o crea .env".
3. Comprueba en la propia PC: `https://localhost:8443`. La primera vez verás el aviso de certificado hasta que instales la autoridad (sección "Quitar el aviso de sitio no seguro").

El contenedor tiene `restart: unless-stopped`: se levanta solo cuando Docker Desktop arranca.

## Conectar los celulares
1. Celular al WiFi del módem. Abre `https://<IP-de-la-PC>:8443` (p. ej. `https://192.168.1.50:8443`).
2. **Android (Chrome):** *Configuración avanzada → Continuar a 192.168.1.50 (no seguro)* → permite la cámara.
3. **iPhone (Safari):** *Mostrar detalles → visitar este sitio* → permite la cámara. Para quitar el aviso y asegurar la conexión en vivo, instala la autoridad (sección anterior).
4. Añade la página a la pantalla de inicio para abrirla como app (Compartir → *Añadir a pantalla de inicio*).
5. Si cambió la IP de la PC: vuelve a ejecutar `.\desplegar.ps1` (renueva solo el certificado del servidor). La autoridad ya instalada en PC y celulares **no** hay que reinstalarla.

## Quitar el aviso de "sitio no seguro" (una sola vez por dispositivo)
El navegador muestra "Tu conexión no es privada / No es seguro" porque no conoce quién firmó el certificado del servidor.
Se soluciona instalando la **autoridad certificadora local** ("Escaner TQT Local CA", se crea sola en `certs\ca.pem`).
Después el candado aparece sin avisos y **sigue valiendo aunque cambie la IP de la PC** (el certificado del servidor se
renueva solo; la autoridad no cambia). Solo puede firmar IP privadas y `localhost`.

**En esta PC** (Chrome y Edge): abre PowerShell en la carpeta del proyecto y ejecuta
`.\instalar_certificado.ps1` (como Administrador la instala para todos los usuarios; con `-SoloUsuario` solo para ti).
Cierra y vuelve a abrir el navegador. Para quitarla: `.\instalar_certificado.ps1 -Quitar`.

**Android:** abre `https://<IP>:8443/cert` (o pásate el archivo `certs\ca.pem`), guárdalo como `escaner-tqt-ca.crt` y ve a
*Ajustes → Seguridad → Más ajustes de seguridad → Cifrado y credenciales → Instalar un certificado → Certificado de CA*
(el nombre exacto varía según la marca). Chrome mostrará el candado.

**iPhone/iPad:** abre `https://<IP>:8443/cert` en Safari → *Permitir* → *Ajustes → Perfil descargado → Instalar*, y luego
*Ajustes → General → Información → Ajustes de confianza de certificados* → activa `Escaner TQT Local CA`.

Sin instalarla todo funciona igual (puedes pulsar *Avanzado → Continuar*), pero en iPhone la conexión en vivo (WebSocket) puede fallar.

## Operación diaria
| Tarea | Comando (en la carpeta del proyecto) |
|---|---|
| Ver estado | `docker compose ps` |
| Ver logs | `docker compose logs -f` |
| Reiniciar | `docker compose restart` |
| Detener / iniciar | `docker compose stop` / `docker compose start` |
| Actualizar tras cambiar código | `.\desplegar.ps1` |
| Respaldo de la base de datos | `.\respaldar.ps1` → `respaldos\tqt_AAAAMMDD_HHMM.db` (comprueba `integrity_check`; conserva los últimos 30 respaldos programados; los respaldos previos a un borrado del admin, `tqt_..._<motivo>.db`, no se rotan) |

Respaldo automático diario a las 18:00:
`schtasks /Create /SC DAILY /ST 18:00 /TN "Respaldo TQT" /TR "powershell -ExecutionPolicy Bypass -File C:\EscanerTQT\respaldar.ps1"`

**Certificados:** viven en `.\certs\` y se conservan entre reinicios (`ca.pem`/`ca.key` = autoridad local; `cert.pem`/`key.pem` = servidor). **No compartas ni subas `ca.key` ni `key.pem`**; si `certs\` se pierde hay que reinstalar la autoridad en cada dispositivo. Si cambia `TQT_HOST_IP` solo se renueva el certificado del servidor.

**Dónde están los datos:** la base de datos vive en el volumen Docker `tqt_db` (no se pierde al actualizar la imagen). Los Excel mensuales quedan en `.\excel_mensual\`, los certificados en `.\certs\`. No borres el volumen (`docker compose down -v` **borra la base de datos**; usa `docker compose down` a secas).
Restaurar un respaldo: `docker compose stop`, luego
`docker run --rm -v escaner-tqt_tqt_db:/data/db -v "${PWD}\respaldos:/b" python:3.13-slim cp /b/tqt_AAAAMMDD_HHMM.db /data/db/tqt_produccion.db` y `docker compose start`
(el nombre del volumen puede llevar otro prefijo: `docker volume ls`).

## Verificación rápida (lista de comprobación)
- [ ] `docker compose ps` muestra `healthy`.
- [ ] Desde otro dispositivo: `https://<IP>:8443/api/config` responde JSON.
- [ ] El celular abre la app, pide permiso de cámara y muestra el visor.
- [ ] Escanear un QR suena y aparece la fila en el celular **y** en `/monitor` de la PC (WebSocket).
- [ ] Reiniciar la PC: al volver Docker Desktop, la app responde sin intervención.

## Problemas frecuentes
| Síntoma | Causa / solución |
|---|---|
| El celular no abre la página | ¿Mismo WiFi? ¿Aislamiento de clientes activo? ¿Regla de firewall `Escaner TQT 8443` creada (ejecutar como administrador)? Prueba `Test-NetConnection <IP> -Port 8443` desde otra PC. |
| "Cámara bloqueada / no disponible" | Se abrió por `http://` o por un nombre/IP distinto al del certificado. Usa siempre `https://<IP>:8443`. |
| Aviso "sitio no seguro" | Falta instalar la autoridad local en ese dispositivo (sección "Quitar el aviso de sitio no seguro"). |
| Vuelve el aviso tras cambiar la IP | Ejecuta `.\desplegar.ps1` (renueva el certificado del servidor); la autoridad instalada sigue valiendo. Si borraste `certs\`, se crea una autoridad nueva y hay que reinstalarla. |
| `Docker Desktop no está en ejecución` | Ábrelo y espera *Engine running*. |
| Puerto 8443 ocupado | Cierra el `run_server.py` local antes de usar Docker (no correr ambos). |

## Seguridad
La API de las acciones normales del taller **no tiene autenticación** (lo masivo/destructivo sí, ver `docs/ADMIN.md`): cualquiera en esa WiFi puede escribir datos. El servidor rechaza las peticiones que cambian datos si vienen de otro sitio web (cabecera `Origin` distinta del servidor; también el WebSocket) y envía cabeceras de seguridad (`X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Cache-Control: no-store` en `/api`). No expongas el puerto 8443 a Internet (no abras puertos en el módem) y usa una contraseña WPA2/WPA3 fuerte en el WiFi del taller. Un PIN de operador es la siguiente mejora recomendada.
