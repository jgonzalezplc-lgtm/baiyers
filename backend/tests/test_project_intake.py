from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.project_intake import _normalize_items, commit_document_import, commit_project_intake


def actor():
    return ApplicationActorContext("u-actor", "org-1", "Org", ("u-actor",), client_id="codex")


def test_normalize_items_expone_problemas_sin_inventar_datos():
    rows = _normalize_items({"lista_items": [{"nombre_tecnico": "Cable", "cantidad": None, "unidad": ""}]})
    assert rows[0]["issues"] == ["cantidad_faltante", "unidad_faltante"]


def test_commit_document_requiere_confirmacion_explicita():
    with pytest.raises(HTTPException) as error:
        commit_document_import(MagicMock(), actor(), draft_id="d1", list_name=None,
                               idempotency_key="k1", confirmed=False)
    assert error.value.status_code == 409


def test_commit_project_requiere_confirmacion_explicita():
    with pytest.raises(HTTPException) as error:
        commit_project_intake(MagicMock(), actor(), draft_id="d1", list_name=None,
                              idempotency_key="k1", confirmed=False)
    assert error.value.status_code == 409


def test_commit_document_rechaza_draft_con_pendientes(monkeypatch):
    monkeypatch.setattr("app.services.project_intake.get_active_draft", lambda *_: {
        "draft_type": "document_list_import", "payload": {"ready_to_commit": False}
    })
    with pytest.raises(HTTPException) as error:
        commit_document_import(MagicMock(), actor(), draft_id="d1", list_name=None,
                               idempotency_key="k1", confirmed=True)
    assert error.value.status_code == 409


def test_commit_document_crea_lista_y_consumo_unico(monkeypatch):
    monkeypatch.setattr("app.services.project_intake.get_active_draft", lambda *_: {
        "draft_type": "document_list_import", "source_name": "items.xlsx",
        "payload": {"ready_to_commit": True, "lista_items": [{"nombre_tecnico": "Cable"}]},
    })
    create = MagicMock(return_value={"id": "list-1", "items": []})
    committed = MagicMock()
    monkeypatch.setattr("app.services.project_intake.create_list_from_identified_items", create)
    monkeypatch.setattr("app.services.project_intake.commit_draft", committed)
    result = commit_document_import(MagicMock(), actor(), draft_id="d1", list_name="Lista",
                                    idempotency_key="k1", confirmed=True)
    assert result["id"] == "list-1"
    assert create.call_args.kwargs["idempotency_key"] == "k1"
    committed.assert_called_once()
