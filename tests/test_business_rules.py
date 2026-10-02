"""Reglas de negocio puras: parseo de nombres TQT, MAC, vocabulario y estado derivado (igual a la fórmula del Excel)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from app.database.models import (
    VERSION_DEFAULT,
    derivar_estado_general,
    estado_pcb_desde_prueba,
    extract_mac,
    is_valid_mac,
    normalizar_estado_prueba,
    normalize_mac,
    parse_tarjeta_code,
)


class TestReglasDeNegocio(unittest.TestCase):
    # ---------------------------------------------------------------- MAC
    def test_01_mac_formatos(self):
        esperada = "30:AE:A4:07:0B:4C"
        for entrada in ("30aea4070b4c", "30-ae-a4-07-0b-4c", "30:ae:a4:07:0b:4c", "   30:AE:A4:07:0B:4C   "):
            self.assertEqual(normalize_mac(entrada), esperada)
        for entrada in ("30ae.a407.0b4c", "MAC: 30AEA4070B4C\r\n", "SN123 30-AE-A4-07-0B-4C x", "30:AE:A4:07:0B:4C"):
            self.assertEqual(extract_mac(entrada), esperada, entrada)
        self.assertEqual(extract_mac("70:4b:ca:5b:9f:6e"), "70:4B:CA:5B:9F:6E")  # la del ejemplo del usuario

    def test_02_mac_rechazos(self):
        for inv in ("", "12345", "30:AE:A4:07:0B", "30:AE:A4:07:0B:ZZ", "NO-ES-UNA-MAC"):
            self.assertFalse(is_valid_mac(inv), inv)
            self.assertIsNone(extract_mac(inv), inv)
        self.assertIsNone(extract_mac("30:AE:A4:07:0B:4C:5D:6E"))         # 8 octetos: no es una MAC
        self.assertIsNone(extract_mac("00:00:00:00:00:00"))
        self.assertIsNone(extract_mac("FF-FF-FF-FF-FF-FF"))

    # ---------------------------------------------------------------- nombres TQT
    def test_03_parseo_de_los_tres_tipos(self):
        for tipo in ("R1", "R2", "R3"):
            p = parse_tarjeta_code(f"TQT-{tipo}-V30-0011")
            self.assertEqual((p["tipo"], p["version"], p["numero"], p["nombre"]), (tipo, "30", "0011", f"TQT-{tipo}-V30-0011"))
        r3 = parse_tarjeta_code("TQT-R3-V30-0084")  # contenido real del QR de la foto
        self.assertEqual((r3["tipo"], r3["numero"]), ("R3", "0084"))

    def test_04_parseo_tolerante(self):
        self.assertEqual(parse_tarjeta_code("tqt r2 v30 11", "R2")["nombre"], "TQT-R2-V30-0011")   # espacios/minúsculas
        self.assertEqual(parse_tarjeta_code("TQT_R1_V31_0042", "R1")["nombre"], "TQT-R1-V31-0042")  # guiones bajos
        self.assertEqual(parse_tarjeta_code("TQT-R1-V30-42", "R1")["numero"], "0042")               # zfill
        self.assertEqual(parse_tarjeta_code("88", "R2", "30")["nombre"], "TQT-R2-V30-0088")          # solo número
        self.assertEqual(parse_tarjeta_code("88", "R2", "31")["nombre"], "TQT-R2-V31-0088")
        self.assertEqual(VERSION_DEFAULT, "30")

    def test_05_parseo_rechazos(self):
        for basura in ("PCB-MAIN-001", "", "RANDOM", "TQT-R4-V30-0011", "TQT-R1-V30-00112", "TQT-R1-0011"):
            self.assertIsNone(parse_tarjeta_code(basura, "R1"), basura)
        self.assertIsNone(parse_tarjeta_code("88", "R1"))     # solo número únicamente vale para respaldo
        self.assertIsNone(parse_tarjeta_code("88", None))

    # ---------------------------------------------------------------- estados derivados
    def test_06_estado_general_igual_a_la_formula_de_excel(self):
        casos = [
            (["PENDIENTE"] * 5, "PENDIENTE"),
            (["OK"] * 5, "LIBERADO"),
            (["OK", "NO APLICA", "OK", "NO APLICA", "OK"], "LIBERADO"),
            (["NO APLICA"] * 5, "LIBERADO"),
            (["OK", "OK", "PENDIENTE", "PENDIENTE", "PENDIENTE"], "EN PROCESO"),
            (["OK", "OK", "RETRABAJO", "OK", "OK"], "RETRABAJO"),
            (["OK", "FALLA", "RETRABAJO", "OK", "OK"], "DETENIDO"),   # FALLA gana a RETRABAJO
            (["FALLA", "PENDIENTE", "PENDIENTE", "PENDIENTE", "PENDIENTE"], "DETENIDO"),
        ]
        for estados, esperado in casos:
            self.assertEqual(derivar_estado_general(estados), esperado, estados)

    def test_07_vocabulario_canonico_y_alias(self):
        for viejo, nuevo in (("APROBADO", "OK"), ("DEFECTUOSO", "FALLA"), ("defectuosa", "FALLA"), ("Reproceso", "RETRABAJO"),
                             ("no aplica", "NO APLICA"), ("N/A", "NO APLICA"), ("", "PENDIENTE"), ("PENDIENTE", "PENDIENTE")):
            self.assertEqual(normalizar_estado_prueba(viejo), nuevo, viejo)
        with self.assertRaises(ValueError):
            normalizar_estado_prueba("QUIZAS")
        self.assertEqual(estado_pcb_desde_prueba("OK"), "FUNCIONAL")
        self.assertEqual(estado_pcb_desde_prueba("FALLA"), "FALLA")
        for otro in ("PENDIENTE", "RETRABAJO", "NO APLICA", None):
            self.assertEqual(estado_pcb_desde_prueba(otro), "PENDIENTE", otro)


if __name__ == "__main__":
    unittest.main()
