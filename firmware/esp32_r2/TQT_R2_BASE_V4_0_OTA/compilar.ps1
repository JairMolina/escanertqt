$ErrorActionPreference = 'Stop'
$sketch = $PSScriptRoot
$files = @(Get-ChildItem -LiteralPath $sketch -Filter '*.ino')
if ($files.Count -ne 1 -or $files[0].BaseName -ne (Split-Path $sketch -Leaf)) {
    throw 'Arduino requiere un unico .ino con el mismo nombre de su carpeta.'
}
$cliCandidates = @(
    'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe',
    (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe')
)
$cli = $cliCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $cli) { throw 'No se encontro Arduino CLI. Instala Arduino IDE y el core esp32:esp32.' }
$config = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.arduinoIDE\arduino-cli.yaml'
$cliArgs = @()
if (Test-Path -LiteralPath $config) { $cliArgs += @('--config-file', $config) }
$build = Join-Path $sketch 'build'
& $cli @cliArgs compile --fqbn 'esp32:esp32:esp32doit-devkit-v1' --output-dir $build $sketch
if ($LASTEXITCODE -ne 0) { throw 'La compilacion fallo. No se exporto HEX.' }
$merged = Join-Path $build ($files[0].Name + '.merged.bin')
if (-not (Test-Path -LiteralPath $merged)) { throw 'Falta el binario completo merged.bin.' }
$tools = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Arduino15\packages\esp32\tools\esptool_py'
$tool = Get-ChildItem -LiteralPath $tools -Directory |
    Sort-Object { [version]$_.Name } -Descending |
    ForEach-Object { Join-Path $_.FullName 'esptool.exe' } |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $tool) { throw 'Se genero BIN, pero no se encontro esptool.exe para exportar HEX.' }
$hex = Join-Path $build ($files[0].BaseName + '.hex')
& $tool --chip esp32 merge-bin --format hex -o $hex 0x0 $merged
if ($LASTEXITCODE -ne 0) { throw 'Fallo la conversion Intel HEX.' }
Write-Host "Listos para subir a Programacion > R2:"
Write-Host $merged
Write-Host $hex
Write-Host 'Nombre 0000 es plantilla: la web coloca el nombre real de la R2 elegida.'
