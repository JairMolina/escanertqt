import _aislamiento
import sys, io
import fitz, cv2, numpy as np
from app.services.dymo_service import DymoService as D
T={"id":1,"id_tarjeta_num":"0021","nombre_r1":"TQT-R1-V31-9999","mac_r1":"FF:FF:FF:FF:FF:FE","nombre_r2":"TQT-R2-V31-9999","mac_r2":"FF:FF:FF:FF:FF:FE","estado_pcb_r1":"FUNCIONAL","estado_pcb_r2":"FUNCIONAL","estado_general":"LIBERADO"}
svg=D.generate_svg_preview(T,guia=False)
doc=fitz.open(stream=svg.encode(),filetype="svg")
pm=doc[0].get_pixmap(dpi=300,alpha=False,colorspace=fitz.csGRAY)
print(pm.width,pm.height)
a=np.frombuffer(pm.samples,dtype=np.uint8).reshape(pm.height,pm.width)
cv2.imwrite("qa_dymo.png",a)
print(np.unique(a)[:10], len(np.unique(a)))
d=cv2.QRCodeDetector()
v,pts,_=d.detectAndDecode(a)
print(repr(v), v==D.format_qr_payload(T))
_,b=cv2.threshold(a,128,255,cv2.THRESH_BINARY)
for name,img in [("bin",b),("bin+pad",cv2.copyMakeBorder(b,40,40,40,40,cv2.BORDER_CONSTANT,value=255))]:
    print(name,repr(d.detectAndDecode(img)[0]))
# solo el QR recortado, con silencio de 4 módulos añadido
qr=b[:, :260]
print("crop",repr(d.detectAndDecode(cv2.copyMakeBorder(qr,60,60,60,0,cv2.BORDER_CONSTANT,value=255))[0]))
big=cv2.resize(b,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
print("x3",repr(d.detectAndDecode(big)[0]))
try:
    print("wechat", cv2.wechat_qrcode_WeChatQRCode)
except Exception as e: print("nowechat")
print(cv2.__version__)
