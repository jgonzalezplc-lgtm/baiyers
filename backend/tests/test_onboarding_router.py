"""Tests de los endpoints nuevos de onboarding — auth real vs. sesión ajena
vs. SSRF en la subida de logo. Todo mockeado, sin red ni Supabase real."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import onboarding
from app.services.auth_context import AuthContext, get_auth_context

app = FastAPI()
app.include_router(onboarding.router)


def _ctx(user_id="u-real-123"):
    return AuthContext(
        actor_user_id=user_id, organization_id="org-1", organization_nombre="Acme",
        user_ids_organizacion=[user_id], es_admin=True,
    )


class SesionRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_sin_token_devuelve_401(self):
        async def fallo():
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Falta el header Authorization: Bearer <token>")
        app.dependency_overrides[get_auth_context] = fallo
        resp = self.client.post("/api/onboarding/sesion")
        self.assertEqual(resp.status_code, 401)

    def test_sesion_de_otro_usuario_devuelve_404(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx("u-real-123")
        with patch("app.services.onboarding_session.obtener_sesion", return_value=None):
            resp = self.client.get("/api/onboarding/sesion/sesion-ajena")
        self.assertEqual(resp.status_code, 404)

    def test_turno_sobre_sesion_completada_devuelve_400(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        with patch("app.services.onboarding_session.obtener_sesion", return_value={"id": "s1", "estado": "completado"}):
            resp = self.client.post("/api/onboarding/sesion/s1/turno", json={"mensaje": "hola"})
        self.assertEqual(resp.status_code, 400)

    def test_confirmar_con_campos_faltantes_devuelve_400(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        sesion = {"id": "s1", "draft": {"empresa": {"valor": "Acme", "confirmado": True}}}
        with patch("app.services.onboarding_session.obtener_sesion", return_value=sesion):
            resp = self.client.post("/api/onboarding/sesion/s1/confirmar")
        self.assertEqual(resp.status_code, 400)

    def test_confirmar_rut_duplicado_devuelve_409(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        draft = {
            "empresa": {"valor": "Acme", "confirmado": True},
            "rut": {"valor": "76.123.456-0", "confirmado": True},
            "nombre_usuario": {"valor": "Ana", "confirmado": True},
        }
        sesion = {"id": "s1", "draft": draft}

        class FakeCtxOrg:
            organizacion_id = "org-1"

        fake_sb = MagicMock()
        fake_sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception(
            "duplicate key value violates unique constraint ux_organizaciones_rut (23505)"
        )
        with patch("app.services.onboarding_session.obtener_sesion", return_value=sesion), \
             patch("app.services.organizacion.resolver_organizacion", return_value=FakeCtxOrg()), \
             patch("app.services.supabase.get_supabase", return_value=fake_sb):
            resp = self.client.post("/api/onboarding/sesion/s1/confirmar")
        self.assertEqual(resp.status_code, 409)

    def test_logo_candidato_con_ip_privada_es_rechazado(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()

        class FakeCtxOrg:
            organizacion_id = "org-1"

        with patch("app.services.onboarding_session.obtener_sesion", return_value={"id": "s1"}), \
             patch("app.services.organizacion.resolver_organizacion", return_value=FakeCtxOrg()):
            resp = self.client.post(
                "/api/onboarding/sesion/s1/logo/candidato",
                json={"url": "https://127.0.0.1/logo.png"},
            )
        self.assertEqual(resp.status_code, 400)

    def test_logo_candidato_con_esquema_no_https_es_rechazado(self):
        app.dependency_overrides[get_auth_context] = lambda: _ctx()

        class FakeCtxOrg:
            organizacion_id = "org-1"

        with patch("app.services.onboarding_session.obtener_sesion", return_value={"id": "s1"}), \
             patch("app.services.organizacion.resolver_organizacion", return_value=FakeCtxOrg()):
            resp = self.client.post(
                "/api/onboarding/sesion/s1/logo/candidato",
                json={"url": "file:///etc/passwd"},
            )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
