"""Contraste WCAG de los tokens de app.css (claro y oscuro). Uso: python tests/e2e/contraste.py"""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[2] / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")


def tokens(bloque):
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\s*;", bloque))


def bloques():
    claro = tokens(re.search(r":root\s*\{(.*?)\n\}", CSS, re.S).group(1))
    oscuro = tokens(re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\n\}', CSS, re.S).group(1))
    return claro, oscuro


def lum(hexa):
    r, g, b = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (primer plano, fondo, mínimo): 4.5 texto normal, 3.0 texto grande / componentes de interfaz
PARES = [
    ("text", "bg", 4.5), ("text", "surface", 4.5), ("text", "surface-2", 4.5),
    ("muted", "bg", 4.5), ("muted", "surface", 4.5), ("muted", "surface-2", 4.5),
    ("faint", "bg", 4.5), ("faint", "surface", 4.5),
    ("accent-text", "bg", 4.5), ("accent-text", "surface", 4.5),
    ("accent-ink", "accent", 4.5),
    ("ok", "surface", 4.5), ("warn", "surface", 4.5), ("bad", "surface", 4.5), ("info", "surface", 4.5),
    ("ok", "bg", 4.5), ("warn", "bg", 4.5), ("bad", "bg", 4.5), ("info", "bg", 4.5),
    ("r1", "surface", 4.5), ("r2", "surface", 4.5), ("r3", "surface", 4.5),
    ("bg", "ok", 4.5), ("bg", "bad", 4.5), ("bg", "warn", 4.5), ("bg", "muted", 4.5),  # texto sobre relleno semántico
    ("line-2", "bg", 3.0), ("accent", "bg", 3.0),
]


def calcular():
    claro, oscuro = bloques()
    out = []
    for tema, tk in (("claro", claro), ("oscuro", oscuro)):
        for fg, bg, minimo in PARES:
            if fg in tk and bg in tk:
                out.append((tema, fg, bg, round(ratio(tk[fg], tk[bg]), 2), minimo))
    return out


if __name__ == "__main__":
    for tema, fg, bg, r, m in calcular():
        print(f"{'FALLA' if r < m else 'ok   '} {tema:6} {fg:12} sobre {bg:10} {r:5.2f} (min {m})")
