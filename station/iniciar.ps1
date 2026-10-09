$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$tqtPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $tqtPython) { & $tqtPython agent.py; exit $LASTEXITCODE }
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 agent.py; exit $LASTEXITCODE }
if (Get-Command python -ErrorAction SilentlyContinue) { & python agent.py; exit $LASTEXITCODE }
throw 'Instala Python 3.10 o superior y vuelve a ejecutar iniciar.cmd.'
