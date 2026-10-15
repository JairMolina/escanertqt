param(
    [Parameter(Mandatory=$true)][ValidatePattern('^COM[1-9][0-9]*$')][string]$Puerto,
    [ValidateSet(115200,230400,460800,921600)][int]$Baudios=460800,
    [switch]$Comprobar
)
$ErrorActionPreference='Stop'
$baseParent=Split-Path $PSScriptRoot -Parent
$baseCandidates=@((Join-Path $baseParent 'BASE_GENERAL_4_0.bin'),(Join-Path $baseParent 'TQT_R2_BASE_V4_0_GENERIC.merged.bin'))
$baseImage=$baseCandidates | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
if (-not $baseImage) {throw 'No se encontro el BIN fijo de la base 4.0 junto a la carpeta del codigo.'}
$baseHash='05f89f68497bf92cbe4bc80dee9c4d101e59fc22202d8e2d5e2945035f14a487'
if ((Get-FileHash -LiteralPath $baseImage -Algorithm SHA256).Hash.ToLower() -ne $baseHash) {throw 'El BIN cambio; no se graba una base distinta a la verificada.'}
$baseTools=Join-Path $env:USERPROFILE 'AppData\Local\Arduino15\packages\esp32\tools\esptool_py'
$baseTool=Get-ChildItem -LiteralPath $baseTools -Directory | Sort-Object {[version]$_.Name} -Descending |
    ForEach-Object {Join-Path $_.FullName 'esptool.exe'} | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
if (-not $baseTool) {throw 'Falta esptool; instala las herramientas ESP32 de Arduino antes de trabajar offline.'}
Write-Host ('Base generica 4.0 verificada. Puerto: '+$Puerto+'; velocidad: '+$Baudios)
if ($Comprobar) {Write-Host 'Comprobacion terminada sin abrir el puerto ni grabar hardware.';return}
while ($true) {
    $baseAnswer=Read-Host 'Conecta UNA R2 en BOOT+RESET. ENTER para grabar; S para salir'
    if ($baseAnswer -match '^(s|salir)$') {break}
    & $baseTool --chip esp32 --port $Puerto --baud $Baudios --before no-reset --after no-reset write-flash 0x0 $baseImage
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Grabacion y hash verificados. Ya puedes liberar BOOT, reiniciar y cambiar a la siguiente tarjeta.'
    } else {
        Write-Host 'Fallo la grabacion: no se confirma esta tarjeta. Revisa contactos y modo BOOT antes de reintentar.'
    }
}
