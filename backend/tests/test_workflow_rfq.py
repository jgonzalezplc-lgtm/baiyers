"""Fase D: enlace de RFQ por proveedor con el workflow unificado."""
import unittest
from unittest.mock import MagicMock, patch


class WorkflowRFQTest(unittest.TestCase):
    def test_sin_workflow_activo_conserva_camino_legacy(self):
        from app.services import workflow_rfq

        with patch("app.services.workflow_execution.obtener_workflow_activo", return_value=None), \
             patch.object(workflow_rfq, "_sb") as db:
            self.assertIsNone(workflow_rfq.asegurar_contexto_rfq("u1", "l1"))
        db.assert_not_called()

    def test_programa_solo_reglas_de_followup_por_batch(self):
        from app.services import workflow_rfq

        contexto = {
            "reglas": [
                {"id": "initial", "evento_plantilla": "rfq_requested"},
                {"id": "follow", "evento_plantilla": "rfq_followup", "demora_inicial_dias": 2},
            ],
            "ejecucion": {"id": "e1", "visit_number": 3},
            "instancia": {"id": "i1"}, "nodo": {"id": "n1"},
        }
        with patch.object(workflow_rfq, "programar_accion", return_value={"id": "a1"}) as programar:
            creadas = workflow_rfq.programar_followups({"id": "batch-1"}, contexto)

        self.assertEqual(creadas, [{"id": "a1"}])
        self.assertEqual(programar.call_count, 1)
        self.assertEqual(programar.call_args.kwargs["recipient_key"], "batch-1")
        self.assertEqual(programar.call_args.kwargs["communication_rule_id"], "follow")
        self.assertEqual(programar.call_args.kwargs["visit_number"], 3)

    def test_respuesta_de_conversacion_legacy_no_toca_motor(self):
        from app.services import workflow_rfq

        fake_sb = MagicMock()
        fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        with patch.object(workflow_rfq, "_sb", return_value=fake_sb):
            resultado = workflow_rfq.registrar_respuesta_rfq("c1", "m1", completa=True)

        self.assertEqual(resultado, {"aplicada": False, "motivo": "rfq_legacy_o_sin_batch"})

    def test_scheduler_delega_followup_rfq_sin_entrar_a_aprobacion(self):
        from app.services import workflow_scheduler

        action = {"id": "a1", "communication_rule_id": "r1", "node_execution_id": "e1"}
        ejecucion = {"id": "e1", "instance_id": "i1", "estado": "activa"}
        instancia = {"id": "i1", "estado_workflow": "activo", "execution_owner": "unified"}
        regla = {"id": "r1", "evento_plantilla": "rfq_followup"}
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
        with patch.object(workflow_scheduler, "_sb", return_value=fake_sb), \
             patch.object(workflow_scheduler, "_procesar_followup_rfq", return_value={"estado": "enviada"}) as followup:
            resultado = workflow_scheduler.procesar_accion(action)

        self.assertEqual(resultado, {"estado": "enviada"})
        followup.assert_called_once_with(action, regla, ejecucion, instancia)


if __name__ == "__main__":
    unittest.main()
