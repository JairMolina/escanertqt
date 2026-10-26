"""v1.4.39: genera docs/manual/*.md desde las guías del manual (app/static/documentacion/guias/*.json).

Las guías JSON son la fuente; los .md son su copia legible en GitHub. Correr después de agregar, editar o borrar una guía:
    python scripts/generar_manual_md.py           # escribe y borra los .md que sobran
    python scripts/generar_manual_md.py --check   # solo revisa (sale con 1 si algo está desactualizado)
tests/test_manual_guias.py usa el modo --check, así que la suite avisa si se olvida.
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOC = RAIZ / "app" / "static" / "documentacion"
GUIAS = DOC / "guias"
SALIDA = RAIZ / "docs" / "manual"
CAPTURAS_REL = "../../app/static/documentacion/"     # de docs/manual/ a las capturas
AVISO = "<!-- Generado por scripts/generar_manual_md.py desde app/static/documentacion/guias/{id}.json. No editar a mano. -->\n\n"


def _txt(s) -> str:
    """HTML ligero de las guías → Markdown: <b>/<strong> a **, el resto de etiquetas fuera."""
    s = re.sub(r"</?(b|strong)>", "**", str(s or ""))
    return re.sub(r"<[^>]+>", "", s).strip()


def _captura(c: dict) -> list:
    if not c or not c.get("src"):
        return []
    out = [f"![{_txt(c.get('alt'))}]({CAPTURAS_REL}{c['src']})", ""]
    marcas = c.get("marcas") or []
    if marcas:
        out += [f"{m.get('n', i + 1)}. {_txt(m.get('texto'))}" for i, m in enumerate(marcas)] + [""]
    return out


def _seccion(s: dict) -> list:
    out = [f"## {_txt(s.get('titulo'))}", ""]
    for p in s.get("parrafos") or []:
        out += [_txt(p), ""]
    if s.get("intro"):
        out += [_txt(s["intro"]), ""]
    tipo = s.get("tipo")
    if tipo == "pasos":
        for i, p in enumerate(s.get("pasos") or [], 1):
            out += [f"### Paso {i}. {_txt(p.get('titulo'))}", ""]
            if p.get("texto"):
                out += [_txt(p["texto"]), ""]
            out += _captura(p.get("captura"))
            if p.get("nota"):
                out += [f"> **Nota:** {_txt(p['nota'])}", ""]
    elif tipo == "ficha":
        out += ["| Campo | Detalle |", "| --- | --- |"]
        out += [f"| {_txt(a)} | {_txt(b).replace('|', '/')} |" for a, b in s.get("filas") or []] + [""]
    elif tipo == "faq":
        for it in s.get("items") or []:
            out += [f"**{_txt(it.get('p'))}**", "", _txt(it.get("r")), ""]
    elif tipo == "glosario":
        out += [f"- **{_txt(t.get('t'))}**: {_txt(t.get('d'))}" for t in s.get("terminos") or []] + [""]
    out += _captura(s.get("captura"))
    return out


def guia_md(g: dict, titulos: dict) -> str:
    out = [f"# {_txt(g.get('titulo'))}", "", f"*{_txt(g.get('subtitulo'))}* · Ruta: `{g.get('ruta', '')}` · "
           f"Lectura: {g.get('tiempo_lectura', '?')} min", "", _txt(g.get("resumen")), ""]
    roles = g.get("roles") or {}
    if roles:
        out += ["**Quién puede hacer qué**", ""] + [f"- **{r.capitalize()}**: {_txt(d)}" for r, d in roles.items()] + [""]
    for s in g.get("secciones") or []:
        out += _seccion(s)
    rel = [r for r in g.get("relacionadas") or [] if r in titulos]
    if rel:
        out += ["## Guías relacionadas", ""] + [f"- [{titulos[r]}]({r}.md)" for r in rel] + [""]
    return AVISO.format(id=g["id"]) + "\n".join(out).rstrip() + "\n"


def indice_md(idx: dict) -> str:
    out = [f"# {_txt(idx.get('titulo', 'Manual de usuario'))}", "",
           "Versión en Markdown del manual interactivo (`/documentacion/manual`). Se regenera con "
           "`python scripts/generar_manual_md.py`.", ""]
    for gr in idx.get("grupos") or []:
        gs = [g for g in idx["guias"] if g.get("grupo") == gr["id"]]
        if gs:
            out += [f"## {_txt(gr['titulo'])}", ""] + [f"- [{_txt(g['titulo'])}]({g['id']}.md) — {_txt(g.get('subtitulo'))}" for g in gs] + [""]
    return AVISO.format(id="indice") + "\n".join(out).rstrip() + "\n"


def generar() -> dict:
    """{nombre_md: contenido} esperado según el índice y las guías actuales."""
    idx = json.loads((GUIAS / "indice.json").read_text(encoding="utf-8"))
    titulos = {g["id"]: _txt(g["titulo"]) for g in idx["guias"]}
    archivos = {"README.md": indice_md(idx)}
    for g in idx["guias"]:
        datos = json.loads((GUIAS / f"{g['id']}.json").read_text(encoding="utf-8"))
        archivos[f"{g['id']}.md"] = guia_md(datos, titulos)
    return archivos


def diferencias(esperado: dict) -> list:
    actuales = {p.name for p in SALIDA.glob("*.md")} if SALIDA.exists() else set()
    def leer(n):   # sin importar CRLF/LF (git en Windows puede convertirlos)
        return (SALIDA / n).read_text(encoding="utf-8").replace("
", "
")
    malos = [n for n, c in esperado.items() if not (SALIDA / n).exists() or leer(n) != c]
    return sorted(malos + [f"{n} (sobra)" for n in actuales - set(esperado)])


def main() -> int:
    esperado = generar()
    if "--check" in sys.argv:
        dif = diferencias(esperado)
        if dif:
            print("Desactualizados:", ", ".join(dif), "→ corre python scripts/generar_manual_md.py")
            return 1
        print(f"OK: {len(esperado)} archivos al día")
        return 0
    SALIDA.mkdir(parents=True, exist_ok=True)
    for p in SALIDA.glob("*.md"):
        if p.name not in esperado:
            p.unlink()
            print("borrado", p.name)
    for n, c in esperado.items():
        (SALIDA / n).write_text(c, encoding="utf-8", newline="\n")
    print(f"{len(esperado)} archivos en {SALIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
