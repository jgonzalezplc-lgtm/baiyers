"""Fase F: emisión, acuse y despacho de órdenes de compra."""
import unittest
from unittest.mock import MagicMock, patch


class WorkflowPurchaseOrderTest(unittest.TestCase):
    def test_oc_legacy_no_activa_motor_unificado(self):
        from app.services import workflow_purchase_order as svc

        with patch.object(svc, "contexto_de_oc", return_value=None):
            self.assertEqual(svc.registrar_oc_emitida("oc-1"), {"aplicada": False})
            self.assertEqual(svc.registrar_acuse_oc("oc-1", "msg-1"), {"aplicada": False})
            self.assertEqual(svc.registrar_despacho_oc("oc-1", "msg-2"), {"aplicada": False})

    def test_scheduler_delega_recordatorio_de_oc(self):
        from app.services import workflow_scheduler as scheduler

        action = {"id": "a1", "communication_rule_id": "r1", "node_execution_id": "e1"}
        ejecucion = {"id": "e1", "instance_id": "i1", "estado": "activa"}
        instancia = {"id": "i1", "estado_workflow": "activo", "execution_owner": "unified"}
        regla = {"id": "r1", "evento_plantilla": "purchase_order_ack_reminder"}
        q_exec, q_inst, q_rule = MagicMock(), MagicMock(), MagicMock()
        q_exec.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [ejecucion]
        q_inst.select.return_value.eq.return_value.single.return_value.execute.return_value.data = instancia
        q_rule.select.return_value.eq.return_value.single.return_value.execute.return_value.data = regla
        fake_sb = MagicMock()
        fake_sb.table.side_effect = lambda nombre: {
            "workflow_node_executions": q_exec,
            "workflow_instances": q_inst,
            "workflow_node_communication_rules": q_rule,
        }[nombre]
        with patch.object(scheduler, "_sb", return_value=fake_sb), \
             patch.object(scheduler, "_procesar_recordatorio_oc", return_value={"estado": "enviada"}) as procesar:
            resultado = scheduler.procesar_accion(action)

        self.assertEqual(resultado, {"estado": "enviada"})
        procesar.assert_called_once_with(action, regla, ejecucion, instancia)

    def test_despacho_no_cierra_nodo_mientras_queden_ocs_pendientes(self):
        from app.services import workflow_purchase_order as svc

        contexto = {
            "oc": {"id": "oc-1", "estado": "despachada"},
            "ejecucion": {"id": "e1", "nodo_id": "n1"},
            "instancia": {"id": "i1", "workflow_id": "w1"},
            "reglas": [],
        }
        ordenes = MagicMock()
        ordenes.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "oc-1", "estado": "despachada"},
            {"id": "oc-2", "estado": "confirmada"},
        ]
        fake_sb = MagicMock()
        fake_sb.table.side_effect = lambda nombre: ordenes if nombre == "ordenes_compra" else MagicMock()
        with patch.object(svc, "contexto_de_oc", return_value=contexto), \
             patch.object(svc, "_sb", return_value=fake_sb), \
             patch.object(svc, "_cancelar_eventos"), patch.object(svc, "_evento"):
            resultado = svc.registrar_despacho_oc("oc-1", "msg-1")

        self.assertEqual(resultado, {"aplicada": True, "resuelto": False, "ordenes_pendientes": 1})

    def test_catalogo_incluye_comunicaciones_de_oc(self):
        from app.services.mail_events import EVENTOS

        self.assertEqual(EVENTOS["purchase_order_sent"].audiencia, "external")
        self.assertEqual(EVENTOS["purchase_order_ack_reminder"].audiencia, "external")
        self.assertEqual(EVENTOS["dispatch_status_request"].audiencia, "external")
        self.assertEqual(EVENTOS["dispatch_notified_internal"].audiencia, "internal")


if __name__ == "__main__":
    unittest.main()
