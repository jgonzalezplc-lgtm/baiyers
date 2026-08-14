import pytest
from fastapi import HTTPException

from app.services.auth_context import AuthContext
from app.services.mcp_context import ApplicationActorContext


def test_adapta_auth_context_sin_aceptar_identidad_del_cliente():
    auth = AuthContext("user-1", "org-1", "Acme", ["user-1", "user-2"], True)
    actor = ApplicationActorContext.from_auth_context(
        auth, client_id="codex", scopes={"lists:read"}, request_id="req-1"
    )
    assert actor.actor_user_id == "user-1"
    assert actor.organization_user_ids == ("user-1", "user-2")
    assert actor.client_id == "codex"
    assert actor.request_id == "req-1"


def test_scope_y_admin_se_verifican_en_servidor():
    actor = ApplicationActorContext("u", "o", "Org", ("u",), False, scopes=frozenset({"lists:read"}))
    actor.require_scope("lists:read")
    with pytest.raises(HTTPException) as scope_error:
        actor.require_scope("lists:write")
    assert scope_error.value.status_code == 403
    with pytest.raises(HTTPException) as admin_error:
        actor.require_admin()
    assert admin_error.value.status_code == 403
