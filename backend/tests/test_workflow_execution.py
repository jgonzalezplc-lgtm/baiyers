import unittest

from app.services.workflow_conversational import compilar_a_grafo
from app.services.workflow_execution import _nodo_autorizacion_para_monto


class NodoAutorizacionParaMontoTest(unittest.TestCase):
    def test_autorizacion_simple_sin_tramos(self):
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"]},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, [])
        nodo = _nodo_autorizacion_para_monto(nodos, conexiones, 100)
        self.assertIsNotNone(nodo)
        self.assertEqual(nodo["id"], "n1")

    def test_tramos_elige_el_tramo_correcto_por_monto(self):
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

        self.assertEqual(_nodo_autorizacion_para_monto(nodos, conexiones, 100000)["id"], "n1_t0")
        self.assertEqual(_nodo_autorizacion_para_monto(nodos, conexiones, 1000000)["id"], "n1_t1")
        self.assertEqual(_nodo_autorizacion_para_monto(nodos, conexiones, 9000000)["id"], "n1_t2")

    def test_revision_previa_es_transparente(self):
        """Una etapa de revisión antes de la autorización no debe frenar la
        búsqueda — se camina de largo hasta el primer nodo de autorización."""
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"]},
            {"nombre": "Revisar", "tipo": "revision", "roles": ["revisor"]},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"]},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, [])
        nodo = _nodo_autorizacion_para_monto(nodos, conexiones, 100)
        self.assertEqual(nodo["id"], "n2")

    def test_sin_etapa_de_autorizacion_no_encuentra_nada(self):
        etapas = [{"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"]}]
        nodos, conexiones = compilar_a_grafo(etapas, [])
        self.assertIsNone(_nodo_autorizacion_para_monto(nodos, conexiones, 100))


if __name__ == "__main__":
    unittest.main()
