import unittest

from app.services.workflow_conversational import compilar_a_grafo, interpretar_descripcion
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


if __name__ == "__main__":
    unittest.main()
