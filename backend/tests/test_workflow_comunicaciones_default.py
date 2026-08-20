import unittest

from app.services.mail_events import EVENTOS
from app.services.workflow_automation import (
    EVENTOS_DOMINIO,
    POLITICAS_AGOTAMIENTO,
    validar_automatizacion,
)
from app.services.workflow_comunicaciones_default import (
    reglas_para_nodo,
    reglas_por_defecto,
)
from app.services.workflow_conversational import compilar_a_grafo

# Eventos que algún flujo real consume filtrando por `evento_plantilla`.
# Si se cablea un flujo nuevo, se agrega acá Y en el módulo.
EVENTOS_EJECUTADOS = {
    "approval_reminder",
    "rfq_requested", "rfq_followup",
    "supplier_intake_followup",
    "purchase_order_ack_reminder", "dispatch_status_request",
    "purchase_order_internal_copy", "purchase_order_acknowledged_internal",
    "dispatch_notified_internal",
}


def _claves_eventos() -> set[str]:
    try:
        return set(EVENTOS.keys())
    except AttributeError:
        return {e.clave for e in EVENTOS}


class CatalogoTest(unittest.TestCase):
    def test_solo_se_generan_eventos_que_alguien_ejecuta(self):
        """Invariante central: una regla para un evento sin flujo que la lea
        seria un correo que la UI muestra configurado y nunca se envia."""
        nodos = [
            {"id": "n0", "tipo": t, "roles": [r]}
            for t, r in [
                ("tarea_humana", "cotizador"), ("revision", "revisor"),
                ("autorizacion", "autorizador"), ("homologacion", "homologador"),
                ("emision_oc", "comprador"), ("espera_documento", "receptor_facturas"),
            ]
        ]
        generados = {r["evento_plantilla"] for n in nodos for r in reglas_para_nodo(n)}
        self.assertTrue(generados <= EVENTOS_EJECUTADOS, generados - EVENTOS_EJECUTADOS)

    def test_todo_evento_generado_existe_en_el_catalogo(self):
        catalogo = _claves_eventos()
        nodos = [{"id": "n0", "tipo": t, "roles": []} for t in
                 ("tarea_humana", "autorizacion", "homologacion", "emision_oc")]
        for regla in reglas_por_defecto(nodos):
            self.assertIn(regla["evento_plantilla"], catalogo)

    def test_los_eventos_de_termino_son_del_vocabulario_de_dominio(self):
        nodos = [{"id": "n0", "tipo": t, "roles": []} for t in
                 ("tarea_humana", "autorizacion", "homologacion", "emision_oc")]
        for regla in reglas_por_defecto(nodos):
            if regla.get("evento_termino"):
                self.assertIn(regla["evento_termino"], EVENTOS_DOMINIO)


class LoopsTest(unittest.TestCase):
    def test_todo_loop_tiene_termino_y_politica(self):
        """Lo exige el CHECK de la 041; sin esto el insert falla en runtime."""
        nodos = [{"id": "n0", "tipo": t, "roles": []} for t in
                 ("tarea_humana", "autorizacion", "homologacion", "emision_oc")]
        for regla in reglas_por_defecto(nodos):
            if regla.get("repetir_cada_dias"):
                self.assertTrue(regla.get("evento_termino"), regla["evento_plantilla"])
                self.assertIn(regla.get("politica_agotamiento"), POLITICAS_AGOTAMIENTO)

    def test_ningun_loop_autoaprueba_ni_descarta_solo(self):
        nodos = [{"id": "n0", "tipo": t, "roles": []} for t in
                 ("tarea_humana", "autorizacion", "homologacion", "emision_oc")]
        for regla in reglas_por_defecto(nodos):
            if regla.get("politica_agotamiento"):
                self.assertEqual(regla["politica_agotamiento"], "pausar")

    def test_la_insistencia_a_proveedores_es_por_proveedor(self):
        """Que un proveedor no conteste no puede frenar el loop de los otros."""
        reglas = reglas_para_nodo({"id": "n0", "tipo": "tarea_humana", "roles": []})
        followup = next(r for r in reglas if r["evento_plantilla"] == "rfq_followup")
        self.assertEqual(followup["alcance_termino"], "proveedor")


class PorTipoTest(unittest.TestCase):
    def test_revision_y_factura_no_generan_correos(self):
        for tipo in ("revision", "espera_documento"):
            self.assertEqual(reglas_para_nodo({"id": "n", "tipo": tipo, "roles": []}), [])

    def test_autorizacion_solo_agrega_el_recordatorio(self):
        """El correo inicial lo manda listas.py imperativamente: duplicarlo
        como regla mandaria dos veces la misma solicitud."""
        reglas = reglas_para_nodo({"id": "n", "tipo": "autorizacion", "roles": []})
        self.assertEqual([r["evento_plantilla"] for r in reglas], ["approval_reminder"])

    def test_el_aviso_de_despacho_va_a_quien_recibe_si_ese_rol_existe(self):
        con = reglas_para_nodo({"id": "n", "tipo": "emision_oc", "roles": []},
                               roles_disponibles={"comprador", "receptor_facturas"})
        aviso = next(r for r in con if r["evento_plantilla"] == "dispatch_notified_internal")
        self.assertEqual(aviso["rol_clave"], "receptor_facturas")

    def test_sin_rol_de_recepcion_el_aviso_cae_al_comprador(self):
        sin = reglas_para_nodo({"id": "n", "tipo": "emision_oc", "roles": []},
                               roles_disponibles={"comprador"})
        aviso = next(r for r in sin if r["evento_plantilla"] == "dispatch_notified_internal")
        self.assertEqual(aviso["rol_clave"], "comprador")

    def test_nodo_sin_id_se_ignora(self):
        self.assertEqual(reglas_por_defecto([{"tipo": "autorizacion"}]), [])


class IntegracionConElGrafoTest(unittest.TestCase):
    def test_un_ciclo_tipico_del_chat_queda_cableado_y_valido(self):
        etapas = [
            {"nombre": "Cotizar", "tipo": "tarea_humana", "roles": ["cotizador"], "responsables": []},
            {"nombre": "Autorizar", "tipo": "autorizacion", "roles": ["autorizador"], "responsables": []},
            {"nombre": "Emitir OC", "tipo": "emision_oc", "roles": ["comprador"], "responsables": []},
        ]
        nodos, conexiones = compilar_a_grafo(etapas, [])
        reglas = reglas_por_defecto(nodos)
        self.assertTrue(reglas)

        # Las reglas generadas no pueden introducir errores de automatización
        # por sí mismas (los de responsables faltantes son harina de otro costal).
        errores = validar_automatizacion(nodos, conexiones, [], reglas)
        codigos = {e["codigo"] for e in errores}
        self.assertNotIn("loop_sin_evento_termino", codigos)


if __name__ == "__main__":
    unittest.main()
