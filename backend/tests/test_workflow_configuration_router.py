"""Fase B: endpoints por tarjeta siempre usan actor verificado y admin gate."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import workflows
from app.services.auth_context import AuthContext, get_auth_context

app = FastAPI()
app.include_router(workflows.router)


def _ctx(admin=True):
    return AuthContext(actor_user_id="u-actor", organization_id="org-1",
                       organization_nombre="Acme", user_ids_organizacion=["u-actor"],
                       es_admin=admin)


class WorkflowConfigurationRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_listar_configuracion_usa_actor_del_token(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.services.workflow_automation_service.listar_configuracion_workflow", return_value={"asignaciones": [], "reglas": []}) as fn:
            resp = self.client.get("/api/workflows/wf-1/configuracion")
        self.assertEqual(resp.status_code, 200)
        fn.assert_called_once_with("u-actor", "wf-1")

    def test_miembro_no_admin_no_puede_asignar(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(admin=False)
        resp = self.client.post("/api/workflows/wf-1/asignaciones-nodo", json={
            "nodo_id": "n1", "rol_clave": "cotizador", "responsable_id": "r1",
        })
        self.assertEqual(resp.status_code, 403)

    def test_admin_asigna_por_nodo_sin_user_id_del_cliente(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.services.workflow_automation_service.asignar_responsable_nodo", return_value={"id": "a1"}) as fn:
            resp = self.client.post("/api/workflows/wf-1/asignaciones-nodo", json={
                "nodo_id": "n1", "rol_clave": "cotizador", "responsable_id": "r1",
                "modo": "secuencial", "orden": 1,
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(fn.call_args.args[:5], ("u-actor", "wf-1", "n1", "cotizador", "r1"))

    def test_admin_crea_regla_y_audiencia_la_resuelve_el_servicio(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.services.workflow_automation_service.guardar_regla_comunicacion", return_value={"id": "rule-1"}) as fn:
            resp = self.client.post("/api/workflows/wf-1/reglas-comunicacion", json={
                "nodo_id": "n1", "rol_clave": "cotizador",
                "evento_plantilla": "rfq_followup", "destinatario_tipo": "proveedor",
                "repetir_cada_dias": 2, "max_intentos": 3,
                "evento_termino": "rfq_completa", "politica_agotamiento": "pausar",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(fn.call_args.args[0:3], ("u-actor", "wf-1", "n1"))

    def test_admin_crea_version_con_el_grafo_visible_del_canvas(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        esperado = {"id": "wf-2", "estado": "borrador", "version": 2}
        with patch("app.services.workflow_service.crear_version_borrador", return_value=esperado) as fn:
            resp = self.client.post("/api/workflows/wf-1/crear-version", json={
                "nodos": [{"id": "inicio", "tipo": "inicio"}],
                "conexiones": [],
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), esperado)
        fn.assert_called_once_with(
            "u-actor", "wf-1", [{"id": "inicio", "tipo": "inicio"}], [],
        )

    def test_miembro_no_admin_no_puede_crear_version(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx(admin=False)
        resp = self.client.post("/api/workflows/wf-1/crear-version", json={
            "nodos": [], "conexiones": [],
        })
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
