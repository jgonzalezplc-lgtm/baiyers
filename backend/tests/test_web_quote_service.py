import json
import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.web_quote_service import _target_quotes, get_item_quotes, start_web_quote


def actor():
    return ApplicationActorContext("u-actor", "org-1", "Org", ("u-owner", "u-actor"), client_id="codex")


def _quote_query(sb, rows):
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = rows


def test_target_quote_exige_un_solo_tipo_de_objetivo():
    with pytest.raises(HTTPException):
        _target_quotes(MagicMock(), actor(), list_id=None, quote_id=None)
    with pytest.raises(HTTPException):
        _target_quotes(MagicMock(), actor(), list_id="l1", quote_id="c1")


def test_target_quote_rechaza_cotizacion_ajena():
    sb = MagicMock()
    _quote_query(sb, [])
    with pytest.raises(HTTPException) as error:
        _target_quotes(sb, actor(), list_id=None, quote_id="c-ajena")
    assert error.value.status_code == 404


def test_get_item_quotes_normaliza_metadata_y_filtra_propiedad():
    sb = MagicMock()
    quote_result = MagicMock(data=[{"id": "c1", "nombre_identificado": "Cable"}])
    offers_result = MagicMock(data=[{
        "id": "r1", "cotizacion_id": "c1", "proveedor_nombre": "Proveedor",
        "precio": 1000, "moneda": "CLP", "fuente": "manual", "relevante": True,
        "metadata": json.dumps({"fuente_label": "Sodimac", "rating": 4.8}),
    }])
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = quote_result
    sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = offers_result
    result = get_item_quotes(sb, actor(), "c1")
    assert result["quotes"][0]["fuente"] == "Sodimac"
    assert result["quotes"][0]["rating"] == 4.8


def test_start_web_quote_crea_job_idempotente_y_lo_programa(monkeypatch):
    sb = MagicMock()
    monkeypatch.setattr("app.services.web_quote_service._target_quotes", lambda *args, **kwargs: [{"id": "c1"}])
    create = MagicMock(return_value={"id": "j1", "status": "queued", "progress": 0})
    schedule = MagicMock()
    monkeypatch.setattr("app.services.web_quote_service.create_job", create)
    monkeypatch.setattr("app.services.web_quote_service._schedule", schedule)
    result = asyncio.run(start_web_quote(
        sb, actor(), list_id=None, quote_id="c1", idempotency_key="k1"
    ))
    assert result["job"]["id"] == "j1"
    assert create.call_args.kwargs["idempotency_key"] == "k1"
    schedule.assert_called_once()
