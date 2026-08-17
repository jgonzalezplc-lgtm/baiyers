"""Fase G: rollout explícito, métricas y rollback por organización."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import workflows
from app.services.auth_context import AuthContext, get_auth_context


app = FastAPI()
app.include_router(workflows.router)


def _ctx(admin=True):
    return AuthContext(
        actor_user_id="u1", organization_id="org1", organization_nombre="Acme",
        user_ids_organizacion=["u1", "u2"], es_admin=admin,
    )


class WorkflowRolloutTest(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def test_sin_fila_es_legacy(self):
        from app.services import workflow_rollout as svc

        query = MagicMock()
        query.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = None
        fake_sb = MagicMock()
        fake_sb.table.return_value = query
        with patch.object(svc, "_sb", return_value=fake_sb):
            estado = svc.obtener_rollout("org1")
        self.assertEqual(estado["execution_mode"], "legacy")
        self.assertFalse(estado["migration_pending"])

    def test_migracion_pendiente_preserva_compatibilidad(self):
        from app.services import workflow_rollout as svc

        fake_sb = MagicMock()
        fake_sb.table.side_effect = RuntimeError("relation does not exist")
        with patch.object(svc, "_sb", return_value=fake_sb):
            estado = svc.obtener_rollout("org1")
        self.assertEqual(estado["execution_mode"], "compatibility")
        self.assertTrue(estado["migration_pending"])

    def test_rollback_no_muta_instancias(self):
        from app.services import workflow_rollout as svc

        query = MagicMock()
        query.upsert.return_value.execute.return_value.data = [{
            "organization_id": "org1", "execution_mode": "legacy",
        }]
        fake_sb = MagicMock()
        fake_sb.table.return_value = query
        with patch.object(svc, "_sb", return_value=fake_sb):
            resultado = svc.cambiar_rollout("u1", "org1", "legacy", "rollback")
        self.assertEqual(resultado["execution_mode"], "legacy")
        fake_sb.table.assert_called_once_with("workflow_rollout_settings")

    def test_miembro_no_admin_no_puede_cambiar_rollout(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(admin=False)
        resp = TestClient(app).put("/api/workflows/rollout/estado", json={
            "execution_mode": "legacy", "reason": "prueba",
        })
        self.assertEqual(resp.status_code, 403)

    def test_estado_expone_comparacion_sin_confiar_en_user_id_cliente(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        esperado = {"legacy": {"instancias": 2}, "unified": {"instancias": 3}}
        with patch("app.services.workflow_rollout.obtener_metricas_rollout", return_value=esperado) as metricas:
            resp = TestClient(app).get("/api/workflows/rollout/estado")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), esperado)
        metricas.assert_called_once_with(["u1", "u2"], "org1")

    def test_modo_unificado_exige_workflow_valido(self):
        from app.services import workflow_rollout as svc

        with patch("app.services.workflow_execution.obtener_workflow_activo", return_value=None):
            with self.assertRaisesRegex(ValueError, "workflow activo"):
                svc.cambiar_rollout("u1", "org1", "unified")

    def test_autorizacion_nueva_respeta_rollout_legacy(self):
        from app.services import workflow_execution as execution

        workflow = {"id": "w1", "nodos": [], "conexiones": []}
        with patch.object(execution, "obtener_workflow_activo", return_value=workflow), \
             patch("app.services.workflow_rollout.motor_unificado_habilitado", return_value=False):
            self.assertIsNone(execution.iniciar_autorizacion_workflow("u1", "l1", 1000))

    def test_rfq_nueva_respeta_rollout_legacy(self):
        from app.services import workflow_rfq as rfq

        workflow = {"id": "w1", "nodos": [], "conexiones": []}
        with patch("app.services.workflow_execution.obtener_workflow_activo", return_value=workflow), \
             patch("app.services.workflow_rollout.motor_unificado_habilitado", return_value=False), \
             patch.object(rfq, "_sb") as db:
            self.assertIsNone(rfq.asegurar_contexto_rfq("u1", "l1"))
        db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
