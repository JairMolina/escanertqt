"""Envío de correo por SMTP desde el backend (nunca desde el navegador).

* Credenciales SOLO por variables de entorno del contenedor (TQT_SMTP_*): nada en el código, el frontend ni Git.
* Puerto 465 = TLS implícito desde el inicio (SMTP_SSL); cualquier otro puerto usa STARTTLS obligatorio.
  En ambos casos el certificado del servidor se valida (ssl.create_default_context: CA del sistema + nombre de host).
* El remitente es siempre TQT_SMTP_FROM; si hay que responder a un usuario, su correo va en Reply-To.
* Todo correo sale en multipart/alternative (texto + HTML con la plantilla de la marca, v1.3.41): los mensajes
  de solo texto con un adjunto y pocas palabras son los que más terminan en spam.
"""
import html as _html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

TIMEOUT_S = 20


class CorreoNoConfigurado(RuntimeError):
    pass


def _cfg() -> dict:
    usuario = os.getenv("TQT_SMTP_USER", "")
    return {
        "host": os.getenv("TQT_SMTP_HOST", ""),
        "puerto": int(os.getenv("TQT_SMTP_PORT", "465")),
        "usuario": usuario,
        "clave": os.getenv("TQT_SMTP_PASSWORD", ""),
        "remitente": os.getenv("TQT_SMTP_FROM", usuario),
        "nombre": os.getenv("TQT_SMTP_FROM_NAME", "Inventario TQT"),
    }


def configurado() -> bool:
    c = _cfg()
    return bool(c["host"] and c["usuario"] and c["clave"] and c["remitente"])


def enviar(para: str, asunto: str, texto: str, html: Optional[str] = None, reply_to: Optional[str] = None,
           adjuntos: Optional[List[Tuple[str, bytes, str]]] = None) -> str:
    """Envía un correo y devuelve su Message-ID. Lanza CorreoNoConfigurado o smtplib.SMTPException."""
    c = _cfg()
    if not configurado():
        raise CorreoNoConfigurado("El envío de correo no está configurado (variables TQT_SMTP_*).")
    msg = EmailMessage()
    msg["From"] = formataddr((c["nombre"], c["remitente"]))
    msg["To"] = para
    msg["Subject"] = asunto
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=c["remitente"].split("@")[-1])
    msg["Content-Language"] = "es-MX"
    msg["Auto-Submitted"] = "auto-generated"          # RFC 3834: correo automático (evita respuestas de vacaciones)
    msg["X-Auto-Response-Suppress"] = "OOF, AutoReply"
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(texto)
    msg.add_alternative(html or plantilla(asunto, [p for p in texto.split("\n\n") if p.strip()]), subtype="html")
    for nombre, datos, mime in adjuntos or []:   # (nombre, bytes, "tipo/subtipo")
        principal, _, sub = mime.partition("/")
        msg.add_attachment(datos, maintype=principal, subtype=sub, filename=nombre)

    contexto = ssl.create_default_context()
    if c["puerto"] == 465:
        servidor = smtplib.SMTP_SSL(c["host"], c["puerto"], timeout=TIMEOUT_S, context=contexto)
    else:
        servidor = smtplib.SMTP(c["host"], c["puerto"], timeout=TIMEOUT_S)
    with servidor as s:
        if c["puerto"] != 465:
            s.starttls(context=contexto)
        s.login(c["usuario"], c["clave"])
        s.send_message(msg)
    logger.info("Correo enviado a %s: %s", para, asunto)
    return msg["Message-ID"]


# ----------------------------------------------------------------------------- plantilla HTML (v1.3.41)
# Tablas con estilos en línea (lo único que respetan Outlook, Gmail y los clientes móviles), 600 px de ancho y
# los mismos colores que los Excel de la app. Todo texto que llega aquí se escapa.
AZUL, AZUL_CLARO, TINTA, GRIS, LINEA, FONDO = "#1F3A5F", "#E8EEF6", "#1B2333", "#667085", "#E3E8EF", "#F3F5F9"
_FUENTE = "'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
TONOS = {"ok": ("#1E7B4F", "#E6F4EC"), "info": (AZUL, AZUL_CLARO), "warn": ("#9A5B00", "#FFF4E0"), "bad": ("#B42318", "#FDECEA"), "gris": (GRIS, "#F2F4F7")}


def _e(x: object) -> str:
    return _html.escape(str(x), quote=True)


def _parrafo(p: str) -> str:
    return f'<p style="margin:0 0 14px;font:15px/1.6 {_FUENTE};color:{TINTA}">' + _e(p.strip()).replace("\n", "<br>") + "</p>"


def plantilla(titulo: str, parrafos: Optional[List[str]] = None, *, saludo: Optional[str] = None, preencabezado: Optional[str] = None,
              kpis: Optional[List[Tuple[str, object, str]]] = None, filas: Optional[List[Tuple[str, object]]] = None,
              tablas: Optional[List[Tuple[Optional[str], List[str], List[List[object]]]]] = None, nota: Optional[str] = None,
              boton: Optional[Tuple[str, str]] = None, aviso: Optional[Tuple[str, str]] = None, adjunto: Optional[str] = None,
              pie: Optional[str] = None) -> str:
    """Correo HTML con la marca de Escáner TQT.

    parrafos: texto plano. kpis: [(etiqueta, valor, tono de TONOS)]. filas: [(etiqueta, valor)] como ficha.
    tablas: [(subtítulo o None, encabezados, filas)]. nota: mensaje del remitente. boton: (texto, url). aviso: (tono, texto).
    adjunto: nombre del archivo adjunto."""
    partes: List[str] = []
    if saludo:
        partes.append(f'<p style="margin:0 0 14px;font:600 16px/1.5 {_FUENTE};color:{TINTA}">{_e(saludo)}</p>')
    partes += [_parrafo(p) for p in parrafos or []]
    if kpis:
        celdas = []
        for etq, val, tono in kpis:
            color, fondo = TONOS.get(tono, TONOS["gris"])
            celdas.append(f'<td align="center" style="background:{fondo};border-radius:10px;padding:14px 8px">'
                          f'<div style="font:700 28px/1.1 {_FUENTE};color:{color}">{_e(val)}</div>'
                          f'<div style="font:600 11px/1.4 {_FUENTE};color:{color};text-transform:uppercase;letter-spacing:.05em;padding-top:4px">{_e(etq)}</div></td>')
        sep = '<td width="10" style="font-size:0">&nbsp;</td>'
        partes.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 20px"><tr>{sep.join(celdas)}</tr></table>')
    if filas:
        trs = "".join(f'<tr><td style="padding:9px 14px;border-bottom:1px solid {LINEA};font:13px/1.4 {_FUENTE};color:{GRIS};width:38%">{_e(a)}</td>'
                      f'<td style="padding:9px 14px;border-bottom:1px solid {LINEA};font:600 14px/1.4 {_FUENTE};color:{TINTA}">{_e(b)}</td></tr>' for a, b in filas)
        partes.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;border:1px solid {LINEA};border-radius:10px;border-collapse:separate">{trs}</table>')
    for sub, cab, cuerpo in tablas or []:
        if sub:
            partes.append(f'<p style="margin:0 0 8px;font:700 14px/1.4 {_FUENTE};color:{AZUL}">{_e(sub)}</p>')
        th = "".join(f'<th align="left" style="padding:9px 10px;background:{AZUL};color:#FFFFFF;font:600 12px/1.3 {_FUENTE}">{_e(x)}</th>' for x in cab)
        trs = "".join("<tr>" + "".join(f'<td style="padding:8px 10px;border-bottom:1px solid {LINEA};font:13px/1.4 {_FUENTE};color:{TINTA};background:{"#FFFFFF" if i % 2 == 0 else FONDO}">{_e(v)}</td>' for v in fila) + "</tr>"
                      for i, fila in enumerate(cuerpo))
        partes.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;border-collapse:collapse"><tr>{th}</tr>{trs}</table>')
    if adjunto:
        partes.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 20px"><tr>'
                      f'<td style="background:#E6F4EC;border:1px solid #BFE3CF;border-radius:10px;padding:12px 16px;font:13px/1.4 {_FUENTE}">'
                      f'<span style="display:inline-block;background:#1E7B4F;color:#FFFFFF;font:700 11px/1 {_FUENTE};padding:5px 7px;border-radius:5px;letter-spacing:.05em">XLSX</span>'
                      f'&nbsp;&nbsp;<b style="color:{TINTA}">{_e(adjunto)}</b>'
                      f'<div style="color:{GRIS};font-size:12px;padding-top:6px">Archivo adjunto a este correo</div></td></tr></table>')
    if nota:
        partes.append(f'<div style="margin:0 0 20px;padding:12px 16px;border-left:4px solid {AZUL};background:{AZUL_CLARO};border-radius:0 8px 8px 0;'
                      f'font:14px/1.6 {_FUENTE};color:{TINTA}">{_e(nota).replace(chr(10), "<br>")}</div>')
    if aviso:
        color, fondo = TONOS.get(aviso[0], TONOS["info"])
        partes.append(f'<div style="margin:0 0 20px;padding:12px 16px;border-radius:8px;background:{fondo};font:600 14px/1.5 {_FUENTE};color:{color}">{_e(aviso[1])}</div>')
    if boton:
        partes.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px"><tr><td style="border-radius:8px;background:{AZUL}">'
                      f'<a href="{_e(boton[1])}" style="display:inline-block;padding:13px 26px;font:600 15px/1 {_FUENTE};color:#FFFFFF;text-decoration:none;border-radius:8px">{_e(boton[0])}</a>'
                      f'</td></tr></table><p style="margin:0 0 14px;font:12px/1.5 {_FUENTE};color:{GRIS}">Si el botón no funciona, copia este enlace en tu navegador:<br>'
                      f'<a href="{_e(boton[1])}" style="color:{AZUL};word-break:break-all">{_e(boton[1])}</a></p>')
    pie = pie or "Correo automático de Escáner TQT · Control de producción de tarjetas electrónicas."
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"><title>{_e(titulo)}</title></head>
<body style="margin:0;padding:0;background:{FONDO};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{FONDO}">{_e(preencabezado or titulo)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FONDO}"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#FFFFFF;border:1px solid {LINEA};border-radius:14px;border-collapse:separate;overflow:hidden">
<tr><td style="background:{AZUL};padding:22px 28px;border-radius:14px 14px 0 0">
<div style="font:700 20px/1.2 {_FUENTE};color:#FFFFFF">Escáner TQT</div>
<div style="font:13px/1.4 {_FUENTE};color:#C9D6E8;padding-top:3px">Control de producción</div></td></tr>
<tr><td style="padding:28px 28px 8px">
<h1 style="margin:0 0 18px;font:700 22px/1.3 {_FUENTE};color:{TINTA}">{_e(titulo)}</h1>
{"".join(partes)}</td></tr>
<tr><td style="padding:16px 28px 22px;border-top:1px solid {LINEA};font:12px/1.6 {_FUENTE};color:{GRIS}">{_e(pie)}</td></tr>
</table></td></tr></table></body></html>"""


def avisar_clave_restablecida(email: str) -> None:
    """Aviso de seguridad a la cuenta cuya contraseña se restableció. Nunca interrumpe el flujo si falla."""
    if not configurado():
        return
    try:
        texto = ("Hola:\n\nLa contraseña de tu cuenta de Escáner TQT se acaba de restablecer con la aprobación de otra cuenta.\n"
                 "Si no fuiste tú, avisa de inmediato al supervisor.\n\nEscáner TQT")
        html = plantilla("Tu contraseña se restableció", saludo="Hola:",
                         parrafos=["La contraseña de tu cuenta de Escáner TQT se acaba de restablecer con la aprobación de otra cuenta."],
                         filas=[("Cuenta", email)], aviso=("warn", "Si no fuiste tú, avisa de inmediato al supervisor."))
        enviar(email, "Tu contraseña de Escáner TQT se restableció", texto, html)
    except Exception as e:  # noqa: BLE001 - el aviso es un extra; jamás debe romper el restablecimiento
        logger.warning("No se pudo enviar el aviso de contraseña restablecida a %s: %s", email, e)
