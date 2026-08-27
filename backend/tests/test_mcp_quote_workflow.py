from app.services.mcp_quote_workflow import build_web_quote_summary
import asyncio
from unittest.mock import MagicMock

from app.services.mcp_context import ApplicationActorContext


def test_resumen_cotizacion_suma_la_mejor_oferta_clp_por_item():
    result = build_web_quote_summary({
        "list_id": "l1", "nombre": "Obra", "items": [
            {"item": {"cotizacion_id": "c1", "nombre": "Cable", "cantidad": 2, "unidad": "m"}, "quotes": [
                {"relevante": True, "precio_unitario": 1200, "moneda": "CLP", "proveedor": "A"},
                {"relevante": True, "precio_unitario": 1000, "moneda": "CLP", "proveedor": "B"},
            ]},
            {"item": {"cotizacion_id": "c2", "nombre": "Tornillo", "cantidad": 3}, "quotes": [
                {"relevante": True, "precio_unitario": 500, "moneda": "CLP", "proveedor": "C"},
            ]},
        ],
    })
    assert result["resumen"]["total_estimado_clp"] == 3500
    assert result["items"][0]["mejor_oferta_clp"]["proveedor"] == "B"


def test_resumen_no_mezcla_moneda_extranjera_en_total():
    result = build_web_quote_summary({
        "list_id": "l1", "nombre": "Obra", "items": [{
            "item": {"cotizacion_id": "c1", "nombre": "Sensor", "cantidad": 1},
            "quotes": [{"relevante": True, "precio_unitario": 10, "moneda": "USD", "proveedor": "A"}],
        }],
    })
    assert result["resumen"]["total_estimado_clp"] == 0
    assert result["items"][0]["estado"] == "solo_moneda_extranjera"


def test_cotizacion_nueva_con_datos_completos_crea_lista_y_busca(monkeypatch):
    from app.services.mcp_quote_workflow import quote_new_project

    actor = ApplicationActorContext(
        "u1", "o1", "Org", ("u1",), scopes=frozenset({"lists:write"}), client_id="test",
    )
    async def intake(*_args, **_kwargs):
        return {"draft_id": "d1", "ready_to_commit": True, "nombre_lista_sugerido": "Obra",
                "lista_items": [{"nombre_tecnico": "Cable", "cantidad": 2, "unidad": "m"}]}
    async def quoted(*_args, **_kwargs):
        return {"list_id": "l1", "job": {"status": "completed"}, "cotizacion_web": {}}

    create = MagicMock(return_value={"id": "l1"})
    commit = MagicMock()
    monkeypatch.setattr("app.services.project_intake.start_project_intake", intake)
    monkeypatch.setattr("app.services.lista_service.create_list_from_identified_items", create)
    monkeypatch.setattr("app.services.mcp_jobs.commit_draft", commit)
    monkeypatch.setattr("app.services.mcp_quote_workflow.quote_existing_list", quoted)
    result = asyncio.run(quote_new_project(MagicMock(), actor, description="100 m cable", idempotency_key="k1"))

    assert result["estado"] == "cotizado"
    assert result["lista"]["id"] == "l1"
    assert create.call_args.kwargs["idempotency_key"] == "k1:list"
    commit.assert_called_once()
