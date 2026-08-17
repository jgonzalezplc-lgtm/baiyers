"""Tests del router de plantillas — admin-gating y mapeo de errores. Todo
mockeado, sin red ni Supabase real."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import mail_templates
from app.services.auth_context import AuthContext, get_auth_context

app = FastAPI()
app.include_router(mail_templates.router)


def _ctx(es_admin=True):
    return AuthContext(
        actor_user_id="u-1", organization_id="org-1", organization_nombre="Acme",
        user_ids_organizacion=["u-1"], es_admin=es_admin,
    )


class MailTemplatesRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_listar_eventos_no_requiere_auth(self):
        resp = self.client.get("/api/mail-templates/eventos")
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.json()), 0)

    def test_preview_no_admin_igual_puede_previsualizar(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(es_admin=False)
        resp = self.client.post("/api/mail-templates/preview", json={
            "evento": "rfq_received_thanks", "subject": "Hola {{proveedor_nombre}}",
            "body": "{{proveedor_nombre}}", "variables_declaradas": ["proveedor_nombre"],
        })
        self.assertEqual(resp.status_code, 200)

    def test_preview_con_variable_invalida_devuelve_400(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        resp = self.client.post("/api/mail-templates/preview", json={
            "evento": "rfq_received_thanks", "subject": "Hola",
            "body": "{{password}}", "variables_declaradas": ["password"],
        })
        self.assertEqual(resp.status_code, 400)

    def test_guardar_sin_ser_admin_devuelve_403(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(es_admin=False)
        resp = self.client.post("/api/mail-templates", json={
            "evento": "rfq_received_thanks", "subject": "Hola {{proveedor_nombre}}",
            "body": "{{proveedor_nombre}}", "variables_declaradas": ["proveedor_nombre"],
        })
        self.assertEqual(resp.status_code, 403)

    def test_guardar_como_admin_llama_al_servicio_con_la_organizacion_del_contexto(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(es_admin=True)
        with patch("app.services.mail_template_service.guardar_version", return_value={"id": "def-1"}) as mock_guardar:
            resp = self.client.post("/api/mail-templates", json={
                "evento": "rfq_received_thanks", "subject": "Hola {{proveedor_nombre}}",
                "body": "{{proveedor_nombre}}", "variables_declaradas": ["proveedor_nombre"],
            })
        self.assertEqual(resp.status_code, 200)
        mock_guardar.assert_called_once()
        self.assertEqual(mock_guardar.call_args.args[0], "org-1")

    def test_restaurar_default_sin_ser_admin_devuelve_403(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(es_admin=False)
        resp = self.client.post("/api/mail-templates/restaurar-default", json={"evento": "rfq_received_thanks"})
        self.assertEqual(resp.status_code, 403)

    def test_listar_plantillas_usa_organizacion_del_contexto(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.services.mail_template_service.listar_plantillas", return_value=[]) as mock_listar:
            resp = self.client.get("/api/mail-templates")
        self.assertEqual(resp.status_code, 200)
        mock_listar.assert_called_once_with("org-1", None, None)

    def test_workflow_contextual_ajeno_devuelve_404(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.routers.mail_templates._verificar_workflow_contexto", side_effect=mail_templates.HTTPException(status_code=404, detail="Workflow no encontrado")):
            resp = self.client.get("/api/mail-templates?workflow_id=wf-ajeno&nodo_id=n1")
        self.assertEqual(resp.status_code, 404)

    def test_restaurar_en_nodo_vuelve_a_herencia(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.routers.mail_templates._verificar_workflow_contexto"), \
             patch("app.services.mail_template_service.restaurar_herencia", return_value={"heredando": True}) as fn:
            resp = self.client.post("/api/mail-templates/restaurar-default", json={
                "evento": "rfq_followup", "workflow_id": "wf-1", "nodo_id": "n1",
            })
        self.assertEqual(resp.status_code, 200)
        fn.assert_called_once_with("org-1", "rfq_followup", "wf-1", "n1")


if __name__ == "__main__":
    unittest.main()
