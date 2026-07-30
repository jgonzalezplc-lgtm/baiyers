import unittest

from app.routers.aprobaciones import _texto_notificacion_lista


class TextoNotificacionListaTest(unittest.TestCase):
    def test_rechazo_no_se_anuncia_como_aprobacion(self):
        tipo, titulo, cuerpo = _texto_notificacion_lista("rechazar", "Paneles solares")
        self.assertEqual(tipo, "cotizacion_rechazada")
        self.assertEqual(titulo, "Cotización rechazada")
        self.assertIn("rechazó", cuerpo)
        self.assertNotIn("aprob", cuerpo.lower())

    def test_aprobacion_con_observaciones_es_distinta(self):
        tipo, titulo, _ = _texto_notificacion_lista("aprobar_con_observaciones", "Lista")
        self.assertEqual(tipo, "cotizacion_observada")
        self.assertIn("observaciones", titulo.lower())


if __name__ == "__main__":
    unittest.main()
