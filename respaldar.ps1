# Copia consistente de la base de datos a .\respaldos (segura con el servicio en marcha, usa la API de backup de SQLite).
# Genera respaldos\tqt_AAAAMMDD_HHMM.db, comprueba su integridad y conserva los ultimos 30 respaldos programados
# (los respaldos automaticos previos a un borrado del admin, tqt_..._<motivo>.db, no se rotan aqui).
# Programar a diario:  schtasks /Create /SC DAILY /ST 18:00 /TN "Respaldo TQT" /TR "powershell -ExecutionPolicy Bypass -File C:\EscanerTQT\respaldar.ps1"
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force respaldos | Out-Null

# El codigo Python viaja por stdin: Windows PowerShell 5.1 elimina las comillas dobles de los argumentos de programas
# nativos, y con "python -c <codigo>" el codigo llegaba roto (SyntaxError).
$py = @'
import sqlite3, datetime, os, glob, re
dst = "/backups/tqt_" + datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".db"
src = sqlite3.connect(os.environ["TQT_DB_PATH"])
out = sqlite3.connect(dst)
src.backup(out)
estado = out.execute("PRAGMA integrity_check").fetchone()[0]
out.close(); src.close()
if estado != "ok":
    os.remove(dst)
    raise SystemExit("Respaldo descartado: integrity_check = " + str(estado))
programados = sorted(f for f in glob.glob("/backups/tqt_*.db") if re.search(r"tqt_\d{8}_\d{4}\.db$", f))
for f in programados[:-30]:
    os.remove(f)
print("OK", dst, "(" + str(min(len(programados), 30)) + " respaldos programados conservados)")
'@
$py | docker compose exec -T tqt python -
if ($LASTEXITCODE -ne 0) { Write-Error "El respaldo fallo (codigo $LASTEXITCODE). Comprueba 'docker compose ps'."; exit 1 }
