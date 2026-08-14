import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.comparison_approval_service import (
    _authorized_request, compare_item, decide_request, select_final_quote,
)
from app.services.mcp_context import ApplicationActorContext


def actor():
    return ApplicationActorContext("approver-user", "org-1", "Org", ("owner", "approver-user"), client_id="codex")


def test_compare_item_calcula_total_y_campos_faltantes(monkeypatch):
    monkeypatch.setattr("app.services.comparison_approval_service.get_list", lambda *_: {
        "items": [{"cotizacion_id": "c1", "nombre": "Cable", "cantidad": 3}],
        "definitivos": {},
    })
    monkeypatch.setattr("app.services.comparison_approval_service.get_item_quotes", lambda *_args, **_kwargs: {
        "quotes": [{"resultado_id": "r1", "precio": 100, "precio_cotizado": None,
                    "relevante": True, "plazo_entrega": None, "stock": None}]
    })
    result = compare_item(MagicMock(), actor(), "l1", "c1")
    assert result["quotes"][0]["total_linea"] == 300
    assert result["quotes"][0]["missing_fields"] == ["plazo_entrega", "disponibilidad"]


def _sb_approval(request, responsible):
    sb = MagicMock()
    request_result = MagicMock(data=request)
    responsible_result = MagicMock(data=responsible)
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value = request_result
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = responsible_result
    return sb


def test_decision_mcp_rechaza_solicitud_legacy_sin_responsable():
    sb = _sb_approval({"id": "a1", "estado": "pendiente", "responsable_id": None}, None)
    with pytest.raises(HTTPException) as error:
        _authorized_request(sb, actor(), "a1")
    assert error.value.status_code == 403


def test_decision_mcp_rechaza_actor_no_asignado():
    sb = _sb_approval({"id": "a1", "estado": "pendiente", "responsable_id": "resp-1"}, None)
    with pytest.raises(HTTPException) as error:
        _authorized_request(sb, actor(), "a1")
    assert error.value.status_code == 403


def test_select_final_exige_confirmacion_antes_de_leer_oferta():
    with pytest.raises(HTTPException) as error:
        asyncio.run(select_final_quote(
            MagicMock(), actor(), list_id="l1", quote_id="c1", result_id="r1",
            price_clp=None, confirmed=False,
        ))
    assert error.value.status_code == 409


def test_decide_request_confirmado_usa_token_solo_despues_de_autorizar(monkeypatch):
    request = {"id": "a1", "estado": "pendiente", "responsable_id": "resp-1", "token": "secret"}
    monkeypatch.setattr("app.services.comparison_approval_service._authorized_request", lambda *_: request)
    decide = MagicMock()

    async def fake_decide(token, req):
        decide(token, req.decision)
        return {"ok": True, "estado": "aprobado"}

    monkeypatch.setattr("app.routers.aprobaciones.decidir", fake_decide)
    result = asyncio.run(decide_request(
        MagicMock(), actor(), request_id="a1", decision="aprobar", comment=None,
        item_decisions={}, confirmed=True,
    ))
    assert result["estado"] == "aprobado"
    decide.assert_called_once_with("secret", "aprobar")
