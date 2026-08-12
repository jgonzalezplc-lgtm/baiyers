import json
import unittest
from unittest.mock import MagicMock, patch

from app.services.workflow_conversational import compilar_a_grafo, deduplicar_responsables, interpretar_correccion, interpretar_descripcion
from app.services.workflow_engine import validar_grafo, siguiente_nodo


class CompilarGrafoTest(unittest.TestCase):
    def test_sin_etapas_produce_grafo_valido(self):
        nodos, conexiones = compilar_a_grafo([], [])
        self.assertEqual(validar_grafo(nodos, conexiones), [])

    def test_secuencia_simple_sin_reglas_de_monto(self):
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"]},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, [])
        self.assertEqual(validar_grafo(nodos, conexiones), [])
        self.assertEqual(siguiente_nodo(conexiones, "n1", "aprobado"), "fin")
        self.assertEqual(siguiente_nodo(conexiones, "n1", "rechazado"), "n0")

    def test_ejemplo_del_prompt_original(self):
        """'Los cotizadores preparan la comparación. Después la revisa el jefe
        de operaciones. Las compras menores a $1.000.000 las autoriza él
        mismo, pero sobre ese monto también debe aprobar finanzas.
        Finalmente compras emite la orden de compra.'"""
        etapas = [
            {"nombre": "Preparar comparación", "tipo": "tarea_humana", "roles": ["cotizador"]},
            {"nombre": "Revisión de Operaciones", "tipo": "revision", "roles": ["revisor"]},
            {"nombre": "Autorización", "tipo": "autorizacion", "roles": ["autorizador"]},
            {"nombre": "Emitir OC", "tipo": "emision_oc", "roles": ["comprador"]},
        ]
        reglas = [
            {"hasta": 1000000, "desde": None, "descripcion": "jefe de operaciones"},
            {"hasta": None, "desde": 1000001, "descripcion": "jefe de operaciones y finanzas"},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, reglas)
        self.assertEqual(validar_grafo(nodos, conexiones), [])

        # El tramo bajo aprobado va al siguiente paso real (Emitir OC), NO al
        # tramo alto — este fue el bug real que se encontró y se corrigió.
        self.assertEqual(siguiente_nodo(conexiones, "n2_t0", "aprobado"), "n3")
        self.assertEqual(siguiente_nodo(conexiones, "n2_t1", "aprobado"), "n3")
        # Un rechazo en cualquier tramo vuelve a la etapa anterior (revisión),
        # no al otro tramo.
        self.assertEqual(siguiente_nodo(conexiones, "n2_t0", "rechazado"), "n1")
        self.assertEqual(siguiente_nodo(conexiones, "n2_t1", "rechazado"), "n1")

    def test_tramos_de_monto_al_final_de_la_secuencia(self):
        """Si la autorización con tramos es la ÚLTIMA etapa, ambos tramos
        aprobados deben ir a 'fin', no quedar sueltos."""
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"]},
        ]
        reglas = [
            {"hasta": 500000, "desde": None, "descripcion": "jefe"},
            {"hasta": None, "desde": 500001, "descripcion": "gerencia"},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, reglas)
        self.assertEqual(validar_grafo(nodos, conexiones), [])
        self.assertEqual(siguiente_nodo(conexiones, "n1_t0", "aprobado"), "fin")
        self.assertEqual(siguiente_nodo(conexiones, "n1_t1", "aprobado"), "fin")

    def test_tres_tramos_de_monto(self):
        """Hasta $500.000 / $500.001-$5.000.000 / sobre $5.000.000 — el
        ejemplo de tres niveles del spec original."""
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"]},
            {"nombre": "Emitir OC", "tipo": "emision_oc", "roles": ["comprador"]},
        ]
        reglas = [
            {"hasta": 500000, "desde": None, "descripcion": "jefe de área"},
            {"hasta": 5000000, "desde": 500001, "descripcion": "jefe de área y finanzas"},
            {"hasta": None, "desde": 5000001, "descripcion": "finanzas y gerencia general"},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, reglas)
        self.assertEqual(validar_grafo(nodos, conexiones), [])
        for tramo in ("n1_t0", "n1_t1", "n1_t2"):
            self.assertEqual(siguiente_nodo(conexiones, tramo, "aprobado"), "n2")
            self.assertEqual(siguiente_nodo(conexiones, tramo, "rechazado"), "n0")

    def test_una_sola_regla_no_expande_a_tramos(self):
        """Con una sola regla de monto no hay nada que ramificar — debe
        comportarse como autorización simple."""
        etapas = [{"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"]}]
        nodos, conexiones = compilar_a_grafo(etapas, [{"hasta": 1000000, "desde": None, "descripcion": "jefe"}])
        self.assertEqual(validar_grafo(nodos, conexiones), [])
        self.assertEqual(siguiente_nodo(conexiones, "n0", "aprobado"), "fin")


class DeduplicarResponsablesTest(unittest.TestCase):
    """Regresión: si la misma persona aparece en varias etapas (ej: revisa
    Y autoriza), debe quedar con TODOS esos roles acumulados — quedarse
    solo con los de la primera etapa la dejaba sin asignar en el resto."""

    def test_misma_persona_en_dos_etapas_acumula_ambos_roles(self):
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"], "responsables": []},
            {"nombre": "Revisar", "tipo": "revision", "roles": ["revisor"],
             "responsables": [{"nombre": "Joaquín", "email": "joaquin@usach.cl"}]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"],
             "responsables": [{"nombre": "Joaquín", "email": "joaquin@usach.cl"}]},
        ]
        detectados = deduplicar_responsables(etapas)
        self.assertEqual(len(detectados), 1)
        self.assertEqual(set(detectados[0]["roles"]), {"revisor", "autorizador"})

    def test_personas_distintas_no_se_mezclan(self):
        etapas = [
            {"nombre": "Revisar", "tipo": "revision", "roles": ["revisor"],
             "responsables": [{"nombre": "Ignacio", "email": "hola@claria.cc"}]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"],
             "responsables": [{"nombre": "Joaquín", "email": "joaquin@usach.cl"}]},
        ]
        detectados = deduplicar_responsables(etapas)
        self.assertEqual(len(detectados), 2)
        self.assertEqual(next(d for d in detectados if d["email"] == "hola@claria.cc")["roles"], ["revisor"])
        self.assertEqual(next(d for d in detectados if d["email"] == "joaquin@usach.cl")["roles"], ["autorizador"])

    def test_sin_email_dedupe_por_nombre(self):
        etapas = [
            {"nombre": "Revisar", "tipo": "revision", "roles": ["revisor"],
             "responsables": [{"nombre": "María", "email": ""}]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"],
             "responsables": [{"nombre": "María", "email": ""}]},
        ]
        detectados = deduplicar_responsables(etapas)
        self.assertEqual(len(detectados), 1)
        self.assertEqual(set(detectados[0]["roles"]), {"revisor", "autorizador"})


class InterpretarDescripcionSinRedTest(unittest.TestCase):
    """Regresión: `simple()` (detección de "yo hago todo") corre ANTES de
    llamar a Gemini y no debe depender de `re` importado dentro de la
    función — un `import re` local ahí rompía el closure con
    UnboundLocalError, tumbando /api/workflows/interpretar con 500 incluso
    para el caso más simple, sin llegar a tocar la red."""

    def test_declaracion_solo_no_lanza_ni_llama_a_gemini(self):
        r = interpretar_descripcion("Yo hago todo")
        self.assertTrue(r["requiere_aclaracion"])
        self.assertEqual(r["etapas"], [])

    def test_descripcion_normal_no_lanza_por_scope_de_re(self):
        # No verificamos el contenido (requiere Gemini/API key); solo que
        # la función no explota por un NameError de scoping antes de llegar
        # a la llamada real al modelo.
        try:
            interpretar_descripcion("Yo cotizo, mi jefa revisa y autoriza todo.")
        except UnboundLocalError as e:
            self.fail(f"interpretar_descripcion no debe fallar por scope de 're': {e}")


class InterpretarCorreccionTest(unittest.TestCase):
    """Correcciones sobre un grafo ya existente — el LLM propone operaciones,
    nunca el grafo completo. Todo mockeado, sin red real."""

    GRAFO = {
        "nodos": [
            {"id": "inicio", "tipo": "inicio", "nombre": "Inicio"},
            {"id": "n0", "tipo": "tarea_humana", "nombre": "Cotizar", "roles": ["cotizador"]},
            {"id": "n1", "tipo": "autorizacion", "nombre": "Autorizar", "roles": ["autorizador"], "resultados": ["aprobado", "rechazado"]},
            {"id": "fin", "tipo": "fin", "nombre": "Fin"},
        ],
        "conexiones": [
            {"origen_nodo_id": "inicio", "destino_nodo_id": "n0"},
            {"origen_nodo_id": "n0", "destino_nodo_id": "n1"},
            {"origen_nodo_id": "n1", "destino_nodo_id": "fin", "resultado": "aprobado"},
        ],
    }

    def test_sin_api_key_devuelve_vacio_seguro(self):
        with patch("app.config.settings.gemini_api_key", ""):
            r = interpretar_correccion("cambia el nombre", self.GRAFO)
        self.assertEqual(r["operaciones"], [])
        self.assertTrue(r["requiere_aclaracion"])

    def test_descripcion_vacia_no_llama_a_gemini(self):
        r = interpretar_correccion("   ", self.GRAFO)
        self.assertEqual(r["operaciones"], [])

    def test_operacion_con_nodo_id_inexistente_se_descarta(self):
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "Renombro la etapa",
                "operaciones": [{"tipo": "renombrar_nodo", "nodo_id": "n99-no-existe", "nombre": "X"}],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("cambia el nombre de la etapa inexistente", self.GRAFO)
        self.assertEqual(r["operaciones"], [])

    def test_agregar_nodo_con_tipo_invalido_se_descarta(self):
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "", "operaciones": [{"tipo": "agregar_nodo", "tipo_nodo": "algo_inventado", "nombre": "X", "roles": ["autorizador"]}],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("agrega una etapa rara", self.GRAFO)
        self.assertEqual(r["operaciones"], [])

    def test_operacion_valida_se_mantiene(self):
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "Agrego autorización de finanzas",
                "operaciones": [
                    {"tipo": "agregar_nodo", "tipo_nodo": "autorizacion", "nombre": "Autorizar Finanzas", "roles": ["autorizador"]},
                    {"tipo": "renombrar_nodo", "nodo_id": "n1", "nombre": "Autorizar jefatura"},
                ],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("agrega que finanzas también autorice y renombra la etapa n1", self.GRAFO)
        self.assertEqual(len(r["operaciones"]), 2)

    def test_conectar_nodo_recien_agregado_en_la_misma_correccion(self):
        """Bug real: conectar una etapa que se agrega en la misma corrección
        se descartaba porque se validaba contra el grafo previo, sin el id
        nuevo — el usuario veía la tarjeta aparecer sin conectarse a nada."""
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "Agrego homologación entre autorizar y fin",
                "operaciones": [
                    {"tipo": "agregar_nodo", "nodo_id": "nuevo_homologacion", "tipo_nodo": "homologacion", "nombre": "Homologar proveedores", "roles": ["revisor"]},
                    {"tipo": "desconectar", "origen_nodo_id": "n1", "destino_nodo_id": "fin", "resultado": "aprobado"},
                    {"tipo": "conectar", "origen_nodo_id": "n1", "destino_nodo_id": "nuevo_homologacion", "resultado": "aprobado"},
                    {"tipo": "conectar", "origen_nodo_id": "nuevo_homologacion", "destino_nodo_id": "fin"},
                ],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("agrega homologación de proveedores después de autorizar", self.GRAFO)
        self.assertEqual(len(r["operaciones"]), 4)
        tipos = [op["tipo"] for op in r["operaciones"]]
        self.assertEqual(tipos, ["agregar_nodo", "desconectar", "conectar", "conectar"])
        conectar_ops = [op for op in r["operaciones"] if op["tipo"] == "conectar"]
        self.assertTrue(any(op["destino_nodo_id"] == "nuevo_homologacion" for op in conectar_ops))
        self.assertTrue(any(op["origen_nodo_id"] == "nuevo_homologacion" for op in conectar_ops))

    def test_agregar_nodo_sin_id_del_modelo_genera_uno_disponible_para_conectar(self):
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "", "operaciones": [
                    {"tipo": "agregar_nodo", "tipo_nodo": "revision", "nombre": "Revisión extra"},
                    {"tipo": "conectar", "origen_nodo_id": "n0", "destino_nodo_id": "n1"},
                ],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("agrega una revisión", self.GRAFO)
        self.assertEqual(len(r["operaciones"]), 2)
        self.assertTrue(r["operaciones"][0]["nodo_id"])

    def test_conectar_a_id_inventado_no_agregado_sigue_descartandose(self):
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "", "operaciones": [
                    {"tipo": "conectar", "origen_nodo_id": "n0", "destino_nodo_id": "nodo_que_no_existe"},
                ],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("conecta con algo que no existe", self.GRAFO)
        self.assertEqual(r["operaciones"], [])

    def test_roles_invalidos_se_descartan(self):
        with patch("app.config.settings.gemini_api_key", "x"), \
             patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as MockModel:
            instancia = MockModel.return_value
            instancia.generate_content.return_value = MagicMock(text=json.dumps({
                "resumen": "", "operaciones": [{"tipo": "cambiar_roles", "nodo_id": "n1", "roles": ["rol_inventado"]}],
                "requiere_aclaracion": False, "preguntas": [],
            }))
            r = interpretar_correccion("cambia el rol", self.GRAFO)
        self.assertEqual(r["operaciones"], [])


if __name__ == "__main__":
    unittest.main()
