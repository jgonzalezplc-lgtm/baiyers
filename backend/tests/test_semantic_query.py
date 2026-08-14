from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.semantic_query import describe_schema, query_data


class Query:
    def __init__(self): self.calls = []
    def select(self, value): self.calls.append(("select", value)); return self
    def in_(self, field, value): self.calls.append(("in", field, value)); return self
    def eq(self, field, value): self.calls.append(("eq", field, value)); return self
    def gte(self, field, value): self.calls.append(("gte", field, value)); return self
    def order(self, field, desc=False): self.calls.append(("order", field, desc)); return self
    def limit(self, value): self.calls.append(("limit", value)); return self
    def execute(self): return MagicMock(data=[{"id": "1", "estado": "borrador"}])


def actor():
    return ApplicationActorContext("u-2", "org", "Org", ("u-1", "u-2"))


def test_schema_solo_publica_entidades_controladas():
    schema = describe_schema()
    assert "lists" in schema
    assert "auth.users" not in schema


def test_query_inyecta_tenant_y_limite():
    query = Query()
    sb = MagicMock()
    sb.table.return_value = query
    rows = query_data(sb, actor(), {
        "entity": "lists", "fields": ["id", "estado"],
        "filters": [{"field": "estado", "operator": "eq", "value": "borrador"}],
        "limit": 20,
    })
    assert rows[0]["id"] == "1"
    assert ("in", "user_id", ["u-1", "u-2"]) in query.calls
    assert ("limit", 20) in query.calls


@pytest.mark.parametrize("query_request", [
    {"entity": "auth.users"},
    {"entity": "lists", "fields": ["descripcion"]},
    {"entity": "lists", "limit": 1000},
    {"entity": "lists", "filters": [{"field": "id", "operator": "sql", "value": "x"}]},
])
def test_query_rechaza_superficie_no_permitida(query_request):
    with pytest.raises(HTTPException) as error:
        query_data(MagicMock(), actor(), query_request)
    assert error.value.status_code == 422
