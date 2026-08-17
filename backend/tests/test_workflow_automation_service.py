"""Persistencia base: las reservas deben delegar en RPCs atómicas."""
import unittest
from unittest.mock import MagicMock, patch


class ReservarAccionTest(unittest.TestCase):
    def test_rpc_adquiere_y_devuelve_accion(self):
        from app.services import workflow_automation_service as svc

        fake_sb = MagicMock()
        fake_sb.rpc.return_value.execute.return_value.data = [{"id": "a1", "estado": "reservada"}]
        with patch.object(svc, "_sb", return_value=fake_sb), \
             patch.object(svc, "uuid4", return_value="lease-1"):
            accion = svc.reservar_accion("a1", lease_seconds=60)

        self.assertEqual(accion["id"], "a1")
        fake_sb.rpc.assert_called_once_with("claim_workflow_scheduled_action", {
            "p_action_id": "a1",
            "p_lease_token": "lease-1",
            "p_lease_seconds": 60,
        })

    def test_rpc_sin_fila_significa_que_otro_worker_gano(self):
        from app.services import workflow_automation_service as svc

        fake_sb = MagicMock()
        fake_sb.rpc.return_value.execute.return_value.data = []
        with patch.object(svc, "_sb", return_value=fake_sb):
            self.assertIsNone(svc.reservar_accion("a1"))


if __name__ == "__main__":
    unittest.main()
