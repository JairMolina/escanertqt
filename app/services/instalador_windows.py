"""v1.4.64: instalador .cmd autoextraíble del agente/puente Bluetooth de Windows (sin descomprimir).

El .cmd lleva un script PowerShell entre marcadores y, al final, el ZIP del agente en base64. Al abrirlo con
doble clic: detiene el agente previo de la misma estación, extrae en %LOCALAPPDATA%\\TQT\\..., conserva .venv,
instala Python con winget si falta, pip, acceso directo en Inicio y arranca oculto. El token solo va en config.json.
"""
import base64

MARCA_PS_INICIO = "::TQT_PS_INICIO"
MARCA_PS_FIN = "::TQT_PS_FIN"
MARCA_ZIP = "::TQT_ZIP_BASE64"

# v1.4.64: se instala en segundo plano. El .cmd lanza PowerShell oculto y se cierra al instante (puede verse un
# parpadeo); el avance se ve en la página (install-progress) y un error sale además en un aviso de Windows.
_CABECERA = r"""@echo off
setlocal
set "TQT_CMD=%~f0"
start "" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:TQT_CMD,[Text.Encoding]::UTF8);$m='::TQT_PS'+'_INICIO';$a=$t.IndexOf($m)+$m.Length;$b=$t.IndexOf('::TQT_PS'+'_FIN');Invoke-Expression $t.Substring($a,$b-$a)"
exit /b 0
"""

# Todo lo que sigue a «exit /b» lo ignora cmd.exe; solo lo lee PowerShell.
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$Id = '__ID__'
$Nombre = '__NOMBRE__'
$Dest = Join-Path $env:LOCALAPPDATA '__CARPETA__'
$Final = '__FINAL__'

$Cfg = $null
function Avance([string]$Etapa, [string]$Mensaje = '') {
    # Reporta a la página con el token del config.json ya extraído; si falla (sin red, certificado) se sigue igual.
    if (-not $Cfg) { return }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $cuerpo = @{ etapa = $Etapa; mensaje = $Mensaje } | ConvertTo-Json -Compress
        Invoke-RestMethod -Method Post -Uri ($Cfg.server.TrimEnd('/') + '/api/stm32/agent/tests/install-progress') -TimeoutSec 8 `
            -Headers @{ Authorization = ('Bearer ' + $Cfg.token) } -ContentType 'application/json; charset=utf-8' `
            -Body ([Text.Encoding]::UTF8.GetBytes($cuerpo)) | Out-Null
    } catch { }
}
function Aviso([string]$Texto) {
    try { Add-Type -AssemblyName System.Windows.Forms; [void][System.Windows.Forms.MessageBox]::Show($Texto, 'Instalador TQT', 'OK', 'Error') } catch { }
}

function Ejecutar([string]$Exe, [string[]]$Argumentos) {
    $ErrorActionPreference = 'Continue'
    & $Exe @Argumentos | Out-Host
    return $LASTEXITCODE
}

function Buscar-Python {
    $c = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $c += ,@('py', '-3') }
    if (Get-Command python -ErrorAction SilentlyContinue) { $c += ,@('python') }
    foreach ($v in '313', '312', '311', '310') {
        $p = Join-Path $env:LOCALAPPDATA ('Programs\Python\Python' + $v + '\python.exe')
        if (Test-Path -LiteralPath $p) { $c += ,@($p) }
    }
    foreach ($x in $c) {
        $pre = @($x | Select-Object -Skip 1)
        try {
            $ErrorActionPreference = 'Continue'
            $r = & $x[0] @pre -c 'import sys; print(int(sys.version_info >= (3, 10)))' 2>$null
            if ("$r".Trim() -eq '1') { return ,$x }
        } catch { }
    }
    return $null
}

function Detener-Previo {
    # Agente previo de esta carpeta o de esta misma estación (otra carpeta con el mismo id): su token ya rotó.
    $procs = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue)
    foreach ($p in $procs) {
        $cl = [string]$p.CommandLine
        if (-not $cl -or $cl.IndexOf('agent.py', [StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
        $mismo = $cl.IndexOf($Dest, [StringComparison]::OrdinalIgnoreCase) -ge 0
        if (-not $mismo) {
            $m = [regex]::Match($cl, '--config\s+"?([^"]+?\.json)"?')
            if ($m.Success -and (Test-Path -LiteralPath $m.Groups[1].Value)) {
                try { $mismo = ((Get-Content -LiteralPath $m.Groups[1].Value -Raw | ConvertFrom-Json).id -eq $Id) } catch { }
            }
        }
        if ($mismo) {
            Write-Host ('Deteniendo el ' + $Nombre + ' anterior (proceso ' + $p.ProcessId + ')...')
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
}

try {
    Write-Host ('Instalando ' + $Nombre + ' de TQT en ' + $Dest)
    Detener-Previo

    $texto = [IO.File]::ReadAllText($env:TQT_CMD, [Text.Encoding]::UTF8)
    $marca = '::TQT_' + 'ZIP_BASE64'
    $i = $texto.LastIndexOf($marca)
    if ($i -lt 0) { throw 'El instalador está incompleto; descárgalo de nuevo desde la web.' }
    $bytes = [Convert]::FromBase64String(($texto.Substring($i + $marca.Length) -replace '[^A-Za-z0-9+/=]', ''))
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    $viejo = Join-Path $Dest 'tqtstation'
    if (Test-Path -LiteralPath $viejo) { Remove-Item -LiteralPath $viejo -Recurse -Force }
    $tmp = Join-Path $env:TEMP ('tqt_' + [guid]::NewGuid().ToString('N') + '.zip')
    [IO.File]::WriteAllBytes($tmp, $bytes)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($tmp)
    try {
        foreach ($e in $zip.Entries) {
            if (-not $e.Name) { continue }
            $out = Join-Path $Dest ($e.FullName -replace '/', '\')
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $out, $true)
        }
    } finally {
        $zip.Dispose()
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
    try { $Cfg = Get-Content -LiteralPath (Join-Path $Dest 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $Cfg = $null }
    Avance 'extrayendo' 'Archivos copiados'

    $venvPy = Join-Path $Dest '.venv\Scripts\python.exe'
    $venvPyw = Join-Path $Dest '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $venvPy)) {
        $py = Buscar-Python
        Avance 'python' 'Preparando Python'
        if (-not $py -and (Get-Command winget -ErrorAction SilentlyContinue)) {
            Write-Host 'Python no está instalado; instalando Python 3.12 con winget (puede tardar unos minutos)...'
            Ejecutar 'winget' @('install', '-e', '--id', 'Python.Python.3.12', '--silent', '--accept-package-agreements', '--accept-source-agreements') | Out-Null
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
            $py = Buscar-Python
        }
        if (-not $py) {
            throw 'No se encontró Python 3.10 o superior. Instálalo desde https://www.python.org/downloads/ (marca «Add python.exe to PATH») y vuelve a abrir este instalador.'
        }
        Write-Host 'Creando el entorno de Python...'
        $pre = @($py | Select-Object -Skip 1)
        $code = Ejecutar $py[0] ($pre + @('-m', 'venv', (Join-Path $Dest '.venv')))
        if ($code -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) { throw 'No se pudo crear el entorno de Python.' }
    }
    Avance 'dependencias' 'Instalando bleak y pyserial'
    Write-Host 'Instalando dependencias (bleak, pyserial)...'
    $code = Ejecutar $venvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', (Join-Path $Dest 'requirements.txt'))
    if ($code -ne 0) { throw 'No se pudieron instalar las dependencias. Revisa la conexión a internet y vuelve a abrir el instalador.' }
    if (-not (Test-Path -LiteralPath $venvPyw)) { $venvPyw = $venvPy }

    $argumentos = '-u "' + (Join-Path $Dest 'agent.py') + '" --config "' + (Join-Path $Dest 'config.json') + '" --background'
    $inicio = [Environment]::GetFolderPath('Startup')
    if ($inicio) {
        $ws = New-Object -ComObject WScript.Shell
        $lnk = $ws.CreateShortcut((Join-Path $inicio ('TQT ' + $Nombre + '.lnk')))
        $lnk.TargetPath = $venvPyw
        $lnk.Arguments = $argumentos
        $lnk.WorkingDirectory = $Dest
        $lnk.WindowStyle = 7
        $lnk.Description = 'Arranca oculto el ' + $Nombre + ' de TQT al iniciar sesión'
        $lnk.Save()
    }

    Avance 'arrancando' 'Arrancando el agente'
    Start-Process -FilePath $venvPyw -ArgumentList $argumentos -WorkingDirectory $Dest -WindowStyle Hidden
    Start-Sleep -Seconds 4
    $vivo = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { ([string]$_.CommandLine).IndexOf($Dest, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
    if ($vivo.Count -eq 0) {
        $log = Join-Path $Dest 'agent.log'
        if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 15 | Out-Host }
        throw ('El ' + $Nombre + ' no quedó en marcha; revisa ' + $log)
    }
    Write-Host ''
    Write-Host $Final -ForegroundColor Green
    Avance 'listo' $Final
    exit 0
} catch {
    Write-Host ''
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Avance 'error' $_.Exception.Message
    Aviso ('No se pudo instalar el ' + $Nombre + ' de TQT:' + [Environment]::NewLine + [Environment]::NewLine + $_.Exception.Message)
    exit 1
}
"""


def construir(zip_bytes, station_id, ble_only):
    """Devuelve (nombre_archivo, bytes) del .cmd con CRLF. No incluye el token fuera del ZIP (config.json)."""
    if ble_only:
        nombre, carpeta, archivo = "Puente Bluetooth", r"TQT\PuenteBluetooth", "TQT_Puente_Bluetooth.cmd"
        final = "Puente Bluetooth instalado y en marcha."
    else:
        nombre, carpeta, archivo = "Agente de pruebas", r"TQT\AgentePruebas", "TQT_Agente_Pruebas.cmd"
        final = "Agente de pruebas instalado y en marcha."
    sid = "".join(ch for ch in str(station_id) if ch.isalnum())
    script = (_SCRIPT.replace("__ID__", sid).replace("__NOMBRE__", nombre)
              .replace("__CARPETA__", carpeta).replace("__FINAL__", final))
    b64 = base64.b64encode(zip_bytes).decode("ascii")
    lineas = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    texto = (_CABECERA.replace("__NOMBRE__", nombre) + MARCA_PS_INICIO + "\n" + script.strip("\n") + "\n"
             + MARCA_PS_FIN + "\n" + MARCA_ZIP + "\n" + "\n".join(lineas) + "\n")
    texto = texto.replace("\r\n", "\n").replace("\n", "\r\n")
    return archivo, texto.encode("utf-8")


def extraer_zip(cmd_bytes):
    """Para pruebas: recupera el ZIP embebido tal como lo hace el script PowerShell."""
    texto = cmd_bytes.decode("utf-8")
    i = texto.rindex(MARCA_ZIP)
    return base64.b64decode("".join(ch for ch in texto[i + len(MARCA_ZIP):] if ch.isalnum() or ch in "+/="))


def script_ps(cmd_bytes):
    texto = cmd_bytes.decode("utf-8")
    a = texto.index(MARCA_PS_INICIO) + len(MARCA_PS_INICIO)
    return texto[a:texto.index(MARCA_PS_FIN)]

