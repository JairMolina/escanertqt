param([ValidateSet('iniciar','detener','estado','validar')][string]$Accion='estado')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $root
$docker=Get-Command docker -ErrorAction SilentlyContinue
if(-not $docker){$docker=Get-Item -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')}
$exe=if($docker.Source){$docker.Source}else{$docker.FullName}
$base=@('compose','-p','cm-local-tqt-web','-f','compose.local.yaml')
switch($Accion){
 'iniciar' {& $exe @base up -d --build web}
 'detener' {& $exe @base stop web}
 'estado' {& $exe @base ps}
 'validar' {& $exe @base config --quiet;if($LASTEXITCODE -ne 0){throw 'Compose invalido'};& $exe @base ps;Invoke-RestMethod 'http://127.0.0.1:18080/api/health'}
}
if($LASTEXITCODE -ne 0){throw 'Docker devolvio un error.'}
