"""Native command section uses authenticated static resources and stable data IDs."""
import _aislamiento  # noqa: F401
import json
import unittest
from pathlib import Path

from app.database import db
from app.main import app
from app.services import usuarios
from _aislamiento import cliente_sin_sesion, verificar_aislamiento

STATIC = Path(__file__).resolve().parent.parent / 'app/static'
RESOURCES = ('/monitor', '/static/js/comandos_core.js', '/static/js/sec_comandos.js',
             '/static/css/sec_comandos.css', '/static/catalogos/comandos_r1.json',
             '/static/catalogos/COMANDOS_R1.md')


class TestComandosCatalogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def test_resources_require_login(self):
        client = cliente_sin_sesion(app)
        for resource in RESOURCES:
            if resource.endswith('.css'):
                # Existing middleware makes styles public for the login page.
                self.assertEqual(client.get(resource).status_code, 200)
                continue
            self.assertIn(client.get(resource, follow_redirects=False).status_code, (302, 401), resource)

    def test_read_only_catalog_is_available_for_all_existing_roles(self):
        for role in ('administrador', 'general', 'consultor'):
            email = f'comandos-{role}@ejemplo.com'
            invite = usuarios.crear_invitacion(email, role, 'developer@skyguardian.mx')
            usuarios.aceptar_invitacion(invite, 'SoloPrueba-Comandos-2026')
            client = cliente_sin_sesion(app)
            client.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion(email))
            for resource in RESOURCES:
                self.assertEqual(client.get(resource).status_code, 200, (role, resource))

    def test_catalog_defaults_and_metadata(self):
        catalog = json.loads((STATIC / 'catalogos/comandos_r1.json').read_text(encoding='utf-8'))
        commands = catalog['commands']
        self.assertEqual(len(commands), 37)
        self.assertEqual(len(set(c['id'] for c in commands)), len(commands))
        self.assertEqual(len(catalog['factory_defaults']), 28)
        for command in commands:
            self.assertTrue(set(command['supported_versions']) <= set(catalog['firmware_versions']))
            for key in ('title', 'group', 'kind', 'input'):
                self.assertTrue(command[key])

    def test_native_monitor_loads_catalog_logic_before_section(self):
        html = (STATIC / 'monitor.html').read_text(encoding='utf-8')
        self.assertLess(html.index('comandos_core.js'), html.index('sec_comandos.js'))
        self.assertIn('sec_comandos.css', html)
        section = (STATIC / 'js/sec_comandos.js').read_text(encoding='utf-8')
        self.assertIn("grupo:'gestion'", section)
        self.assertNotIn('<iframe', section)


if __name__ == '__main__':
    unittest.main()
