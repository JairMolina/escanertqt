# Prueba sin COM ni grabacion; compatible con Windows PowerShell 5.1.
$ErrorActionPreference='Stop'
$source=Join-Path $PSScriptRoot '../firmware/esp32_r2/TQT_R2_BASE_V4_0_GENERIC/programar_base.ps1'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Test-BaseDownloadBootText'},$true)
Invoke-Expression $fn.Extent.Text
$rom="ets Jul 29 2019 12:21:46`r`n`r`nrst:0x1 (POWERON_RESET),boot:0x3 (DOWNLOAD_BOOT(UART0/UART1/SDIO_REI_REO_V2))`r`nwaiting for download`r`n"
$cases=@(
    @{Text=$rom; Expected=$true},
    @{Text=$rom.Replace("`r",''); Expected=$true},
    @{Text=''; Expected=$false},
    @{Text="waiting for download`r`n"; Expected=$false},
    @{Text=$rom.Replace('boot:0x3','boot:0x13'); Expected=$false},
    @{Text=$rom.Replace('waiting for download','waiting for down'); Expected=$false},
    @{Text=$rom.Replace('boot:0x3','boot:0x30'); Expected=$false},
    @{Text="rst:0x1,boot:0x3 (DOWNLOAD_BOOT)`n"; Expected=$false}
)
foreach ($case in $cases) {
    if ((Test-BaseDownloadBootText $case.Text) -ne $case.Expected) {throw 'Clasificacion de BOOT incorrecta.'}
}
# La deteccion no se dispara hasta completar la ultima linea, incluso al recibir fragmentos.
$buffer=''; $triggered=0
foreach ($line in ($rom -split "`n")) {
    $buffer += $line+"`n"
    if (Test-BaseDownloadBootText $buffer) { $triggered++; break }
}
if ($triggered -ne 1) {throw 'No detecto el arranque completo.'}
$all=Get-Content -LiteralPath $source -Raw
if ($all.IndexOf('if ($Comprobar)') -gt $all.IndexOf('while ($true) {', $all.IndexOf('if ($Comprobar)'))) {throw 'Comprobar no protege la entrada al bucle.'}
if ($all -notmatch '\[ValidateSet\("Manual","Automatico"\)\]\[string\]\$Modo="Manual"') {throw 'Se debe conservar Manual predeterminado.'}
Write-Host 'PASS: sintaxis PowerShell, 8 casos BOOT, flujo fragmentado y modo manual predeterminado; sin hardware.'

# Ejecutar solo el bucle principal con esptool y BOOT simulados: fallo -> nueva espera -> exito.
$loop=$ast.EndBlock.Statements | Where-Object {$_ -is [System.Management.Automation.Language.WhileStatementAst]} | Select-Object -Last 1
$script:bootCalls=0; $script:flashCalls=0; $script:flow=@()
function Wait-BaseDownloadBoot {
    param([string]$NombrePuerto)
    $script:bootCalls++; $script:flow+='BOOT'
    if ($script:bootCalls -eq 3) {throw 'FIN_SIMULACION'}
}
function Invoke-FakeBaseTool {
    $script:flashCalls++; $script:flow+='FLASH'
    $global:LASTEXITCODE=0
    if ($script:flashCalls -eq 1) {$global:LASTEXITCODE=2}
}
$Modo='Automatico'; $Puerto='COM-FAKE'; $baseTool='Invoke-FakeBaseTool'; $Baudios=460800; $baseImage='NO-IMAGE'
try {
    Invoke-Expression $loop.Extent.Text
    throw 'El bucle termino antes de completar la simulacion.'
} catch {
    if ($_.Exception.Message -ne 'FIN_SIMULACION') {throw}
}
if ($script:flashCalls -ne 2 -or ($script:flow -join ',') -ne 'BOOT,FLASH,BOOT,FLASH,BOOT') {
    throw 'Tras fallo debe esperar otro BOOT antes de volver a escribir.'
}
Write-Host 'PASS: fallo simulado no cierra sesion; exige nuevo BOOT, graba siguiente y vuelve a esperar. Sin hardware.'
