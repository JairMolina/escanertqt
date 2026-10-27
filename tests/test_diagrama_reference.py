import _aislamiento as iso
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.services import usuarios
from app.database import db


class DiagramReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(app, base_url='https://testserver')

    def test_catalog_and_original_images_require_authenticated_tqt_access(self):
        anonymous = iso.cliente_sin_sesion(app)
        for path in ('/static/catalogos/diagrama_tqt.json', '/static/img/diagrama_tqt/pages_6.jpg'):
            self.assertEqual(anonymous.get(path).status_code, 401)
            with patch.object(usuarios, 'validar_sesion', return_value=dict(email='reader@test.mx', rol='consultor', debe_cambiar=False, modulos=['impresora'])):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_consultor_reads_the_catalog_and_every_image_without_extra_privileges(self):
        with patch.object(usuarios, 'validar_sesion', return_value=dict(email='reader@test.mx', rol='consultor', debe_cambiar=False, modulos=['escaner-tqt'])):
            response = self.client.get('/static/catalogos/diagrama_tqt.json')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            for assets in data['assets'].values():
                for path in assets.values():
                    image = self.client.get(path)
                    self.assertEqual(image.status_code, 200)
                    self.assertEqual(image.headers['content-type'], 'image/jpeg')
                    self.assertTrue(image.content.startswith(b'\xff\xd8'))
            self.assertEqual(self.client.delete('/api/stm32/stations/'+'a'*24).status_code, 403)
