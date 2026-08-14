import asyncio
from unittest.mock import patch

from app.mcp.token_service import BaiyerTokenVerifier, token_hash


def test_token_hash_no_guarda_credencial_cruda():
    assert token_hash("secreto") != "secreto"
    assert len(token_hash("secreto")) == 64


def test_verifier_rechaza_token_de_otro_resource():
    row = {
        "id": "t1", "user_id": "u1", "organization_id": "o1", "client_id": "c1",
        "scopes": ["lists:read"], "resource": "https://otro.example/mcp",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    with patch("app.mcp.token_service.load_token", return_value=row):
        assert asyncio.run(BaiyerTokenVerifier().verify_token("raw")) is None
