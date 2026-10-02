<#
  Despliegue de Escaner TQT en la PC del taller (Docker Desktop).
  Uso:  clic derecho > "Ejecutar con PowerShell" como Administrador   (o:  .\desplegar.ps1)
  Simulacion sin cambios:  .\desplegar.ps1 -WhatIf   (muestra la IP y lo que haria; no escribe .env, no toca el firewall, no levanta nada)
  Hace: detecta la IP LAN, la guarda en .env, abre el puerto 8443 (solo red local) en el firewall,
        construye y levanta el contenedor, y muestra las URLs para celulares.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-LanIp {
    # Interfaz con puerta de enlace predeterminada (la que sale al modem), ignorando Docker/WSL/VPN
    $cfg = Get-NetIPConfiguration | Where-Object {
        $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" -and
        $_.InterfaceAlias -notmatch "vEthernet|WSL|Docker|VPN|Loopback|VirtualBox|VMware"
    } | Select-Object -First 1
    if (-not $cfg) { throw "No se detecto una red activa con puerta de enlace. Conecta la PC al modem por cable o WiFi." }
    return ($cfg.IPv4Address | Select-Object -First 1).IPAddress
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker no esta instalado. Instala Docker Desktop (WSL2) y reinicia." }
# 'docker info' escribe en stderr si el motor no esta encendido: con "Stop" eso abortaria con un error crudo en vez del mensaje claro
$ErrorActionPreference = "Continue"; docker info *> $null; $dockerOk = ($LASTEXITCODE -eq 0); $ErrorActionPreference = "Stop"
if (-not $dockerOk) { throw "Docker Desktop no esta en ejecucion. Abrelo y espera a que diga 'Engine running'." }

$ip = if ($env:TQT_HOST_IP) { $env:TQT_HOST_IP } else { Get-LanIp }
$parsed = $null
if (-not [System.Net.IPAddress]::TryParse($ip, [ref]$parsed) -or $parsed.AddressFamily -ne "InterNetwork") { throw "TQT_HOST_IP '$ip' no es una direccion IPv4 valida." }
Write-Host "IP de esta PC en la red del modem: $ip" -ForegroundColor Cyan

# Conserva la contrasena de admin existente; si no hay, la pide (min. 8 caracteres; vacia = admin deshabilitado).
# En .env va entre comillas simples: asi Docker Compose no interpreta '$', '#' ni espacios de la contrasena.
$pass = ""
if (Test-Path .env) {
    $m = Select-String -Path .env -Pattern '^TQT_ADMIN_PASSWORD=(.*)$' | Select-Object -First 1
    if ($m) { $pass = $m.Matches[0].Groups[1].Value.Trim(); if ($pass -match "^'(.*)'$") { $pass = $Matches[1] } }
}
if (-not $pass -and -not $WhatIfPreference) {
    $sec = Read-Host "Contrasena para el area /admin (min. 8 caracteres, Enter = sin admin)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { $pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($pass -and $pass.Length -lt 8) { throw "La contrasena debe tener al menos 8 caracteres." }
}
if ($pass -match "['\r\n]") { throw "La contrasena no puede contener comillas simples ni saltos de linea." }
if ($pass -and $pass.Length -lt 8) { throw "TQT_ADMIN_PASSWORD en .env tiene menos de 8 caracteres: corrigela o borra esa linea." }
if ($PSCmdlet.ShouldProcess((Join-Path $PSScriptRoot ".env"), "Escribir TQT_HOST_IP=$ip y la contrasena de admin")) {
    $contenido = "TQT_HOST_IP=$ip`nTZ=America/Mexico_City`nTQT_ADMIN_PASSWORD='$pass'`n"
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot ".env"), $contenido, (New-Object System.Text.UTF8Encoding($false)))
}

# Firewall (requiere administrador; si no, avisa y continua). Solo la red local: nunca Internet.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    if (-not (Get-NetFirewallRule -DisplayName "Escaner TQT 8443" -ErrorAction SilentlyContinue)) {
        if ($PSCmdlet.ShouldProcess("Firewall de Windows", "Crear regla 'Escaner TQT 8443' (TCP 8443 entrante, solo subred local)")) {
            New-NetFirewallRule -DisplayName "Escaner TQT 8443" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
            Write-Host "Regla de firewall creada (TCP 8443, solo red local)." -ForegroundColor Green
        }
    }
} else {
    Write-Warning "No eres administrador: si los celulares no conectan, ejecuta este script como Administrador para abrir el puerto 8443."
}

if ($PSCmdlet.ShouldProcess("docker compose", "up -d --build (imagen escaner-tqt, puerto 8443)")) {
    New-Item -ItemType Directory -Force excel_mensual, exports, certs, respaldos | Out-Null
    # docker compose escribe su progreso en stderr: con "Stop" Windows PowerShell 5.1 lo tomaria por un error y abortaria
    $ErrorActionPreference = "Continue"; docker compose up -d --build; $rc = $LASTEXITCODE; $ErrorActionPreference = "Stop"
    if ($rc -ne 0) { throw "Fallo docker compose (codigo $rc)." }

    Write-Host "`nEsperando a que el servicio responda..." -NoNewline
    $h = ""
    for ($i = 0; $i -lt 30; $i++) {
        try { $h = docker inspect -f "{{.State.Health.Status}}" escaner-tqt 2>$null } catch { $h = "" }
        if ($h -eq "healthy") { break }
        Start-Sleep 2; Write-Host "." -NoNewline
    }
    Write-Host ""
    docker compose ps
    if ($h -ne "healthy") { Write-Warning "El servicio aun no aparece como 'healthy'. Revisa: docker compose logs --tail 50" }
}
Write-Host "`n  Celulares (misma WiFi):  https://${ip}:8443" -ForegroundColor Green
Write-Host "  Monitor en esta PC:      https://${ip}:8443/monitor"
Write-Host "  Administracion:          https://${ip}:8443/admin"
Write-Host "  Sin aviso de sitio no seguro: en esta PC  .\instalar_certificado.ps1 ;  en celulares  https://${ip}:8443/cert  (ver docs\DESPLIEGUE.md)"
Write-Host "  Logs:                    docker compose logs -f`n"
