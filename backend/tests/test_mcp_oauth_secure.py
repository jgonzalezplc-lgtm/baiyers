import asyncio
import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.mcp.oauth import _redirect_uri_valida, _validar_scopes, authorize, registrar_cliente, token


def test_redirect_uri_solo_https_o_loopback_http():
    assert _redirect_uri_valida("https://claude.ai/api/mcp/auth_callback")
    assert _redirect_uri_valida("http://127.0.0.1:9876/callback")
    assert not _redirect_uri_valida("http://evil.example/callback")
    assert not _redirect_uri_valida("https://user:password@example.com/callback")
    assert not _redirect_uri_valida("https://example.com/callback#fragment")


def test_scopes_son_allowlist_y_default_minimo():
    assert "lists:read" in _validar_scopes("")
    with pytest.raises(HTTPException) as error:
        _validar_scopes("lists:read database:drop")
    assert error.value.status_code == 400


def test_dcr_rechaza_redirect_inseguro_sin_escribir():
    with patch("app.mcp.oauth.SUPABASE") as sb, pytest.raises(HTTPException):
        asyncio.run(registrar_cliente({"redirect_uris": ["http://evil.example/callback"]}))
    sb.table.assert_not_called()


def test_authorize_exige_cliente_redirect_pkce_state_y_resource():
    client = {"client_id": "c1", "client_name": "Codex", "redirect_uris": ["http://127.0.0.1:9999/callback"]}
    with patch("app.mcp.oauth._cliente", return_value=client), patch("app.mcp.oauth._guardar_estado") as save:
        with pytest.raises(HTTPException):
            asyncio.run(authorize("c1", client["redirect_uris"][0], "code", "lists:read", "", "challenge", "S256", "http://localhost:8000/api/mcp"))
        with pytest.raises(HTTPException):
            asyncio.run(authorize("c1", "http://127.0.0.1:9998/otro", "code", "lists:read", "state", "challenge", "S256", "http://localhost:8000/api/mcp"))
        with pytest.raises(HTTPException):
            asyncio.run(authorize("c1", client["redirect_uris"][0], "code", "lists:read", "state", "", "S256", "http://localhost:8000/api/mcp"))
    save.assert_not_called()


def test_token_verifica_pkce_client_redirect_y_resource():
    verifier = "a" * 50
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    entry = {
        "client_id": "c1", "redirect_uri": "http://127.0.0.1/callback",
        "resource": "http://localhost:8000/api/mcp", "code_challenge": challenge,
        "user_id": "u1", "scope": "lists:read",
    }
    with patch("app.mcp.oauth._leer_y_consumir_estado", return_value=entry), \
         patch("app.services.organizacion.obtener_organizacion", return_value={"organizacion_id": "org1"}), \
         patch("app.mcp.token_service.issue_token_pair", return_value={"access_token": "at", "refresh_token": "rt", "token_type": "Bearer", "expires_in": 3600, "scope": "lists:read"}), \
         patch("app.mcp.oauth.SUPABASE", MagicMock()):
        response = asyncio.run(token("authorization_code", "code", entry["redirect_uri"], "c1", verifier, None, entry["resource"]))
        assert response.status_code == 200

    with patch("app.mcp.oauth._leer_y_consumir_estado", return_value=entry), pytest.raises(HTTPException) as error:
        asyncio.run(token("authorization_code", "code", entry["redirect_uri"], "c1", "incorrecto", None, entry["resource"]))
    assert error.value.detail["error"] == "invalid_grant"
