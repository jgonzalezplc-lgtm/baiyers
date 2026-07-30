import unittest

from app.routers.identificar import _normalizar_preguntas


class PreguntasCubicacionTest(unittest.TestCase):
    def test_ids_no_dependen_de_la_posicion(self):
        primera = _normalizar_preguntas(["¿Cuáles son las dimensiones?", "¿Qué material usarás?"])
        segunda = _normalizar_preguntas(["¿Cuántos pisos tendrá?", "¿Qué cimentación usarás?"])
        self.assertNotEqual(primera[0]["id"], segunda[0]["id"])
        self.assertNotEqual(primera[1]["id"], segunda[1]["id"])

    def test_misma_pregunta_conserva_id(self):
        a = _normalizar_preguntas(["¿Cuántos pisos tendrá?"])[0]["id"]
        b = _normalizar_preguntas(["¿Cuántos pisos tendrá?"])[0]["id"]
        self.assertEqual(a, b)

    def test_limita_a_tres_y_completa_objetos(self):
        preguntas = _normalizar_preguntas([{"texto": f"Pregunta {i}"} for i in range(5)])
        self.assertEqual(len(preguntas), 3)
        self.assertTrue(all(p["id"] and p["tipo"] == "texto" for p in preguntas))


if __name__ == "__main__":
    unittest.main()
