param([string]$Nombre,[string]$Hardware,[string]$Firmware,[string]$Identidad)
$ErrorActionPreference='Stop'
$localPyCandidates=@(
    (Join-Path $env:USERPROFILE 'AppData\Local\Python\pythoncore-3.14-64\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$localPython=$localPyCandidates | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
if (-not $localPython) {throw 'Instala Python antes de trabajar offline.'}
$localArgs=@((Join-Path $PSScriptRoot 'preparar_local.py'))
if ($Nombre) {$localArgs+=@('--nombre',$Nombre)}
if ($Hardware) {$localArgs+=@('--hw',$Hardware)}
if ($Firmware) {$localArgs+=@('--fw',$Firmware)}
if ($Identidad) {$localArgs+=@('--identity-file',$Identidad)}
$localStore=Join-Path $env:USERPROFILE '.tqt\R2'
New-Item -ItemType Directory -Path $localStore -Force | Out-Null
$localLock=[IO.File]::Open((Join-Path $localStore 'compilar.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    $localResult=& $localPython @localArgs
    if ($LASTEXITCODE -ne 0) {throw 'No se preparo la identidad local.'}
    $localPrepared=$localResult | ConvertFrom-Json
    Write-Host ('Proyecto privado: '+$localPrepared.project)
    Write-Host ('Identidad: '+$localPrepared.identity_file)
    if (-not $localPrepared.web_registered) {
        Write-Host 'Credencial creada offline: conserva su JSON; debe registrarse en el servidor antes de usar OTA desde la web.'
    }
    & (Join-Path $localPrepared.project 'compilar.ps1')
    $localSketch=Split-Path $localPrepared.project -Leaf
    $localBin=Join-Path $localPrepared.project ('build\'+$localSketch+'.ino.merged.bin')
    $localHex=Join-Path $localPrepared.project ('build\'+$localSketch+'.hex')
    if (-not (Test-Path -LiteralPath $localBin) -or -not (Test-Path -LiteralPath $localHex)) {throw 'Faltan los archivos compilados.'}
    $localArchive=Join-Path $localStore ('firmwares\'+$localPrepared.nombre+'\FW-'+$localPrepared.fw)
    New-Item -ItemType Directory -Path $localArchive -Force | Out-Null
    Copy-Item -LiteralPath $localBin -Destination (Join-Path $localArchive ($localPrepared.nombre+'.bin')) -Force
    Copy-Item -LiteralPath $localHex -Destination (Join-Path $localArchive ($localPrepared.nombre+'.hex')) -Force
    $localPrepared | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $localArchive 'preparacion.json') -Encoding utf8
    Write-Host ('Firmware personalizado listo para USB en: '+$localArchive)
} finally {$localLock.Dispose()}
