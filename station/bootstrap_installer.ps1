$ErrorActionPreference = 'Stop'
try {
    $source = [IO.File]::ReadAllText($env:TQT_INSTALLER)
    $payload = ($source -split '::TQT_PAYLOAD::\r?\n', 2)[1].Trim()
    $data = [Convert]::FromBase64String($payload)
    $folder = Join-Path ([IO.Path]::GetTempPath()) ('TQT-Instalar-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $folder | Out-Null
    $zip = Join-Path $folder 'agente.zip'
    [IO.File]::WriteAllBytes($zip, $data)
    Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $folder 'contenido')
    & (Join-Path $folder 'contenido\instalar.ps1')
} catch {
    Write-Host ('No se pudo instalar: ' + $_.Exception.Message)
    exit 1
}
