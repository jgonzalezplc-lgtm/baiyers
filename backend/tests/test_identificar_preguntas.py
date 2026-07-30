import unittest

from app.routers.identificar import _excluir_servicios_de_proyecto, _normalizar_preguntas


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

    def test_proyecto_excluye_servicios_generados(self):
        resultado = _excluir_servicios_de_proyecto({"es_proyecto": True, "lista_items": [
            {"nombre_tecnico": "Panel", "categoria": "electrico"},
            {"nombre_tecnico": "Ingeniería", "categoria": "servicio"},
        ], "revision_cubicacion": {"items": [
            {"nombre_tecnico": "Panel", "categoria": "electrico"},
            {"nombre_tecnico": "Ingeniería", "categoria": "servicio"},
        ]}})
        self.assertEqual([i["nombre_tecnico"] for i in resultado["lista_items"]], ["Panel"])
        self.assertEqual([i["nombre_tecnico"] for i in resultado["revision_cubicacion"]["items"]], ["Panel"])

    def test_cotizacion_explicita_de_servicio_no_se_filtra(self):
        resultado = _excluir_servicios_de_proyecto({"es_proyecto": False, "lista_items": [{"nombre_tecnico": "Consultoría", "categoria": "servicio"}]})
        self.assertEqual(len(resultado["lista_items"]), 1)


if __name__ == "__main__":
    unittest.main()
