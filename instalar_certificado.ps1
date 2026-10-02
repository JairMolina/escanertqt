<#
  Instala la autoridad certificadora LOCAL de Escaner TQT como confiable en ESTA PC.
  Después, Chrome/Edge abren https://<IP>:8443 con candado, sin el aviso de "sitio no seguro".
  Se hace una sola vez por PC: el certificado del servidor se renueva solo y sigue siendo válido aunque cambie la IP.

  Uso:  .\instalar_certificado.ps1           (como Administrador: para todos los usuarios de la PC)
        .\instalar_certificado.ps1 -SoloUsuario   (sin Administrador: solo para tu usuario)
        .\instalar_certificado.ps1 -Quitar        (la desinstala)
  Los celulares: abre https://<IP>:8443/cert y sigue docs\DESPLIEGUE.md
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$SoloUsuario, [switch]$Quitar)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ca = Join-Path $PSScriptRoot "certs\ca.pem"
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$almacen = if ($esAdmin -and -not $SoloUsuario) { "Cert:\LocalMachine\Root" } else { "Cert:\CurrentUser\Root" }

if ($Quitar) {
    $viejos = Get-ChildItem $almacen | Where-Object { $_.Subject -like "*Escaner TQT Local CA*" }
    foreach ($c in $viejos) { if ($PSCmdlet.ShouldProcess($c.Thumbprint, "Quitar de $almacen")) { Remove-Item $c.PSPath } }
    Write-Host "Autoridad de Escaner TQT quitada de $almacen ($($viejos.Count))." -ForegroundColor Yellow
    return
}

if (-not (Test-Path $ca)) {
    throw "No existe certs\ca.pem. Arranca el servidor una vez (.\desplegar.ps1 o python run_server.py) para que se genere, y vuelve a ejecutar esto."
}
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ca
if ($cert.Subject -notlike "*Escaner TQT Local CA*") { throw "certs\ca.pem no es la autoridad de Escaner TQT." }

$ya = Get-ChildItem $almacen | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
if ($ya) { Write-Host "La autoridad ya estaba instalada en $almacen." -ForegroundColor Green; return }

if ($PSCmdlet.ShouldProcess($almacen, "Instalar la autoridad 'Escaner TQT Local CA' (huella $($cert.Thumbprint))")) {
    Import-Certificate -FilePath $ca -CertStoreLocation $almacen | Out-Null
    Write-Host "Autoridad instalada en $almacen." -ForegroundColor Green
    Write-Host "Cierra y vuelve a abrir el navegador. Huella: $($cert.Thumbprint)"
    if ($almacen -like "*CurrentUser*") { Write-Host "(Solo para tu usuario. Como Administrador se instala para todos.)" }
}
