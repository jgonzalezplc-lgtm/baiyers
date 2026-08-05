"""Tests de AuthContext — verificación de identidad real vs. confiar en el
`user_id` del cliente. Todo mockeado, sin red ni Supabase real."""
import asyncio
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.services.auth_context import get_auth_context, verificar_token


class FakeUser:
    def __init__(self, id_): self.id = id_


class FakeUserResponse:
    def __init__(self, user): self.user = user


class VerificarTokenTest(unittest.TestCase):
    def test_sin_header_lanza_401(self):
        with self.assertRaises(HTTPException) as cm:
            verificar_token(None)
        self.assertEqual(cm.exception.status_code, 401)

    def test_header_sin_bearer_lanza_401(self):
        with self.assertRaises(HTTPException) as cm:
            verificar_token("Token abc123")
        self.assertEqual(cm.exception.status_code, 401)

    def test_bearer_vacio_lanza_401(self):
        with self.assertRaises(HTTPException) as cm:
            verificar_token("Bearer ")
        self.assertEqual(cm.exception.status_code, 401)

    def test_token_valido_devuelve_user_id_verificado(self):
        fake_sb = MagicMock()
        fake_sb.auth.get_user.return_value = FakeUserResponse(FakeUser("u-real-123"))
        with patch("app.services.auth_context._sb", return_value=fake_sb):
            uid = verificar_token("Bearer token-valido")
        self.assertEqual(uid, "u-real-123")
        fake_sb.auth.get_user.assert_called_once_with("token-valido")

    def test_token_rechazado_por_supabase_lanza_401(self):
        fake_sb = MagicMock()
        fake_sb.auth.get_user.side_effect = Exception("invalid JWT")
        with patch("app.services.auth_context._sb", return_value=fake_sb):
            with self.assertRaises(HTTPException) as cm:
                verificar_token("Bearer token-invalido")
        self.assertEqual(cm.exception.status_code, 401)

    def test_supabase_responde_sin_usuario_lanza_401(self):
        fake_sb = MagicMock()
        fake_sb.auth.get_user.return_value = FakeUserResponse(None)
        with patch("app.services.auth_context._sb", return_value=fake_sb):
            with self.assertRaises(HTTPException) as cm:
                verificar_token("Bearer token-expirado")
        self.assertEqual(cm.exception.status_code, 401)


class GetAuthContextTest(unittest.TestCase):
    def test_usuario_verificado_sin_organizacion_lanza_403(self):
        with patch("app.services.auth_context.verificar_token", return_value="u-huerfano"), \
             patch("app.services.organizacion.resolver_organizacion", return_value=None):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(get_auth_context(authorization="Bearer x"))
        self.assertEqual(cm.exception.status_code, 403)

    def test_contexto_completo_expone_organizacion_real(self):
        class FakeCtx:
            organizacion_id = "org-1"
            nombre = "hoktus"
            user_ids_miembros = ["u-real-123", "u-otro"]
            es_admin = True

        with patch("app.services.auth_context.verificar_token", return_value="u-real-123"), \
             patch("app.services.organizacion.resolver_organizacion", return_value=FakeCtx()):
            ctx = asyncio.run(get_auth_context(authorization="Bearer x"))

        self.assertEqual(ctx.actor_user_id, "u-real-123")
        self.assertEqual(ctx.organization_id, "org-1")
        self.assertEqual(ctx.organization_nombre, "hoktus")
        self.assertEqual(ctx.user_ids_organizacion, ["u-real-123", "u-otro"])
        self.assertTrue(ctx.es_admin)


if __name__ == "__main__":
    unittest.main()
