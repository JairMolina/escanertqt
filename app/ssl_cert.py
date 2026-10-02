"""Certificados SSL para HTTPS en la red local.

Por qué hay una autoridad propia (CA): un certificado autofirmado suelto hace que el navegador muestre "Tu conexión no es
privada / Sitio no seguro" y obliga a repetir el aviso cada vez que cambia la IP. Aquí se crea UNA vez una autoridad local
("Escaner TQT Local CA", certs/ca.pem) que se instala como confiable en la PC y en los celulares (ruta /cert o el script
instalar_certificado.ps1); el certificado del servidor (certs/cert.pem) lo firma esa autoridad y se regenera solo cuando
cambia la IP o está por vencer, sin volver a instalar nada. La CA solo puede firmar IP privadas y localhost.
"""
import ipaddress
import logging
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.config import settings

logger = logging.getLogger(__name__)


def generate_self_signed_cert(
    cert_path: Path,
    key_path: Path,
    local_ip: str,
    validity_days: int = 1095,  # 3 años
) -> Tuple[Path, Path]:
    """
    Genera un certificado SSL autofirmado X.509 con SAN (Subject Alternative Names)
    para localhost, 127.0.0.1 y la IP local detectada (ej. 192.168.3.36).

    Esto garantiza que navegadores móviles (Chrome en Android, Safari en iOS)
    permitan invocar `navigator.mediaDevices.getUserMedia` para la cámara del escáner.
    """
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Generando nueva clave privada RSA 2048 bits...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Identidad del certificado
    hostname = socket.gethostname()
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Produccion"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "TQT Planta"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Escaner TQT"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Control de Calidad"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"Escaner-TQT-{local_ip}"),
    ])

    # Construir lista de Subject Alternative Names (SAN)
    san_list: List[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]

    # Agregar hostname de la máquina
    if hostname and hostname.lower() != "localhost":
        san_list.append(x509.DNSName(hostname))

    # Agregar IP local detectada como IPAddress y DNSName para compatibilidad máxima
    try:
        ip_obj = ipaddress.ip_address(local_ip)
        san_list.append(x509.IPAddress(ip_obj))
    except ValueError:
        logger.warning("La IP local proporcionada '%s' no es válida como dirección IP.", local_ip)

    if local_ip not in ("127.0.0.1", "localhost"):
        san_list.append(x509.DNSName(local_ip))

    now = datetime.now(timezone.utc)
    # Restar 1 día para prevenir problemas de desfase horario en dispositivos móviles
    not_valid_before = now - timedelta(days=1)
    not_valid_after = now + timedelta(days=validity_days)

    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_cert_sign=True,
                crl_sign=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
    )

    certificate = cert_builder.sign(
        private_key=private_key,
        algorithm=hashes.SHA256(),
    )

    # Guardar clave privada en formato PEM
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(key_path, "wb") as f:
        f.write(key_pem)

    # Guardar certificado en formato PEM
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    with open(cert_path, "wb") as f:
        f.write(cert_pem)

    logger.info("Certificado SSL generado con éxito en %s", cert_path)
    logger.info("Clave privada SSL guardada en %s", key_path)
    return cert_path, key_path


def cert_contains_ip(cert_path: Path, target_ip: str) -> bool:
    """Verifica si un certificado existente ya incluye la IP objetivo en sus SANs."""
    if not cert_path.exists():
        return False

    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Chequear fecha de expiración
        now = datetime.now(timezone.utc)
        if cert.not_valid_after_utc < now:
            return False

        # Obtener extensión SAN
        san_ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        san_value = san_ext.value

        target_obj = None
        try:
            target_obj = ipaddress.ip_address(target_ip)
        except ValueError:
            pass

        for name in san_value:
            if isinstance(name, x509.IPAddress) and target_obj and name.value == target_obj:
                return True
            if isinstance(name, x509.DNSName) and name.value == target_ip:
                return True

        return False
    except Exception as e:
        logger.warning("Error al inspeccionar certificado existente: %s", e)
        return False


CA_DIAS = 3650        # 10 años: se instala una sola vez
HOJA_DIAS = 800       # menos de los 825 que admite Apple; se renueva sola
RENOVAR_ANTES_DIAS = 30


def ca_paths() -> Tuple[Path, Path]:
    return settings.CERTS_DIR / "ca.pem", settings.CERTS_DIR / "ca.key"


def _escribir_privado(ruta: Path, clave) -> None:
    ruta.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption()))
    try:
        ruta.chmod(0o600)
    except OSError:
        pass


def ensure_ca(ca_cert: Optional[Path] = None, ca_key: Optional[Path] = None) -> Tuple[x509.Certificate, object]:
    """Devuelve (certificado, clave) de la autoridad local; la crea si no existe (o si está por vencer)."""
    ca_cert = ca_cert or ca_paths()[0]
    ca_key = ca_key or ca_paths()[1]
    if ca_cert.exists() and ca_key.exists():
        try:
            cert = x509.load_pem_x509_certificate(ca_cert.read_bytes())
            clave = serialization.load_pem_private_key(ca_key.read_bytes(), password=None)
            if cert.not_valid_after_utc - datetime.now(timezone.utc) > timedelta(days=RENOVAR_ANTES_DIAS):
                return cert, clave
        except Exception as e:
            logger.warning("No se pudo leer la autoridad local, se crea una nueva: %s", e)
    ca_cert.parent.mkdir(parents=True, exist_ok=True)
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TQT"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Escaner TQT Local CA"),
    ])
    ahora = datetime.now(timezone.utc)
    privadas = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    cert = (
        x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(days=1)).not_valid_after(ahora + timedelta(days=CA_DIAS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False),
                       critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
        # la CA solo puede emitir para redes privadas y localhost (si la llave se filtrara, no sirve para sitios públicos)
        .add_extension(x509.NameConstraints(permitted_subtrees=[x509.IPAddress(n) for n in privadas] + [x509.DNSName("localhost")],
                                            excluded_subtrees=None), critical=False)
        .sign(clave, hashes.SHA256())
    )
    ca_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    _escribir_privado(ca_key, clave)
    logger.info("Autoridad certificadora local creada en %s", ca_cert)
    return cert, clave


def generate_signed_cert(cert_path: Path, key_path: Path, local_ip: str, ca_cert: x509.Certificate, ca_key) -> Tuple[Path, Path]:
    """Certificado del servidor firmado por la autoridad local (SAN: localhost, 127.0.0.1 y la IP de la PC)."""
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    san: List[x509.GeneralName] = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
    try:
        ip = ipaddress.ip_address(local_ip)
        if ip != ipaddress.IPv4Address("127.0.0.1"):
            san.append(x509.IPAddress(ip))
    except ValueError:
        logger.warning("La IP local '%s' no es una dirección válida; el certificado solo cubrirá localhost.", local_ip)
    ahora = datetime.now(timezone.utc)
    nombre = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TQT"), x509.NameAttribute(NameOID.COMMON_NAME, f"Escaner TQT {local_ip}")])
    cert = (
        x509.CertificateBuilder().subject_name(nombre).issuer_name(ca_cert.subject).public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(days=1)).not_valid_after(ahora + timedelta(days=HOJA_DIAS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False, data_encipherment=False,
                                     key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False),
                       critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    # cadena completa (servidor + autoridad): algunos clientes la necesitan para validar
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM))
    _escribir_privado(key_path, clave)
    return cert_path, key_path


def _hoja_valida(cert_path: Path, key_path: Path, ca_cert: x509.Certificate, ip: str) -> bool:
    """¿El certificado del servidor existe, lo firmó nuestra autoridad, cubre la IP y no vence pronto?"""
    if not (cert_path.exists() and key_path.exists() and cert_contains_ip(cert_path, ip)):
        return False
    try:
        hoja = x509.load_pem_x509_certificate(cert_path.read_bytes())  # el primero del archivo es el del servidor
        if hoja.issuer != ca_cert.subject:
            return False
        hoja.verify_directly_issued_by(ca_cert)
        return hoja.not_valid_after_utc - datetime.now(timezone.utc) > timedelta(days=RENOVAR_ANTES_DIAS)
    except Exception:
        return False


def ensure_ssl_certificates(force_regenerate: bool = False) -> Tuple[Path, Path]:
    """
    Garantiza una autoridad local y un certificado de servidor firmado por ella que cubra la IP actual.
    Se regenera solo el del servidor (IP nueva, próximo a vencer, o un autofirmado antiguo); la autoridad se conserva,
    así que los dispositivos que ya la instalaron siguen confiando sin repetir nada.
    """
    cert_file, key_file, local_ip = settings.CERT_FILE, settings.KEY_FILE, settings.LOCAL_IP
    ca_cert, ca_key = ensure_ca()
    if force_regenerate or not _hoja_valida(cert_file, key_file, ca_cert, local_ip):
        print(f"[SSL] Emitiendo certificado del servidor para {local_ip} (firmado por la autoridad local)...")
        generate_signed_cert(cert_file, key_file, local_ip, ca_cert, ca_key)
        print(f"[SSL] Certificado listo en: {cert_file}")
    else:
        print(f"[SSL] Certificado del servidor válido para {local_ip}.")
    return cert_file, key_file


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_ssl_certificates()
