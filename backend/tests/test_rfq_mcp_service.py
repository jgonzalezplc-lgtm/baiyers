import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.rfq_mcp_service import (
    apply_reply_proposal, get_rfq_status, reject_reply_proposal,
    select_supplier_for_item, send_rfq, suggest_suppliers, sync_supplier_replies,
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


def test_suggest_suppliers_incluye_banco_global_de_la_vista_web(monkeypatch):
    detail = AsyncMock(return_value={"items": [{
        "cotizacion_id": "q1", "nombre": "Cemento", "cantidad": 35,
        "unidad": "saco", "categoria": "construccion",
        "proveedores_recomendados": [{
            "id": "sugerido:ventas@example.cl", "nombre": "Proveedor",
            "email": "ventas@example.cl", "origen": "sugerido",
            "match_label": "Match por producto: cemento",
        }],
    }]})
    monkeypatch.setattr("app.routers.listas.detalle_lista", detail)

    result = asyncio.run(suggest_suppliers(actor(), "l1"))

    assert result["items"][0]["n_candidatos"] == 1
    assert result["items"][0]["proveedores_recomendados"][0]["origen"] == "sugerido"
    assert detail.call_args.args[1].organization_id == "o1"


def test_select_supplier_for_item_delega_origen_sugerido(monkeypatch):
    select = AsyncMock(return_value={"success": True, "seleccionado": True})
    monkeypatch.setattr("app.routers.listas.seleccionar_proveedor_item", select)

    result = asyncio.run(select_supplier_for_item(
        actor(), "l1", "q1", origin="sugerido", email="ventas@example.cl",
    ))

    assert result["success"] is True
    request = select.call_args.args[1]
    assert request.origen == "sugerido"
    assert request.email == "ventas@example.cl"
