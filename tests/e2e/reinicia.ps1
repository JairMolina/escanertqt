# Uso: powershell -NoProfile -File tests/e2e/reinicia.ps1 -Tmp <carpeta> [-Puerto 8457] [-Keep]
# Mata el servidor del puerto y arranca uno nuevo (BD limpia salvo -Keep), desacoplado de la consola.
param([Parameter(Mandatory=$true)][string]$Tmp, [string]$Puerto = "8457", [switch]$Keep)
Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-Sleep 1
if (-not $Keep) { if (Test-Path $Tmp) { Remove-Item -Recurse -Force $Tmp } }
New-Item -ItemType Directory -Force $Tmp | Out-Null
$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Start-Process -FilePath python -ArgumentList "tests/e2e/servidor.py",$Puerto,$Tmp -WorkingDirectory $raiz -WindowStyle Hidden -RedirectStandardOutput "$Tmp.log" -RedirectStandardError "$Tmp.err.log"
for ($i=0; $i -lt 30; $i++) { Start-Sleep 1; if (Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue) { "listo"; break } }
