"""Uso único (v1.4.15): carga los activos de un Excel de inventario en la BD configurada (TQT_DB_PATH).

    python scripts/importar_activos_excel.py "ACTIVOS SKYGUARDIAN x.xlsx"               # solo vista previa
    python scripts/importar_activos_excel.py "ACTIVOS SKYGUARDIAN x.xlsx" --aplicar     # escribe en la BD
    python scripts/importar_activos_excel.py archivo.xlsx --todas-las-filas --aplicar   # también las filas sin verde

Con Docker: copia el libro al contenedor y ejecútalo con `docker exec` desde /app. Es idempotente: volver a correrlo
actualiza por número de activo en lugar de duplicar.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import db  # noqa: E402
from app.services import activos_import  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Importa activos desde el Excel de inventario.")
    p.add_argument("xlsx", help="ruta del libro .xlsx")
    p.add_argument("--aplicar", action="store_true", help="escribir en la BD (sin esto solo muestra la vista previa)")
    p.add_argument("--todas-las-filas", action="store_true", help="no limitarse a las filas en verde")
    p.add_argument("--por", default="importacion@script", help="usuario que queda en la bitácora")
    a = p.parse_args()
    ruta = Path(a.xlsx)
    if not ruta.is_file():
        print(f"No existe el archivo: {ruta}", file=sys.stderr)
        return 2
    db.init_db()
    try:
        r = activos_import.analizar(ruta.read_bytes(), solo_verdes=not a.todas_las_filas)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for h in r["hojas"]:
        print(f"{h['hoja']:<10} {h['formato']:<10} verdes={h['filas_verdes']:<4} nuevos={h['nuevos']:<4} "
              f"actualizar={h['actualizar']:<4} omitidos={len(h['omitidos'])}")
        for o in h["omitidos"][:5]:
            print(f"    fila {o['fila']}: {o['motivo']}")
    for av in r["avisos"]:
        print(f"Aviso: {av['codigo']} repetido; gana {av['gana']} (descartada {av['descartada']})")
    t = r["totales"]
    print(f"Total: {t['nuevos']} nuevos, {t['actualizar']} por actualizar, {t['omitidos']} omitidos")
    if not a.aplicar:
        print("Vista previa: no se escribió nada. Usa --aplicar para cargar.")
        return 0
    res = activos_import.aplicar(r["items"], a.por)
    print(f"Aplicado: {res['creados']} creados, {res['actualizados']} actualizados, {res['sin_cambios']} sin cambios, "
          f"{len(res['errores'])} con error (lote {res['lote']}).")
    for e in res["errores"][:10]:
        print(f"    {e['codigo']}: {e['detail']}")
    return 1 if res["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
