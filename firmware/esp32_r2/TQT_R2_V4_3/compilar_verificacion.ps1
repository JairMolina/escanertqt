param(
    [string]$Cli='C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe',
    [string]$ArduinoData='C:\Users\LEO\AppData\Local\Arduino15',
    [string]$Output='',
    [int]$CompileJobs=3
)
$ErrorActionPreference='Stop'
if (-not $Output) { $Output=Join-Path $PSScriptRoot '../../../privado/fw43-build' }
$Output=[IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path $Output -Force | Out-Null
if (-not (Test-Path -LiteralPath $Cli)) {throw 'Arduino CLI no encontrado.'}
$core=Join-Path $ArduinoData 'packages/esp32/hardware/esp32/3.3.11'
if (-not (Test-Path -LiteralPath $core)) {throw 'Verificacion reproducible requiere esp32:esp32 3.3.11; no instala ni cambia el core global.'}
$config=Join-Path $Output 'arduino-cli.yaml'
$settings=@{
    directories=@{data=$ArduinoData;downloads=(Join-Path $Output 'downloads');user=(Join-Path $Output 'sketchbook')}
    build_cache=@{path=(Join-Path $Output 'cache')}
}
$settings | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $config -Encoding utf8
$build=Join-Path $Output 'build'
$artifacts=Join-Path $Output 'artifacts'
$tools=Join-Path $ArduinoData 'packages/esp32/tools/esp-x32'
$toolchain=Get-ChildItem -LiteralPath $tools -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $toolchain) {throw 'Toolchain ESP32 no encontrado.'}
# Verification only: the template key is zero and must not be programmed.
& $Cli --config-file $config compile --fqbn 'esp32:esp32:esp32doit-devkit-v1' --jobs $CompileJobs `
    --build-property ('runtime.tools.esp-x32.path='+$toolchain.FullName) `
    --build-path $build --output-dir $artifacts $PSScriptRoot
if ($LASTEXITCODE -ne 0) {throw 'La compilacion FW4.3 fallo.'}
$binary=Join-Path $artifacts 'TQT_R2_V4_3.ino.bin'
if (-not (Test-Path -LiteralPath $binary)) {throw 'No se genero el app BIN.'}
$bytes=[IO.File]::ReadAllBytes($binary)
if (-not [Text.Encoding]::ASCII.GetString($bytes).Contains('TQT_OFFLINE_V1_P256')) {throw 'Falta marcador offline en el app BIN.'}
Get-FileHash -Algorithm SHA256 -LiteralPath $binary
Write-Host 'Compilacion verificada; plantilla sin identidad, NO apta para grabar. No se accedio a hardware.'
