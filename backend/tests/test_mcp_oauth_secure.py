import asyncio
import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.mcp.oauth import (
    SessionConsentRequest,
    _redirect_uri_valida,
    _validar_scopes,
    authorization_request,
    authorize,
    consent,
    consent_session,
    registrar_cliente,
    token,
)


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


def test_authorize_valido_guarda_request_opaco_y_redirige_al_frontend():
    redirect_uri = "http://127.0.0.1:9999/callback"
    client = {
        "client_id": "c1",
        "client_name": "<Codex>",
        "redirect_uris": [redirect_uri],
    }
    with patch("app.mcp.oauth._cliente", return_value=client), \
         patch("app.mcp.oauth._guardar_estado") as save, \
         patch("app.mcp.oauth.secrets.token_urlsafe", return_value="r" * 43):
        response = asyncio.run(authorize(
            "c1", redirect_uri, "code", "lists:read", "state-valid",
            "a" * 43, "S256", "http://localhost:8000/api/mcp",
        ))

    assert response.status_code == 302
    assert response.headers["location"].endswith("/mcp/autorizar?request=" + "r" * 43)
    save.assert_called_once_with(
        "pending_" + "r" * 43,
        {
            "client_id": "c1",
            "redirect_uri": redirect_uri,
            "scope": "lists:read",
            "state": "state-valid",
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
            "resource": "http://localhost:8000/api/mcp",
        },
    )


def test_request_preview_no_expone_redirect_ni_pkce():
    pending = {
        "client_id": "c1",
        "redirect_uri": "http://127.0.0.1:9999/callback",
        "scope": "lists:read quotes:write",
        "code_challenge": "a" * 43,
    }
    with patch("app.mcp.oauth._leer_estado_vigente", return_value=pending), \
         patch("app.mcp.oauth._cliente", return_value={"client_name": "Codex"}):
        response = asyncio.run(authorization_request("r" * 43))

    assert response == {"client_name": "Codex", "scopes": ["lists:read", "quotes:write"]}


def test_consent_session_verifica_token_antes_de_consumir():
    pending = {"redirect_uri": "http://127.0.0.1/callback", "state": "client-state"}
    with patch("app.mcp.oauth._leer_estado_vigente", return_value=pending), \
         patch("app.mcp.oauth._leer_y_consumir_estado") as consume, \
         patch("app.services.auth_context.verificar_token", side_effect=HTTPException(401, "Token inválido")), \
         pytest.raises(HTTPException) as error:
        asyncio.run(consent_session(
            SessionConsentRequest(request_id="r" * 43),
            "Bearer vencido",
        ))

    assert error.value.status_code == 401
    consume.assert_not_called()


def test_consent_session_emite_codigo_para_usuario_de_sesion():
    pending = {
        "redirect_uri": "http://127.0.0.1/callback?source=codex",
        "state": "client-state",
    }
    with patch("app.mcp.oauth._leer_estado_vigente", return_value=pending), \
         patch("app.mcp.oauth._leer_y_consumir_estado", return_value=pending) as consume, \
         patch("app.services.auth_context.verificar_token", return_value="user-1"), \
         patch("app.mcp.oauth._emitir_codigo", return_value="code-1") as emitir:
        response = asyncio.run(consent_session(
            SessionConsentRequest(request_id="r" * 43),
            "Bearer valido",
        ))

    assert response["redirect_url"] == "http://127.0.0.1/callback?source=codex&code=code-1&state=client-state"
    consume.assert_called_once_with("pending_" + "r" * 43)
    emitir.assert_called_once_with(pending, "user-1")


def test_cancelar_consent_session_consume_request_sin_exigir_sesion():
    pending = {"redirect_uri": "http://127.0.0.1/callback", "state": "client-state"}
    with patch("app.mcp.oauth._leer_estado_vigente", return_value=pending), \
         patch("app.mcp.oauth._leer_y_consumir_estado", return_value=pending):
        response = asyncio.run(consent_session(
            SessionConsentRequest(request_id="r" * 43, action="deny"),
            None,
        ))

    assert response["redirect_url"] == "http://127.0.0.1/callback?error=access_denied&state=client-state"


def test_consent_no_consume_estado_si_credenciales_son_invalidas():
    pending = {"redirect_uri": "http://127.0.0.1/callback", "state": "state"}
    fake_client = MagicMock()
    fake_client.auth.sign_in_with_password.side_effect = RuntimeError("invalid")
    with patch("app.mcp.oauth._leer_estado_vigente", return_value=pending), \
         patch("app.mcp.oauth._leer_y_consumir_estado") as consume, \
         patch("app.mcp.oauth.create_client", return_value=fake_client), \
         pytest.raises(HTTPException) as error:
        asyncio.run(consent("state", "user@example.com", "incorrecta", "allow"))

    assert error.value.status_code == 401
    consume.assert_not_called()


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
