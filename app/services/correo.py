"""Envío de correo por SMTP desde el backend (nunca desde el navegador).

* Credenciales SOLO por variables de entorno del contenedor (TQT_SMTP_*): nada en el código, el frontend ni Git.
* Puerto 465 = TLS implícito desde el inicio (SMTP_SSL); cualquier otro puerto usa STARTTLS obligatorio.
  En ambos casos el certificado del servidor se valida (ssl.create_default_context: CA del sistema + nombre de host).
* El remitente es siempre TQT_SMTP_FROM; si hay que responder a un usuario, su correo va en Reply-To.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

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


def enviar(para: str, asunto: str, texto: str, html: Optional[str] = None, reply_to: Optional[str] = None) -> str:
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
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")

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


def avisar_clave_restablecida(email: str) -> None:
    """Aviso de seguridad a la cuenta cuya contraseña se restableció. Nunca interrumpe el flujo si falla."""
    if not configurado():
        return
    try:
        enviar(email, "Tu contraseña de Escáner TQT se restableció",
               "Hola:\n\nLa contraseña de tu cuenta de Escáner TQT se acaba de restablecer con la aprobación de otra cuenta.\n"
               "Si no fuiste tú, avisa de inmediato al supervisor.\n\nInventario TQT")
    except Exception as e:  # noqa: BLE001 - el aviso es un extra; jamás debe romper el restablecimiento
        logger.warning("No se pudo enviar el aviso de contraseña restablecida a %s: %s", email, e)
