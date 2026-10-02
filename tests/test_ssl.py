"""Certificado SSL autofirmado con SAN (IP LAN, 127.0.0.1, localhost). Usa una carpeta temporal: no toca certs/ real."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import ipaddress
import tempfile
import unittest
from pathlib import Path

from cryptography import x509

import socket
import ssl
import threading
from unittest import mock

from app.config import settings
from app.ssl_cert import (cert_contains_ip, ensure_ca, ensure_ssl_certificates, generate_self_signed_cert,
                          generate_signed_cert)


class TestSSLCertificates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.test_cert_path = Path(self.tmp.name) / "test_cert.pem"
        self.test_key_path = Path(self.tmp.name) / "test_key.pem"

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_and_inspect_san(self):
        test_ip = "192.168.3.36"
        cert_p, key_p = generate_self_signed_cert(cert_path=self.test_cert_path, key_path=self.test_key_path, local_ip=test_ip)
        self.assertTrue(cert_p.exists())
        self.assertTrue(key_p.exists())
        cert = x509.load_pem_x509_certificate(cert_p.read_bytes())
        san = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        ip_entries = [n.value for n in san if isinstance(n, x509.IPAddress)]
        dns_entries = [n.value for n in san if isinstance(n, x509.DNSName)]
        self.assertIn(ipaddress.IPv4Address("127.0.0.1"), ip_entries)
        self.assertIn(ipaddress.IPv4Address(test_ip), ip_entries)
        self.assertIn("localhost", dns_entries)

    def test_cert_contains_ip_checker(self):
        test_ip = "192.168.3.36"
        generate_self_signed_cert(cert_path=self.test_cert_path, key_path=self.test_key_path, local_ip=test_ip)
        self.assertTrue(cert_contains_ip(self.test_cert_path, test_ip))
        self.assertTrue(cert_contains_ip(self.test_cert_path, "127.0.0.1"))
        self.assertFalse(cert_contains_ip(self.test_cert_path, "10.0.0.99"))


class TestAutoridadLocal(unittest.TestCase):
    """La autoridad local hace que el navegador confíe en el servidor (sin el aviso de sitio no seguro)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.ca_cert, self.ca_key = self.d / "ca.pem", self.d / "ca.key"

    def tearDown(self):
        self.tmp.cleanup()

    def _hoja(self, ip="127.0.0.1"):
        ca, clave = ensure_ca(self.ca_cert, self.ca_key)
        generate_signed_cert(self.d / "cert.pem", self.d / "key.pem", ip, ca, clave)
        return ca

    def _handshake(self, ca_pem, hostname, servir_ip="127.0.0.1"):
        """Servidor TLS con el certificado emitido y cliente que confía solo en `ca_pem` (o en nada si es None)."""
        srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        srv_ctx.load_cert_chain(self.d / "cert.pem", self.d / "key.pem")
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        puerto = sock.getsockname()[1]

        def servir():
            try:
                c, _ = sock.accept()
                with srv_ctx.wrap_socket(c, server_side=True) as s:
                    s.recv(1)
            except Exception:
                pass
        hilo = threading.Thread(target=servir, daemon=True)
        hilo.start()
        ctx = ssl.create_default_context(cafile=str(ca_pem)) if ca_pem else ssl.create_default_context()
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=5) as raw:
                with ctx.wrap_socket(raw, server_hostname=hostname) as t:
                    t.sendall(b"x")
                    return t.version()
        finally:
            sock.close()
            hilo.join(timeout=2)

    def test_la_autoridad_es_restringida_y_la_hoja_esta_bien_formada(self):
        ca = self._hoja("192.168.3.36")
        bc = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
        self.assertEqual((bc.ca, bc.path_length), (True, 0))
        nc = ca.extensions.get_extension_for_class(x509.NameConstraints).value
        self.assertTrue(any(isinstance(n, x509.DNSName) and n.value == "localhost" for n in nc.permitted_subtrees))
        cadena = (self.d / "cert.pem").read_bytes().decode()
        self.assertEqual(cadena.count("BEGIN CERTIFICATE"), 2)              # servidor + autoridad
        hoja = x509.load_pem_x509_certificate((self.d / "cert.pem").read_bytes())
        hoja.verify_directly_issued_by(ca)
        self.assertFalse(hoja.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertIn(x509.oid.ExtendedKeyUsageOID.SERVER_AUTH, hoja.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
        san = hoja.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertIn(ipaddress.IPv4Address("192.168.3.36"), [n.value for n in san if isinstance(n, x509.IPAddress)])
        self.assertLessEqual((hoja.not_valid_after_utc - hoja.not_valid_before_utc).days, 825)   # límite de Apple
        self.assertNotIn(b"PRIVATE", (self.ca_cert).read_bytes())

    def test_apreton_tls_real_con_y_sin_la_autoridad_instalada(self):
        self._hoja("127.0.0.1")
        self.assertTrue(self._handshake(self.ca_cert, "127.0.0.1").startswith("TLS"))          # con la autoridad: confiable
        with self.assertRaises(ssl.SSLCertVerificationError):
            self._handshake(None, "127.0.0.1")                                                   # sin ella: el aviso de "no seguro"

    def test_la_autoridad_no_sirve_para_sitios_publicos(self):
        self._hoja("8.8.8.8")                                     # certificado para una IP pública, firmado por nuestra CA
        with self.assertRaises(ssl.SSLCertVerificationError):
            self._handshake(self.ca_cert, "8.8.8.8")

    def test_cambio_de_ip_reemite_solo_el_certificado_del_servidor(self):
        cfg = dict(CERTS_DIR=self.d, CERT_FILE=self.d / "cert.pem", KEY_FILE=self.d / "key.pem")
        with mock.patch.multiple(settings, LOCAL_IP="192.168.3.36", **cfg):
            ensure_ssl_certificates()
            ca1 = (self.d / "ca.pem").read_bytes()
            hoja1 = (self.d / "cert.pem").read_bytes()
            ensure_ssl_certificates()                                            # sin cambios: no reemite
            self.assertEqual((self.d / "cert.pem").read_bytes(), hoja1)
        with mock.patch.multiple(settings, LOCAL_IP="192.168.3.99", **cfg):
            ensure_ssl_certificates()
            self.assertEqual((self.d / "ca.pem").read_bytes(), ca1)              # la autoridad instalada en los celulares se conserva
            self.assertNotEqual((self.d / "cert.pem").read_bytes(), hoja1)
            self.assertTrue(cert_contains_ip(self.d / "cert.pem", "192.168.3.99"))

    def test_un_autofirmado_antiguo_se_reemplaza_por_uno_firmado_por_la_autoridad(self):
        cfg = dict(CERTS_DIR=self.d, CERT_FILE=self.d / "cert.pem", KEY_FILE=self.d / "key.pem", LOCAL_IP="192.168.3.36")
        generate_self_signed_cert(self.d / "cert.pem", self.d / "key.pem", "192.168.3.36")   # lo que había antes
        with mock.patch.multiple(settings, **cfg):
            ensure_ssl_certificates()
        ca = x509.load_pem_x509_certificate((self.d / "ca.pem").read_bytes())
        x509.load_pem_x509_certificate((self.d / "cert.pem").read_bytes()).verify_directly_issued_by(ca)


if __name__ == "__main__":
    unittest.main()
