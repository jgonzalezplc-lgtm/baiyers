"""Tests de workflow_service.py — eliminar_workflow() y el enriquecimiento
de obtener_workflow() con estado de onboarding. Todo mockeado."""
import unittest
from unittest.mock import MagicMock, patch


class EliminarWorkflowTest(unittest.TestCase):
    def test_no_encontrado_lanza_value_error(self):
        from app.services import workflow_service as ws
        with patch.object(ws, "obtener_workflow", return_value=None):
            with self.assertRaises(ValueError) as cm:
                ws.eliminar_workflow("u-1", "wf-inexistente")
        self.assertIn("no encontrado", str(cm.exception).lower())

    def test_rechaza_eliminar_ciclo_activo(self):
        from app.services import workflow_service as ws
        with patch.object(ws, "obtener_workflow", return_value={"id": "wf-1", "estado": "activo"}):
            with self.assertRaises(ValueError) as cm:
                ws.eliminar_workflow("u-1", "wf-1")
        self.assertIn("activo", str(cm.exception).lower())

    def test_borrador_se_elimina(self):
        from app.services import workflow_service as ws
        fake_sb = MagicMock()
        with patch.object(ws, "obtener_workflow", return_value={"id": "wf-1", "estado": "borrador"}), \
             patch.object(ws, "_sb", return_value=fake_sb):
            ws.eliminar_workflow("u-1", "wf-1")
        fake_sb.table.assert_called_with("workflow_definitions")
        fake_sb.table.return_value.delete.return_value.eq.assert_called_with("id", "wf-1")


class ObtenerWorkflowEstadoOnboardingTest(unittest.TestCase):
    def test_responsable_sin_vincular_no_llama_a_supabase_auth(self):
        from app.services import workflow_service as ws

        def table_side_effect(nombre):
            m = MagicMock()
            if nombre == "workflow_definitions":
                m.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"id": "wf-1", "estado": "borrador"})
            elif nombre == "workflow_roles":
                m.select.return_value.eq.return_value.execute.return_value.data = []
            elif nombre == "responsable_roles":
                m.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "rr-1", "rol_clave": "autorizador", "responsables": {"id": "r-1", "nombre": "Pedro", "usuario_baiyer_id": None}},
                ]
            return m

        fake_sb = MagicMock()
        fake_sb.table.side_effect = table_side_effect

        with patch.object(ws, "_sb", return_value=fake_sb), \
             patch.object(ws, "_ids_organizacion", return_value=["u-1"]), \
             patch("app.services.organizacion.estado_onboarding_de_usuarios") as mock_estado:
            resultado = ws.obtener_workflow("u-1", "wf-1")

        mock_estado.assert_called_once_with([])
        self.assertEqual(resultado["responsables"][0]["responsables"]["estado_onboarding"], "sin_vincular")

    def test_responsable_vinculado_usa_estado_de_organizacion(self):
        from app.services import workflow_service as ws

        def table_side_effect(nombre):
            m = MagicMock()
            if nombre == "workflow_definitions":
                m.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"id": "wf-1", "estado": "borrador"})
            elif nombre == "workflow_roles":
                m.select.return_value.eq.return_value.execute.return_value.data = []
            elif nombre == "responsable_roles":
                m.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "rr-1", "rol_clave": "autorizador", "responsables": {"id": "r-1", "nombre": "Pedro", "usuario_baiyer_id": "u-pedro"}},
                ]
            return m

        fake_sb = MagicMock()
        fake_sb.table.side_effect = table_side_effect

        with patch.object(ws, "_sb", return_value=fake_sb), \
             patch.object(ws, "_ids_organizacion", return_value=["u-1"]), \
             patch("app.services.organizacion.estado_onboarding_de_usuarios", return_value={"u-pedro": "activo"}):
            resultado = ws.obtener_workflow("u-1", "wf-1")

        self.assertEqual(resultado["responsables"][0]["responsables"]["estado_onboarding"], "activo")


class ActivarWorkflowAutomatizacionTest(unittest.TestCase):
    def test_error_de_automatizacion_bloquea_activacion(self):
        from app.services import workflow_service as ws
        workflow = {"id": "wf-1", "estado": "borrador", "nombre": "Ciclo", "nodos": [], "conexiones": []}
        fake_sb = MagicMock()
        with patch.object(ws, "obtener_workflow", return_value=workflow), \
             patch.object(ws, "validar_workflow", return_value=[{"codigo": "loop_sin_evento_termino"}]), \
             patch.object(ws, "_sb", return_value=fake_sb):
            with self.assertRaises(ValueError):
                ws.activar_workflow("u-1", "wf-1")
        fake_sb.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
