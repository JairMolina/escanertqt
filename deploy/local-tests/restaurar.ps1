param([Parameter(Mandatory=$true)][string]$BackupPath,[string]$ProjectName='cm-local-tqt-web')
$ErrorActionPreference='Stop'
if($ProjectName -notmatch '^cm-local-tqt-web(-[a-z0-9-]+)?$'){throw 'Usa un nombre de proyecto local TQT independiente.'}
$root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $root
$source=(Resolve-Path -LiteralPath $BackupPath).Path
if(Test-Path -LiteralPath ($source+'-wal')){throw 'Usa un respaldo SQLite completo y cerrado; no una base con WAL pendiente.'}
$docker=Get-Command docker -ErrorAction SilentlyContinue
if(-not $docker){$docker=Get-Item -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')}
$exe=if($docker.Source){$docker.Source}else{$docker.FullName}
& $exe compose -p $ProjectName -f compose.local.yaml build web
if($LASTEXITCODE -ne 0){throw 'Build fallido; no restaurar.'}
& $exe compose -p $ProjectName -f compose.local.yaml create web
if($LASTEXITCODE -ne 0){throw 'No se pudo preparar el volumen local.'}
$image=(& $exe compose -p $ProjectName -f compose.local.yaml config --images | Select-Object -First 1)
$script=@'
import sqlite3,pathlib
p=pathlib.Path('/data/db/tqt_produccion.db')
assert not p.exists(),'La base local ya existe: no se sobrescribe. Usa otro ProjectName para repetir la restauracion.'
a=sqlite3.connect('file:/backup/original.db?mode=ro&immutable=1',uri=True)
assert a.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
count=a.execute('SELECT COUNT(*) FROM tarjetas_produccion').fetchone()[0]
b=sqlite3.connect(p);a.backup(b)
assert b.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert b.execute('SELECT COUNT(*) FROM tarjetas_produccion').fetchone()[0]==count
b.close();a.close();print('Restauracion local validada; original intacto.')
'@
& $exe run --rm --mount ('type=bind,source='+$source+',target=/backup/original.db,readonly') --mount ('type=volume,source='+$ProjectName+'_test_data,target=/data') $image python -c $script
if($LASTEXITCODE -ne 0){throw 'Restauracion fallida; no iniciar la aplicacion.'}
Write-Output 'Copia preparada. Inicia solo este Compose. No se tocaron produccion ni servicios ajenos.'
