"""Fase C: scheduler durable y conexión segura con el cron."""
import unittest
from unittest.mock import MagicMock, patch


class WorkflowSchedulerTest(unittest.TestCase):
    def test_legacy_no_programa_recordatorios(self):
        from app.services import workflow_scheduler as scheduler

        with patch.object(scheduler, "_sb") as db:
            creadas = scheduler.programar_recordatorios_autorizacion(
                {"execution_owner": "legacy"}, responsable_id="r1",
                lista_id="l1", lista_nombre="Lista",
            )

        self.assertEqual(creadas, [])
        db.assert_not_called()

    def test_unified_programa_una_accion_por_regla(self):
        from app.services import workflow_scheduler as scheduler

        fake_sb = MagicMock()
        fake_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "rule-1", "demora_inicial_dias": 2},
            {"id": "rule-2", "repetir_cada_dias": 3},
        ]
        resolucion = {
            "execution_owner": "unified", "workflow_id": "w1",
            "workflow_instance_id": "i1", "nodo_id": "n1",
        }
        with patch.object(scheduler, "_sb", return_value=fake_sb), \
             patch.object(scheduler, "obtener_o_crear_ejecucion_nodo", return_value={"id": "e1", "visit_number": 1}), \
             patch.object(scheduler, "_evento"), \
             patch.object(scheduler, "programar_accion", side_effect=[{"id": "a1"}, {"id": "a2"}]) as programar:
            creadas = scheduler.programar_recordatorios_autorizacion(
                resolucion, responsable_id="r1", lista_id="l1", lista_nombre="Lista",
            )

        self.assertEqual([c["id"] for c in creadas], ["a1", "a2"])
        self.assertEqual(programar.call_count, 2)
        self.assertEqual(programar.call_args_list[0].kwargs["recipient_key"], "r1")
        self.assertEqual(programar.call_args_list[0].kwargs["attempt_number"], 1)

    def test_cron_registra_worker_cada_minuto(self):
        from app.services import cron

        fake_scheduler = MagicMock()
        with patch.object(cron, "BackgroundScheduler", return_value=fake_scheduler):
            cron.start_cron()

        jobs = {call.kwargs["id"]: call.kwargs for call in fake_scheduler.add_job.call_args_list}
        self.assertIn("workflow_actions_cron", jobs)
        self.assertEqual(jobs["workflow_actions_cron"]["minutes"], 1)
        fake_scheduler.start.assert_called_once()

    def test_worker_no_procesa_si_rpc_no_adquiere_lease(self):
        from app.services import workflow_scheduler as scheduler

        fake_sb = MagicMock()
        fake_sb.table.return_value.select.return_value.lte.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {"id": "a1"}, {"id": "a2"},
        ]
        with patch.object(scheduler, "_sb", return_value=fake_sb), \
             patch.object(scheduler, "reservar_accion", return_value=None) as reservar, \
             patch.object(scheduler, "procesar_accion") as procesar:
            resultado = scheduler.procesar_acciones_vencidas()

        self.assertEqual(resultado, {"candidatas": 2, "procesadas": 0, "errores": 0})
        self.assertEqual(reservar.call_count, 2)
        procesar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
