import unittest

from app.services.workflow_automation import validar_automatizacion
from app.services.workflow_comunicaciones_default import reglas_por_defecto
from app.services.workflow_conversational import compilar_a_grafo
from app.services.workflow_service import mapear_asignaciones_por_tarjeta


def _grafo_tipico():
    etapas = [
        {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"], "responsables": []},
        {"nombre": "Revisar", "tipo": "revision", "roles": ["revisor"], "responsables": []},
        {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"], "responsables": []},
        {"nombre": "Emitir OC", "tipo": "emision_oc", "roles": ["comprador"], "responsables": []},
    ]
    return compilar_a_grafo(etapas, [])


class MapearAsignacionesTest(unittest.TestCase):
    def test_cada_tarjeta_humana_queda_con_su_responsable(self):
        """El bug reportado: el ciclo se creaba con el roster de roles lleno
        pero TODAS las tarjetas decian 'Nadie asignado todavia'."""
        nodos, _ = _grafo_tipico()
        filas = mapear_asignaciones_por_tarjeta(nodos, {
            "cotizador": ["r1"], "revisor": ["r2"],
            "autorizador": ["r3"], "comprador": ["r4"],
        })
        con_rol = [n for n in nodos if n.get("roles")]
        self.assertEqual(len(filas), len(con_rol))
        self.assertEqual({f["nodo_id"] for f in filas}, {n["id"] for n in con_rol})

    def test_inicio_y_fin_no_reciben_responsables(self):
        nodos, _ = _grafo_tipico()
        filas = mapear_asignaciones_por_tarjeta(nodos, {"cotizador": ["r1"]})
        self.assertNotIn("inicio", {f["nodo_id"] for f in filas})
        self.assertNotIn("fin", {f["nodo_id"] for f in filas})

    def test_una_persona_en_varios_roles_se_asigna_a_cada_tarjeta(self):
        """'yo cotizo y tambien autorizo' debe quedar en ambas tarjetas."""
        nodos, _ = _grafo_tipico()
        filas = mapear_asignaciones_por_tarjeta(nodos, {"cotizador": ["r1"], "autorizador": ["r1"]})
        self.assertEqual(len([f for f in filas if f["responsable_id"] == "r1"]), 2)

    def test_varias_personas_en_un_rol_van_en_paralelo(self):
        """'individual' borra las demas asignaciones del rol: con dos
        autorizadores dejaria solo al ultimo."""
        nodos, _ = _grafo_tipico()
        filas = mapear_asignaciones_por_tarjeta(nodos, {"autorizador": ["r1", "r2"]})
        self.assertEqual({f["modo"] for f in filas}, {"paralelo"})
        self.assertEqual(len(filas), 2)

    def test_una_sola_persona_queda_individual(self):
        nodos, _ = _grafo_tipico()
        filas = mapear_asignaciones_por_tarjeta(nodos, {"autorizador": ["r1"]})
        self.assertEqual(filas[0]["modo"], "individual")

    def test_rol_sin_nadie_no_inventa_asignacion(self):
        nodos, _ = _grafo_tipico()
        filas = mapear_asignaciones_por_tarjeta(nodos, {"cotizador": []})
        self.assertEqual(filas, [])

    def test_nodo_sin_id_se_ignora(self):
        self.assertEqual(
            mapear_asignaciones_por_tarjeta([{"roles": ["cotizador"]}], {"cotizador": ["r1"]}), [],
        )


class ActivableTest(unittest.TestCase):
    def test_con_asignaciones_desaparece_el_error_que_bloquea_activar(self):
        nodos, conexiones = _grafo_tipico()
        reglas = reglas_por_defecto(nodos)
        responsables = {f"r{i}": {"activo": True, "email": f"r{i}@abc.cl"} for i in range(1, 5)}

        sin = validar_automatizacion(nodos, conexiones, [], reglas, responsables)
        asignaciones = mapear_asignaciones_por_tarjeta(nodos, {
            "cotizador": ["r1"], "revisor": ["r2"],
            "autorizador": ["r3"], "comprador": ["r4"],
        })
        con = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)

        # Sin asignaciones hay errores de responsables faltantes; con ellas no.
        faltantes = {"nodo_sin_responsable", "rol_sin_responsable", "asignacion_faltante"}
        self.assertLessEqual(len(con), len(sin))
        self.assertEqual([e for e in con if e["codigo"] in faltantes], [])


if __name__ == "__main__":
    unittest.main()
