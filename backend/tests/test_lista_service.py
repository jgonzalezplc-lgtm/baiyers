import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.lista_service import (
    ListItemInput, add_list_items, build_list_payload, create_list, get_list,
    parse_list_project, remove_list_item, rename_list, update_list_item,
)
from app.services.mcp_context import ApplicationActorContext


def actor():
    return ApplicationActorContext("u-actor", "org-1", "Org", ("u-owner", "u-actor"))


def test_payload_valida_items_y_preserva_identidad_estable():
    data = build_list_payload([ListItemInput("cot-1", " Cable ", 12, "m", "Electricidad")])
    assert data["tipo"] == "lista_cotizacion"
    assert data["items"][0] == {
        "cotizacion_id": "cot-1", "nombre": "Cable", "cantidad": 12,
        "unidad": "m", "partida": "Electricidad", "comparado": False,
    }
    assert parse_list_project({"descripcion": json.dumps(data)}) == data


@pytest.mark.parametrize("items", [[], [ListItemInput("x", "", 1)], [ListItemInput("x", "A", 0)]])
def test_payload_rechaza_listas_invalidas(items):
    with pytest.raises(HTTPException) as error:
        build_list_payload(items)
    assert error.value.status_code == 422


def test_payload_rechaza_cotizacion_duplicada():
    with pytest.raises(HTTPException):
        build_list_payload([ListItemInput("x", "A"), ListItemInput("x", "B")])


def test_create_list_firma_con_actor_verificado():
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = [{"id": "cot-1"}]
    sb.table.return_value.insert.return_value.execute.return_value.data = [{"id": "list-1"}]
    result = create_list(sb, actor(), " Compra mensual ", [ListItemInput("cot-1", "Cable")])
    inserted = sb.table.return_value.insert.call_args.args[0]
    assert inserted["user_id"] == "u-actor"
    assert inserted["nombre"] == "Compra mensual"
    assert result["id"] == "list-1"


def test_create_list_rechaza_cotizacion_de_otra_organizacion():
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = []
    with pytest.raises(HTTPException) as error:
        create_list(sb, actor(), "Lista", [ListItemInput("cot-ajena", "Secreto")])
    assert error.value.status_code == 404


def _project(items=None, definitivos=None):
    data = {"tipo": "lista_cotizacion", "items": items or [{
        "cotizacion_id": "cot-1", "nombre": "Cable", "cantidad": 1,
        "unidad": "m", "comparado": False,
    }], "definitivos": definitivos or {}}
    return {"id": "list-1", "user_id": "u-actor", "nombre": "Lista", "descripcion": json.dumps(data)}


def _sb_for_mutation(project):
    sb = MagicMock()
    # get_list inicial, update y get_list final.
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [project]
    sb.table.return_value.update.return_value.eq.return_value.in_.return_value.execute.return_value.data = [project]
    sb.table.return_value.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = [
        {"id": "cot-1"}, {"id": "cot-2"}
    ]
    return sb


def test_get_list_aisla_por_miembros_de_organizacion():
    project = _project()
    sb = _sb_for_mutation(project)
    result = get_list(sb, actor(), "list-1")
    assert result["items"][0]["cotizacion_id"] == "cot-1"
    sb.table.return_value.select.return_value.eq.return_value.in_.assert_called_with(
        "user_id", ["u-owner", "u-actor"]
    )


def test_rename_list_actualiza_solo_lista_autorizada():
    sb = _sb_for_mutation(_project())
    rename_list(sb, actor(), "list-1", " Nueva ")
    payload = sb.table.return_value.update.call_args.args[0]
    assert payload["nombre"] == "Nueva"


def test_add_update_remove_items_preservan_identidad_y_definitivos():
    project = _project(definitivos={"cot-1": {"proveedor": "A"}})
    sb = _sb_for_mutation(project)
    sb.table.return_value.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = [{"id": "cot-2"}]
    add_list_items(sb, actor(), "list-1", [ListItemInput("cot-2", "Motor", 2, "un")])
    added = json.loads(sb.table.return_value.update.call_args.args[0]["descripcion"])
    assert [item["cotizacion_id"] for item in added["items"]] == ["cot-1", "cot-2"]

    update_list_item(sb, actor(), "list-1", "cot-1", quantity=5, unit="rollo")
    updated = json.loads(sb.table.return_value.update.call_args.args[0]["descripcion"])
    assert updated["items"][0]["cantidad"] == 5

    project_two = _project(items=[*json.loads(project["descripcion"])["items"], {
        "cotizacion_id": "cot-2", "nombre": "Motor", "cantidad": 2,
        "unidad": "un", "comparado": False,
    }], definitivos={"cot-1": {"proveedor": "A"}, "cot-2": {"proveedor": "B"}})
    sb = _sb_for_mutation(project_two)
    remove_list_item(sb, actor(), "list-1", "cot-1")
    removed = json.loads(sb.table.return_value.update.call_args.args[0]["descripcion"])
    assert [item["cotizacion_id"] for item in removed["items"]] == ["cot-2"]
    assert "cot-1" not in removed["definitivos"]


def test_remove_rechaza_dejar_lista_vacia():
    with pytest.raises(HTTPException) as error:
        remove_list_item(_sb_for_mutation(_project()), actor(), "list-1", "cot-1")
    assert error.value.status_code == 409
