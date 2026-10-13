$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.10 o superior.' }
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar pyserial y bleak.' }
$arguments='-u "'+(Join-Path $PSScriptRoot 'agent.py')+'" --config "'+(Join-Path $PSScriptRoot 'config.json')+'" --background'
Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe') -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
Write-Output 'Agente iniciado en segundo plano. Usa la web; diagnostico en agent.log.'
