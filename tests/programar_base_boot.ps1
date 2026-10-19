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
