import unittest

from app.services.rut import formatear_rut, normalizar_rut, validar_rut


class RutTest(unittest.TestCase):
    def test_rut_valido_con_puntos_y_guion(self):
        self.assertTrue(validar_rut("76.123.456-0"))

    def test_rut_valido_sin_formato(self):
        self.assertTrue(validar_rut("761234560"))

    def test_rut_con_digito_verificador_cinco(self):
        self.assertTrue(validar_rut("12345678-5"))

    def test_rut_invalido_por_digito_verificador(self):
        self.assertFalse(validar_rut("76.123.456-7"))

    def test_rut_muy_corto_es_invalido(self):
        self.assertFalse(validar_rut("1-9"))

    def test_rut_vacio_es_invalido(self):
        self.assertFalse(validar_rut(""))

    def test_rut_con_letras_en_el_cuerpo_es_invalido(self):
        self.assertFalse(validar_rut("7A123456-0"))

    def test_normalizar_quita_puntos_guion_y_espacios(self):
        self.assertEqual(normalizar_rut(" 76.123.456-0 "), "761234560")

    def test_formatear_produce_formato_estandar(self):
        self.assertEqual(formatear_rut("761234560"), "76.123.456-0")

    def test_formatear_rut_de_siete_digitos(self):
        self.assertEqual(formatear_rut("76123454"), "7.612.345-4")


if __name__ == "__main__":
    unittest.main()
