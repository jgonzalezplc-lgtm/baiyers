"""Fase A del workflow + comunicaciones: contratos puros e idempotencia."""
import unittest
from datetime import datetime, timezone

from app.services.workflow_automation import (
    clave_idempotencia,
    proximo_vencimiento,
    validar_automatizacion,
)


def _base():
    nodos = [
        {"id": "inicio", "tipo": "inicio", "nombre": "Inicio"},
        {
            "id": "cotizar", "tipo": "tarea_humana", "nombre": "Cotizar",
            "roles": ["cotizador"], "resultados": ["completo", "timeout"],
        },
        {"id": "fin", "tipo": "fin", "nombre": "Fin"},
    ]
    conexiones = [
        {"origen_nodo_id": "inicio", "destino_nodo_id": "cotizar"},
        {"origen_nodo_id": "cotizar", "destino_nodo_id": "fin", "resultado": "completo"},
        {"origen_nodo_id": "cotizar", "destino_nodo_id": "fin", "resultado": "timeout"},
    ]
    asignaciones = [{
        "nodo_id": "cotizar", "rol_clave": "cotizador",
        "responsable_id": "r1", "modo": "individual", "orden": None,
    }]
    reglas = [{
        "id": "rule-1", "nodo_id": "cotizar", "rol_clave": "cotizador",
        "evento_plantilla": "rfq_followup", "audiencia": "external",
        "destinatario_tipo": "proveedor", "disparador_tipo": "al_entrar",
        "repetir_cada_dias": 2, "max_intentos": 3,
        "evento_termino": "rfq_completa", "alcance_termino": "proveedor",
        "resultado_al_terminar": "completo",
        "politica_agotamiento": "avanzar_timeout",
        "resultado_agotamiento": "timeout",
    }]
    responsables = {"r1": {"activo": True, "email": "ana@empresa.cl"}}
    return nodos, conexiones, asignaciones, reglas, responsables


class ValidacionAutomatizacionTest(unittest.TestCase):
    def test_configuracion_completa_es_valida(self):
        self.assertEqual(validar_automatizacion(*_base()), [])

    def test_tarjeta_humana_exige_asignacion_por_nodo(self):
        nodos, conexiones, _, reglas, responsables = _base()
        errores = validar_automatizacion(nodos, conexiones, [], reglas, responsables)
        self.assertTrue(any(e["codigo"] == "rol_sin_responsable_nodo" for e in errores))

    def test_loop_exige_evento_y_politica_de_agotamiento(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        reglas[0]["evento_termino"] = None
        reglas[0]["politica_agotamiento"] = None
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        codigos = {e["codigo"] for e in errores}
        self.assertIn("loop_sin_evento_termino", codigos)
        self.assertIn("loop_sin_politica_agotamiento", codigos)

    def test_audiencia_y_destinatario_deben_coincidir(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        reglas[0]["destinatario_tipo"] = "autorizador"
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "destinatario_audiencia_incompatible" for e in errores))

    def test_evento_de_plantilla_debe_existir(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        reglas[0]["evento_plantilla"] = "correo_inventado"
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "evento_plantilla_inexistente" for e in errores))

    def test_resultado_debe_estar_declarado_y_conectado(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        reglas[0]["resultado_agotamiento"] = "fantasma"
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "resultado_no_declarado" for e in errores))

    def test_asignacion_secuencial_exige_orden(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        asignaciones[0]["modo"] = "secuencial"
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "orden_secuencial_requerido" for e in errores))

    def test_modo_individual_no_admite_dos_responsables(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        asignaciones.append({**asignaciones[0], "responsable_id": "r2"})
        responsables["r2"] = {"activo": True, "email": "bea@empresa.cl"}
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "asignacion_individual_multiple" for e in errores))

    def test_comunicacion_interna_exige_email_resoluble(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        reglas[0].update({
            "evento_plantilla": "approval_reminder",
            "audiencia": "internal",
            "destinatario_tipo": "responsable_rol",
        })
        responsables["r1"]["email"] = None
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "responsable_sin_email" for e in errores))

    def test_rfq_por_minimo_exige_cantidad_valida(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        nodos[1]["criterio_cierre"] = "minimo_respuestas"
        errores = validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables)
        self.assertTrue(any(e["codigo"] == "minimo_respuestas_rfq_invalido" for e in errores))

    def test_rfq_acepta_cierre_manual(self):
        nodos, conexiones, asignaciones, reglas, responsables = _base()
        nodos[1]["criterio_cierre"] = "cierre_manual"
        self.assertEqual(validar_automatizacion(nodos, conexiones, asignaciones, reglas, responsables), [])


class ClaveIdempotenciaTest(unittest.TestCase):
    def test_mismos_componentes_producen_misma_clave(self):
        kwargs = dict(instance_id="i1", nodo_id="cotizar", visit_number=1,
                      rule_id="r1", recipient_key="Proveedor-1", attempt_number=2)
        self.assertEqual(clave_idempotencia(**kwargs), clave_idempotencia(**kwargs))

    def test_nueva_visita_o_intento_produce_otra_clave(self):
        base = dict(instance_id="i1", nodo_id="cotizar", visit_number=1,
                    rule_id="r1", recipient_key="p1", attempt_number=1)
        otra_visita = {**base, "visit_number": 2}
        otro_intento = {**base, "attempt_number": 2}
        self.assertNotEqual(clave_idempotencia(**base), clave_idempotencia(**otra_visita))
        self.assertNotEqual(clave_idempotencia(**base), clave_idempotencia(**otro_intento))

    def test_clave_no_expone_destinatario(self):
        clave = clave_idempotencia(instance_id="i", nodo_id="n", visit_number=1,
                                   rule_id="r", recipient_key="persona@empresa.cl",
                                   attempt_number=1)
        self.assertNotIn("persona@empresa.cl", clave)

    def test_proximo_vencimiento_conserva_zona_horaria(self):
        inicio = datetime(2026, 8, 17, 9, tzinfo=timezone.utc)
        siguiente = proximo_vencimiento(inicio, 2)
        self.assertEqual(siguiente.day, 19)
        self.assertEqual(siguiente.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
