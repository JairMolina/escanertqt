param([int]$Puerto = 8463, [string]$Tmp = "")
# Reinicia el servidor aislado de pruebas de Movimientos con una BD nueva (solo toca el puerto indicado).
$c = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
if ($c) { Stop-Process -Id $c.OwningProcess -Force; Start-Sleep -Seconds 1 }
if (-not $Tmp) { $Tmp = Join-Path $env:TEMP ("tqt_mov_" + [guid]::NewGuid().ToString("N").Substring(0, 8)) }
New-Item -ItemType Directory -Force $Tmp | Out-Null
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Start-Process -FilePath python -ArgumentList "tests/e2e/servidor.py", $Puerto, $Tmp -WorkingDirectory $raiz -WindowStyle Hidden
Start-Sleep -Seconds 6
Write-Output "servidor en $Puerto, tmp $Tmp"
