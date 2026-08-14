import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.purchase_invoice_service import (
    create_purchase_order, get_purchase_order, match_invoice_to_po,
    reconcile_invoice_po, send_purchase_order,
)


def actor():
    return ApplicationActorContext("u1", "o1", "Org", ("u1", "u2"), client_id="codex")


def test_create_y_send_oc_exigen_confirmacion_antes_de_leer_db():
    with pytest.raises(HTTPException):
        asyncio.run(create_purchase_order(MagicMock(), actor(), draft_id="d1", notes=None, confirmed=False))
    with pytest.raises(HTTPException):
        asyncio.run(send_purchase_order(MagicMock(), actor(), "po1", "JVBERg==", confirmed=False))


def test_get_oc_no_expone_token_confirmacion():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value.data = {
        "id": "po1", "user_id": "u1", "token_confirmacion": "secret", "estado": "borrador"
    }
    result = get_purchase_order(sb, actor(), "po1")
    assert "token_confirmacion" not in result


def test_reconcile_invoice_po_es_read_only_y_explica_diferencias(monkeypatch):
    monkeypatch.setattr("app.services.purchase_invoice_service.get_invoice", lambda *_: {
        "id": "f1", "monto_total": 1190, "moneda": "CLP", "proveedor_nombre": "Proveedor"
    })
    monkeypatch.setattr("app.services.purchase_invoice_service.get_purchase_order", lambda *_: {
        "id": "po1", "precio_total": 1190, "moneda": "CLP", "proveedor_nombre": "Proveedor"
    })
    result = reconcile_invoice_po(MagicMock(), actor(), "f1", "po1")
    assert result["matched"] is True
    assert result["amount_delta"] == 0


def test_match_invoice_requiere_confirmacion():
    with pytest.raises(HTTPException) as error:
        match_invoice_to_po(MagicMock(), actor(), "f1", "po1", confirmed=False)
    assert error.value.status_code == 409
