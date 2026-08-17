"""Fase E: homologación humana y seguimiento por proveedor."""
import unittest
from unittest.mock import MagicMock, patch


class WorkflowHomologationTest(unittest.TestCase):
    def test_decision_invalida_no_consulta_base(self):
        from app.services import workflow_homologation as svc

        with patch.object(svc, "_sb") as db:
            with self.assertRaisesRegex(ValueError, "Decisión inválida"):
                svc.decidir_caso("u1", True, "c1", "autoaprobar")
        db.assert_not_called()

    def test_recepcion_sin_caso_activo_es_inocua(self):
        from app.services import workflow_homologation as svc

        fake_sb = MagicMock()
        fake_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = []
        with patch.object(svc, "_sb", return_value=fake_sb):
            resultado = svc.registrar_recepcion_antecedentes("conv", "msg", ["vigencia.pdf"])
        self.assertEqual(resultado, {"aplicada": False})

    def test_scheduler_delega_followup_de_homologacion(self):
        from app.services import workflow_scheduler as scheduler

        action = {"id": "a1", "communication_rule_id": "r1", "node_execution_id": "e1"}
        ejecucion = {"id": "e1", "instance_id": "i1", "estado": "activa"}
        instancia = {"id": "i1", "estado_workflow": "activo", "execution_owner": "unified"}
        regla = {"id": "r1", "evento_plantilla": "supplier_intake_followup"}
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
             patch.object(scheduler, "_procesar_followup_homologacion", return_value={"estado": "enviada"}) as procesar:
            resultado = scheduler.procesar_accion(action)
        self.assertEqual(resultado, {"estado": "enviada"})
        procesar.assert_called_once_with(action, regla, ejecucion, instancia)

    def test_catalogo_incluye_tres_comunicaciones_minimas(self):
        from app.services.mail_events import EVENTOS

        self.assertEqual(EVENTOS["supplier_intake_started"].audiencia, "external")
        self.assertEqual(EVENTOS["supplier_intake_followup"].audiencia, "external")
        self.assertEqual(EVENTOS["supplier_intake_missing_information"].audiencia, "external")


if __name__ == "__main__":
    unittest.main()
