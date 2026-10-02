"""Paquete de tests. Añade esta carpeta al sys.path para que `import _aislamiento` funcione tanto con
`python -m unittest discover -s tests` como con `python -m unittest tests.test_api`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
