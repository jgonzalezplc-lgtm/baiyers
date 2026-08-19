import unittest
from unittest.mock import patch

from app.services.workflow_conversational import compilar_a_grafo
from app.services.workflow_engine import validar_grafo
from app.services.workflow_proceso_slots import (
    MAX_INTENTOS_POR_SLOT,
    SLOTS_PROCESO,
    aplicar_extraccion,
    compilar_slots_a_etapas,
    estado_inicial,
    procesar_turno,
    siguiente_slot,
)


def _extraccion(slots=None, reglas=None, entendido=True, aclaracion=""):
    return {
        "slots": slots or [],
        "reglas_autorizacion": reglas or [],
        "entendido": entendido,
        "aclaracion": aclaracion,
    }


class SiguienteSlotTest(unittest.TestCase):
    def test_arranca_por_el_primer_slot_del_proceso(self):
        self.assertEqual(siguiente_slot(estado_inicial())["clave"], SLOTS_PROCESO[0]["clave"])

    def test_salta_los_ya_resueltos_o_no_aplicables(self):
        ficha = estado_inicial()
        ficha[0]["estado"] = "resuelto"
        ficha[1]["estado"] = "no_aplica"
        self.assertEqual(siguiente_slot(ficha)["clave"], ficha[2]["clave"])

    def test_devuelve_none_cuando_no_queda_nada_pendiente(self):
        ficha = estado_inicial()
        for s in ficha:
            s["estado"] = "resuelto"
        self.assertIsNone(siguiente_slot(ficha))


class AplicarExtraccionTest(unittest.TestCase):
    def test_una_respuesta_puede_llenar_varios_slots(self):
        """El caso que motivó el rediseño: si el usuario contesta la primera
        pregunta con todo el proceso, no se le vuelve a preguntar el resto."""
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "cotizador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": "ana@abc.cl"}]},
            {"clave": "autorizador", "estado": "resuelto", "personas": [{"nombre": "Luis", "email": ""}]},
            {"clave": "comprador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": "ana@abc.cl"}]},
        ]))
        por_clave = {s["clave"]: s for s in ficha}
        self.assertEqual(por_clave["cotizador"]["estado"], "resuelto")
        self.assertEqual(por_clave["autorizador"]["estado"], "resuelto")
        self.assertEqual(por_clave["comprador"]["estado"], "resuelto")
        # El siguiente pendiente es el primero que la respuesta NO cubrió.
        self.assertEqual(siguiente_slot(ficha)["clave"], "revisor")

    def test_rol_se_asigna_por_significado_y_no_por_parecido_de_texto(self):
        """'Coti Zamorano' con correo cotiz@abc.cl es AUTORIZADORA. Ningún
        matching por substring puede degradarla a cotizadora."""
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "autorizador", "estado": "resuelto",
             "personas": [{"nombre": "Coti Zamorano", "email": "cotiz@abc.cl"}]},
        ]))
        por_clave = {s["clave"]: s for s in ficha}
        self.assertEqual(por_clave["autorizador"]["personas"][0]["nombre"], "Coti Zamorano")
        self.assertEqual(por_clave["cotizador"]["personas"], [])
        self.assertEqual(por_clave["cotizador"]["estado"], "pendiente")

    def test_descarta_email_invalido_pero_conserva_el_nombre(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "cotizador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": "no-es-mail"}]},
        ]))
        self.assertEqual(ficha[0]["personas"], [{"nombre": "Ana", "email": ""}])

    def test_ignora_personas_totalmente_vacias_y_claves_desconocidas(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "cotizador", "estado": "resuelto", "personas": [{"nombre": "", "email": ""}]},
            {"clave": "inventada", "estado": "resuelto", "personas": [{"nombre": "X", "email": ""}]},
        ]))
        self.assertEqual(ficha[0]["personas"], [])
        self.assertEqual({s["clave"] for s in ficha}, {s["clave"] for s in SLOTS_PROCESO})

    def test_es_aditivo_y_no_duplica_a_la_misma_persona(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "autorizador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": "ana@abc.cl"}]},
        ]))
        ficha = aplicar_extraccion(ficha, _extraccion([
            {"clave": "autorizador", "estado": "resuelto", "personas": [
                {"nombre": "Ana", "email": "ana@abc.cl"},
                {"nombre": "Luis", "email": "luis@abc.cl"},
            ]},
        ]))
        por_clave = {s["clave"]: s for s in ficha}
        self.assertEqual([p["nombre"] for p in por_clave["autorizador"]["personas"]], ["Ana", "Luis"])

    def test_no_aplica_no_puede_borrar_gente_ya_asignada(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "revisor", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": ""}]},
        ]))
        ficha = aplicar_extraccion(ficha, _extraccion([
            {"clave": "revisor", "estado": "no_aplica", "personas": []},
        ]))
        por_clave = {s["clave"]: s for s in ficha}
        self.assertEqual(por_clave["revisor"]["estado"], "resuelto")
        self.assertEqual(len(por_clave["revisor"]["personas"]), 1)

    def test_montos_coloquiales_ya_normalizados_marcan_el_slot(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion(
            reglas=[{"desde": 0, "hasta": 500000, "descripcion": "Ana"},
                    {"desde": 500001, "hasta": 0, "descripcion": "Gerencia"}],
        ))
        por_clave = {s["clave"]: s for s in ficha}
        self.assertEqual(por_clave["reglas_monto"]["estado"], "resuelto")
        # 0 en el schema significa "sin límite" y hacia afuera viaja como None.
        self.assertEqual(por_clave["reglas_monto"]["reglas"][0]["desde"], None)
        self.assertEqual(por_clave["reglas_monto"]["reglas"][1]["hasta"], None)


class CompilarSlotsTest(unittest.TestCase):
    def test_produce_un_grafo_valido_para_el_motor(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "cotizador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": "ana@abc.cl"}]},
            {"clave": "autorizador", "estado": "resuelto", "personas": [{"nombre": "Luis", "email": "luis@abc.cl"}]},
            {"clave": "comprador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": "ana@abc.cl"}]},
        ]))
        etapas, reglas = compilar_slots_a_etapas(ficha)
        self.assertEqual([e["tipo"] for e in etapas], ["tarea_humana", "autorizacion", "emision_oc"])
        nodos, conexiones = compilar_a_grafo(etapas, reglas)
        self.assertEqual(validar_grafo(nodos, conexiones), [])

    def test_los_slots_no_aplicables_no_generan_etapa(self):
        ficha = aplicar_extraccion(estado_inicial(), _extraccion([
            {"clave": "cotizador", "estado": "resuelto", "personas": [{"nombre": "Ana", "email": ""}]},
            {"clave": "homologador", "estado": "no_aplica", "personas": []},
        ]))
        etapas, _ = compilar_slots_a_etapas(ficha)
        self.assertEqual([e["nombre"] for e in etapas], ["Cotizar"])


class ProcesarTurnoTest(unittest.TestCase):
    def test_primer_turno_no_llama_al_modelo(self):
        with patch("app.services.workflow_proceso_slots.extraer_de_respuesta") as fake:
            r = procesar_turno("", None, "")
        fake.assert_not_called()
        self.assertFalse(r["completo"])
        self.assertEqual(r["clave_pregunta"], SLOTS_PROCESO[0]["clave"])

    def test_una_respuesta_util_siempre_avanza_de_pregunta(self):
        """Regresión directa del bug: 'Valeria Tapia, admin@reveniu.com' como
        respuesta a '¿quién cotiza?' avanza — antes repetía la pregunta
        para siempre porque el texto no contenía la palabra 'cotizar'."""
        with patch("app.services.workflow_proceso_slots.extraer_de_respuesta",
                   return_value=_extraccion([
                       {"clave": "cotizador", "estado": "resuelto",
                        "personas": [{"nombre": "Valeria Tapia", "email": "admin@reveniu.com"}]},
                   ])):
            r = procesar_turno("Valeria Tapia, admin@reveniu.com", estado_inicial(), "")
        self.assertNotEqual(r["clave_pregunta"], "cotizador")
        self.assertEqual(r["aclaracion"], "")

    def test_respuesta_incomprensible_repregunta_una_vez_y_luego_avanza(self):
        ficha = estado_inicial()
        with patch("app.services.workflow_proceso_slots.extraer_de_respuesta",
                   return_value=_extraccion(entendido=False, aclaracion="¿Quién cotiza?")):
            primero = procesar_turno("???", ficha, "")
            self.assertEqual(primero["clave_pregunta"], "cotizador")
            self.assertEqual(primero["aclaracion"], "¿Quién cotiza?")

            segundo = procesar_turno("???", primero["slots"], "")
        # Al agotar los intentos el slot se salta: la entrevista nunca se traba.
        self.assertNotEqual(segundo["clave_pregunta"], "cotizador")

    def test_la_entrevista_termina_aunque_el_modelo_nunca_entienda_nada(self):
        """Garantía dura contra loops: con extracción siempre vacía, la
        entrevista igual llega al final en un número acotado de turnos."""
        estado, turnos = None, 0
        with patch("app.services.workflow_proceso_slots.extraer_de_respuesta",
                   return_value=_extraccion(entendido=False, aclaracion="no entendí")):
            r = procesar_turno("", None, "")
            while not r["completo"] and r["clave_pregunta"]:
                r = procesar_turno("bla", r["slots"], "")
                turnos += 1
                self.assertLessEqual(turnos, len(SLOTS_PROCESO) * MAX_INTENTOS_POR_SLOT)
        self.assertEqual(r["clave_pregunta"], "")

    def test_al_completar_devuelve_grafo_valido_y_responsables(self):
        with patch("app.services.workflow_proceso_slots.extraer_de_respuesta",
                   return_value=_extraccion([
                       {"clave": c, "estado": "resuelto",
                        "personas": [{"nombre": "Ana", "email": "ana@abc.cl"}]}
                       for c in ("cotizador", "revisor", "autorizador", "homologador", "comprador")
                   ] + [{"clave": "reglas_monto", "estado": "no_aplica", "personas": []}])):
            r = procesar_turno("Ana hace todo el proceso, ana@abc.cl", estado_inicial(), "")
        self.assertTrue(r["completo"])
        self.assertEqual(validar_grafo(r["nodos"], r["conexiones"]), [])
        self.assertEqual([x["email"] for x in r["responsables_detectados"]], ["ana@abc.cl"])
        self.assertIn("Cotizar", r["resumen"])

    def test_ficha_manipulada_desde_el_cliente_se_sanea(self):
        r = procesar_turno("", [{"clave": "inventada", "estado": "resuelto"}], "")
        self.assertEqual({s["clave"] for s in r["slots"]}, {s["clave"] for s in SLOTS_PROCESO})

    def test_extraccion_sin_api_key_devuelve_vacio_seguro(self):
        """Sin Gemini disponible la entrevista no se cae: extrae nada y deja
        que el avance determinístico haga su trabajo."""
        from app.services import workflow_proceso_slots as mod

        with patch.object(mod, "extraer_de_respuesta", wraps=mod.extraer_de_respuesta):
            with patch("app.config.settings") as settings:
                settings.gemini_api_key = ""
                salida = mod.extraer_de_respuesta("Ana cotiza", "¿Quién cotiza?", "")
        self.assertEqual(salida["slots"], [])
        self.assertTrue(salida["entendido"])


if __name__ == "__main__":
    unittest.main()
