$ErrorActionPreference = 'Stop'
$cfg = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw | ConvertFrom-Json
if ($cfg.station_id -notmatch '^[a-f0-9]{24}$') { throw 'Estacion invalida.' }
$python = $null
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $python = & $py.Source -3 -c 'import sys; print(sys.executable)' 2>$null }
if (-not $python) {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Source -notmatch 'WindowsApps') { $python = $candidate.Source }
}
if (-not $python) { throw 'Se necesita Python 3.10 o superior. Instala Python desde python.org y vuelve a ejecutar este instalador.' }
$python = [string]$python
& $python -c 'import sys; assert sys.version_info >= (3,10)'
if ($LASTEXITCODE -ne 0) { throw 'Se necesita Python 3.10 o superior.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $python -c 'import agent; print(agent.find_jlink())'
    if ($LASTEXITCODE -ne 0) { throw 'No se encontro J-Link. Instala SEGGER J-Link o STM32CubeIDE y vuelve a ejecutar el instalador.' }
} finally { Pop-Location }
$destination = Join-Path $env:LOCALAPPDATA ('TQT\STM32Agent\' + $cfg.station_id)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
foreach ($name in @('agent.py','tqt_hex.py','config.json','iniciar.ps1','iniciar.cmd','LEEME.txt','instalar.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $destination $name) -Force
}
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'ca.crt')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ca.crt') -Destination (Join-Path $destination 'ca.crt') -Force
}
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'No se encontro pythonw.exe en la instalacion de Python.' }
$agentPath = Join-Path $destination 'agent.py'
$configPath = Join-Path $destination 'config.json'
$arguments = '-u "' + $agentPath + '" --config "' + $configPath + '" --background'
$startup = [Environment]::GetFolderPath('Startup')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $startup ('TQT STM32 ' + $cfg.station_id + '.lnk')))
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $destination
$shortcut.WindowStyle = 7
$shortcut.Description = 'Agente TQT STM32: programacion desde la web'
$shortcut.Save()
Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $destination -WindowStyle Hidden
Write-Output 'Instalado. El agente funciona en segundo plano y se inicia con Windows.'
Write-Output 'Vuelve a la web, elige esta laptop y programa con el boton de la R1.'
