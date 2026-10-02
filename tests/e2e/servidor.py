"""Arranca un servidor TQT aislado (carpetas temporales) para las pruebas de navegador.
Uso: python tests/e2e/servidor.py [puerto=8457] [carpeta_tmp]   (Ctrl+C para parar)
"""
import os, subprocess, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
puerto = sys.argv[1] if len(sys.argv) > 1 else "8457"
tmp = Path(sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="tqt_e2e_"))
env = dict(os.environ, TQT_DB_PATH=str(tmp / "x.db"), TQT_EXCEL_DIR=str(tmp / "xl"), TQT_EXPORTS_DIR=str(tmp / "ex"),
           TQT_BACKUP_DIR=str(tmp / "bk"), TQT_ADMIN_PASSWORD="ClaveQA-12345", HTTPS_PORT=puerto, TQT_HOST_IP="127.0.0.1")
print("tmp:", tmp, flush=True)
sys.exit(subprocess.call([sys.executable, "run_server.py"], cwd=RAIZ, env=env))
