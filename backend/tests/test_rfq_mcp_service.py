import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.rfq_mcp_service import (
    apply_reply_proposal, get_rfq_status, reject_reply_proposal,
    send_rfq, sync_supplier_replies,
)


def actor():
    return ApplicationActorContext("u1", "o1", "Org", ("u1", "u2"), is_admin=True, client_id="codex")


@pytest.mark.parametrize("call", [
    lambda a: send_rfq(a, "l1", "b1", confirmed=False),
    lambda a: sync_supplier_replies(a, confirmed=False),
    lambda a: apply_reply_proposal(a, "p1", confirmed=False),
    lambda a: reject_reply_proposal(a, "p1", confirmed=False),
])
def test_acciones_externas_o_de_revision_exigen_confirmacion(call):
    with pytest.raises(HTTPException) as error:
        asyncio.run(call(actor()))
    assert error.value.status_code == 409


def test_contexto_mcp_se_adapta_sin_perder_organizacion():
    ctx = actor().to_auth_context()
    assert ctx.actor_user_id == "u1"
    assert ctx.organization_id == "o1"
    assert ctx.user_ids_organizacion == ["u1", "u2"]
    assert ctx.es_admin is True


def test_estado_rfq_combina_batches_y_respuestas(monkeypatch):
    monkeypatch.setattr("app.routers.rfq.listar_rfq", AsyncMock(return_value={
        "batches": [{"id": "b1", "estado": "sent"}, {"id": "b2", "estado": "sent"}]
    }))
    monkeypatch.setattr("app.routers.gmail.listar_conversaciones", AsyncMock(return_value=[
        {"id": "c1", "lista_proyecto_id": "l1", "estado": "supplier_replied"},
        {"id": "c2", "lista_proyecto_id": "otra", "estado": "closed"},
    ]))
    result = asyncio.run(get_rfq_status(actor(), "l1"))
    assert result["canonical_status"] == "partially_answered"
    assert result["replied"] == 1
    assert len(result["conversations"]) == 1


def test_send_rfq_confirmado_delega_con_actor_verificado(monkeypatch):
    send = AsyncMock(return_value={"success": True, "thread_id": "t1"})
    monkeypatch.setattr("app.routers.rfq.enviar_rfq", send)
    result = asyncio.run(send_rfq(actor(), "l1", "b1", confirmed=True))
    assert result["thread_id"] == "t1"
    delegated_ctx = send.call_args.args[3]
    assert delegated_ctx.organization_id == "o1"
