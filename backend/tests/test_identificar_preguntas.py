import unittest

from app.routers.identificar import (
    _es_error_modelo_no_disponible,
    _excluir_servicios_de_proyecto,
    _modelos_identificacion,
    _normalizar_preguntas,
    _normalizar_revision_generada,
    _preguntas_itemizado_faltantes,
)


class PreguntasCubicacionTest(unittest.TestCase):
    def test_cubicacion_prefiere_modelo_actual_y_conserva_fallback(self):
        self.assertEqual(
            _modelos_identificacion(True),
            ["gemini-3.5-flash-lite", "gemini-2.5-flash"],
        )

    def test_flujo_antiguo_conserva_modelo_estable(self):
        self.assertEqual(_modelos_identificacion(False), ["gemini-2.5-flash"])

    def test_fallback_solo_para_modelo_no_disponible(self):
        self.assertTrue(_es_error_modelo_no_disponible(Exception("404 model no longer available")))
        self.assertFalse(_es_error_modelo_no_disponible(Exception("quota exceeded")))

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

    def test_proyecto_general_construye_revision_por_item(self):
        resultado = _normalizar_revision_generada({"es_proyecto": True, "lista_items": [{
            "nombre_tecnico": "Cemento 42,5 kg", "categoria": "construccion", "cantidad": 18,
            "cantidad_neta": 750, "unidad": "kg", "unidad_compra": "saco",
            "cantidad_comercial": 765, "calculo": "0,75 m3 × 300 kg/m3 ÷ 42,5 kg por saco",
            "supuestos": ["radier de 10 cm"], "advertencias": ["validar suelo"],
        }]})
        revision = resultado["revision_cubicacion"]
        self.assertEqual(revision["items"][0]["cantidad_compra"], 18)
        self.assertIn("42,5 kg", revision["items"][0]["calculo"])
        self.assertEqual(revision["supuestos"], ["radier de 10 cm"])

    def test_itemizado_pregunta_cada_cantidad_y_unidad_faltante(self):
        preguntas = _preguntas_itemizado_faltantes({"lista_items": [
            {"nombre_tecnico": "Cable", "partida": "Tableros", "cantidad": None, "unidad": None},
            {"nombre_tecnico": "Generador", "partida": "Grupo generador", "cantidad": 1, "unidad": ""},
        ]})
        self.assertEqual([p["id"] for p in preguntas], [
            "item_0_cantidad", "item_0_unidad", "item_1_unidad",
        ])
        self.assertIn("Tableros", preguntas[0]["texto"])


if __name__ == "__main__":
    unittest.main()
