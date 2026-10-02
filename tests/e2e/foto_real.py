"""Lee la foto real invertida con la cámara falsa de Chrome (--use-file-for-fake-video-capture) N veces y mide el tiempo.
Cada intento usa un servidor con la PCB ya registrada o no: aquí solo se mira el readout (sirve también DUPLICADA)."""
import sys, time
from playwright.sync_api import sync_playwright
from util import *

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
mj = Path(os.environ.get("TQT_SHOTS", str(RAIZ / "tests" / "e2e" / "_shots"))).resolve() / "qr.mjpeg"
mj.parent.mkdir(parents=True, exist_ok=True)
mj.write_bytes(FIXTURE_QR.read_bytes() * 30)
res = []
with sync_playwright() as p:
    for i in range(N):
        br, ctx = lanzar(p, extra=["--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={mj}"], viewport={"width": 390, "height": 844})
        pg = ctx.new_page(); vg = Vigia(pg)
        t0 = time.time()
        pg.goto(BASE + "/")
        ok = None
        try:
            pg.wait_for_function("()=>document.getElementById('roName').textContent.includes('TQT-R3-V30-0084')", timeout=10000)
            ok = round((time.time() - t0) * 1000)
        except Exception:
            ok = None
        info = pg.evaluate("()=>({name:document.getElementById('roName').textContent,msg:document.getElementById('roMsg').textContent,status:document.querySelector('.visor .status').textContent,state:document.querySelector('.visor').dataset.state,vw:document.querySelector('video').videoWidth,bd:'BarcodeDetector' in window})")
        print(i, "ms hasta lectura:", ok, info, "consola:", vg.consola)
        res.append(ok)
        br.close()
print("fallos:", sum(1 for r in res if r is None), "de", N)
