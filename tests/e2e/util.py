"""Utilidades comunes de las pruebas de navegador (Playwright + Chrome). Ver README.md."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
BASE = os.environ.get("TQT_BASE", "https://127.0.0.1:8457")
HOST = BASE.split("//")[1]
FIXTURE_QR = RAIZ / "tests" / "fixtures" / "qr_R3_V30_0084_invertido.jpg"
QRLIB = (RAIZ / "app" / "static" / "js" / "qrcode-generator.js").read_text(encoding="utf-8")

# Cámara falsa controlable: getUserMedia devuelve el stream de un <canvas>; __showQR(texto, invertido) dibuja el QR.
CAM_JS = QRLIB + r"""
;(() => {
  const cv = document.createElement('canvas'); cv.width = 640; cv.height = 480;
  const ctx = cv.getContext('2d');
  const grey = () => { ctx.fillStyle = '#5a5a5a'; ctx.fillRect(0, 0, 640, 480); };
  grey();
  window.__cam = { shownAt: 0, text: null };
  window.__showQR = (text, inv = true, size = 320) => {
    const q = qrcode(0, 'M'); q.addData(text); q.make();
    const n = q.getModuleCount(), qz = 4, m = Math.floor(size / (n + qz * 2));
    const tot = m * (n + qz * 2), ox = Math.floor((640 - tot) / 2), oy = Math.floor((480 - tot) / 2);
    ctx.fillStyle = inv ? '#000' : '#fff'; ctx.fillRect(ox, oy, tot, tot);
    ctx.fillStyle = inv ? '#fff' : '#000';
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) ctx.fillRect(ox + (c + qz) * m, oy + (r + qz) * m, m, m);
    window.__cam.shownAt = performance.now(); window.__cam.text = text;
  };
  window.__clearQR = () => { grey(); window.__cam.text = null; };
  let tick = 0;
  setInterval(() => { ctx.fillStyle = (tick++ % 2) ? '#5b5b5b' : '#5a5a5a'; ctx.fillRect(0, 0, 2, 2); }, 33); // mantiene fotogramas vivos
  if (navigator.mediaDevices) {
    navigator.mediaDevices.getUserMedia = async () => cv.captureStream(30);
    navigator.mediaDevices.enumerateDevices = async () => [{ kind: 'videoinput', deviceId: 'fake', label: 'fake' }];
  }
})();
"""


class Vigia:
    """Registra consola, fallos de red, respuestas >=400 y peticiones a hosts externos de una página."""
    def __init__(self, page):
        self.consola, self.fallos, self.http, self.externas, self.reqs = [], [], [], [], []
        page.on("console", self._console)
        page.on("pageerror", lambda e: self.consola.append(("pageerror", str(e))))
        page.on("requestfailed", lambda r: self.fallos.append((r.url, r.failure)))
        page.on("response", self._resp)
        page.on("request", self._req)

    def _console(self, m):
        if m.type in ("error", "warning"):
            self.consola.append((m.type, m.text))

    def _resp(self, r):
        self.reqs.append((r.url, r.status))
        if r.status >= 400:
            self.http.append((r.status, r.url))

    def _req(self, r):
        if r.url.startswith(("data:", "blob:", "about:")):
            return
        host = r.url.split("//", 1)[-1].split("/", 1)[0]
        if host != HOST:
            self.externas.append(r.url)

    def limpio(self):
        return not (self.consola or self.fallos or self.http or self.externas)


def lanzar(p, extra=(), **ctx):
    args = ["--ignore-certificate-errors", "--use-fake-ui-for-media-stream", *extra]
    try:
        br = p.chromium.launch(channel="chrome", args=args)
    except Exception:
        br = p.chromium.launch(args=args)
    c = br.new_context(ignore_https_errors=True, permissions=["camera", "clipboard-read", "clipboard-write"], **ctx)
    return br, c
