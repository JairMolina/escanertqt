param(
    [Parameter(Mandatory=$true)][ValidatePattern('^COM[1-9][0-9]*$')][string]$Puerto,
    [ValidateSet(115200,230400,460800,921600)][int]$Baudios=460800,
    [ValidateSet("Manual","Automatico")][string]$Modo="Manual",
    [switch]$Comprobar
)
$ErrorActionPreference='Stop'

function Test-BaseDownloadBootText {
    param([string]$Texto)
    # Solo el mensaje ROM completo; un reset normal o un fragmento no autorizan la grabacion.
    return ($Texto -match '(?m)^boot:0x3\b|(?m)^rst:[^\r\n]*\bboot:0x3\b') -and
        ($Texto -match '(?m)^waiting for download\r?$')
}

function Wait-BaseDownloadBoot {
    param([string]$NombrePuerto)
    $bootPort=New-Object System.IO.Ports.SerialPort $NombrePuerto,115200,([System.IO.Ports.Parity]::None),8,([System.IO.Ports.StopBits]::One)
    $bootPort.DtrEnable=$false
    $bootPort.RtsEnable=$false
    $bootPort.Handshake=[System.IO.Ports.Handshake]::None
    $bootPort.ReadTimeout=250
    try {
        $bootPort.Open()
        # No reutilizar el mensaje que quedo de la tarjeta anterior.
        $bootPort.DiscardInBuffer()
        Write-Host ('Esperando NUEVO BOOT en '+$NombrePuerto+' (115200). Conecta UNA R2 y pulsa BOOT+RESET. Ctrl+C para salir.')
        $bootText=''
        while ($true) {
            try { $bootText += $bootPort.ReadLine()+"`n" }
            catch [System.TimeoutException] { continue }
            if (Test-BaseDownloadBootText $bootText) {
                Write-Host 'DOWNLOAD_BOOT detectado. Comenzando grabacion automaticamente...'
                return
            }
            if ($bootText.Length -gt 8192) { $bootText=$bootText.Substring($bootText.Length-4096) }
        }
    } finally {
        # esptool necesita acceso exclusivo: liberar incluso al cancelar o desconectar el USB.
        if ($bootPort.IsOpen) { $bootPort.Close() }
        $bootPort.Dispose()
    }
}

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
Write-Host ('Base generica 4.0 verificada. Puerto: '+$Puerto+'; velocidad: '+$Baudios+'; modo: '+$Modo)
if ($Comprobar) {Write-Host 'Comprobacion terminada sin abrir el puerto ni grabar hardware.';return}
while ($true) {
    if ($Modo -eq 'Automatico') {
        Wait-BaseDownloadBoot -NombrePuerto $Puerto
    } else {
        $baseAnswer=Read-Host 'Conecta UNA R2 en BOOT+RESET. ENTER para grabar; S para salir'
        if ($baseAnswer -match '^(s|salir)$') {break}
    }
    & $baseTool --chip esp32 --port $Puerto --baud $Baudios --before no-reset --after no-reset write-flash 0x0 $baseImage
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Grabacion y hash verificados. Ya puedes liberar BOOT, reiniciar y cambiar a la siguiente tarjeta.'
    } else {
        Write-Host 'Fallo la grabacion: no se confirma esta tarjeta. Revisa contactos y modo BOOT antes de reintentar.'
        if ($Modo -eq 'Automatico') {
            Write-Host 'La sesion sigue abierta. Corrige los contactos y genera un NUEVO BOOT+RESET para volver a intentar o cambiar de tarjeta.'
            continue
        }
    }
}
