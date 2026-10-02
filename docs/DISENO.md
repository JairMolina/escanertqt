# Sistema visual — "máscara de soldadura + serigrafía"

Todo en `app/static/css/app.css` (tokens en `:root`, oscuro por defecto, claro con el botón de tema o `prefers-color-scheme`).
Sin CDN: fuentes y librerías son locales.

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--bg` / `--surface` / `--surface-2` | `#0A1020` / `#121B33` / `#1A2646` | `#E9ECF1` / `#FFFFFF` / `#F3F5F9` | suelo, paneles, controles |
| `--text` / `--muted` / `--faint` | `#E9EEF5` / `#93A1BD` / `#6C7B9F` | `#0D1630` / `#4C5873` / `#7A86A0` | texto (serigrafía) |
| `--accent` | `#D9A441` (oro ENIG) | `#C58B14` | acción primaria, marco del visor |
| `--ok / --warn / --bad / --info` | `#3FD08A / #F2B33D / #FF6B6B / #5AA9FF` | `#0B8A55 / #9A5F00 / #C12A2A / #1D63C2` | estados semánticos (aparte del acento) |
| `--r1 / --r2 / --r3` | `#62A8FF / #B08CFF / #2FC9C0` | `#1D63C2 / #7444D6 / #0B8D86` | tipo de PCB (siempre con forma: ■ ● ◆ y texto) |

Tipografía: **Barlow Semi Condensed** (interfaz, 400–700) + **IBM Plex Mono** (series, nombres, MAC; 400–600), en `app/static/fonts/`.

Firma visual: visor con esquinas de "patrón de posición" de QR y trazo de barrido; número de serie leído en mono enorme
(como la serigrafía de la placa); designadores de tipo R1/R2/R3 con forma propia; esquinas cortadas en el visor.
Sonido por tipo (R1 grave, R2 medio, R3 agudo) y "ya registrada" con tono distinto al de error.

Componentes JS reutilizables (`window.TQT`, `js/common.js`): `h()` (DOM seguro), `sheet()` (hoja inferior/diálogo sin `confirm()`),
`toast()`, `tipoChip()`, `badge()`, `stagesStrip()`, `icon()` (SVG propio), `mountShell()` (cabecera + pestañas), `mountVisor()` (`js/visor.js`).
