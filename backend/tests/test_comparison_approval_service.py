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


# ─── price_clp: conversión de moneda y override manual ───────────────────────
# Antes el 409 de "oferta sin precio" se evaluaba antes de mirar price_clp, así que el
# parámetro era inalcanzable en la ruta CLP (caso real: correo del WC del 2026-08-25,
# donde la extracción falló por timeout y las ofertas quedaron con precio null).

def _preparar_seleccion(monkeypatch, oferta):
    monkeypatch.setattr("app.services.comparison_approval_service.get_list", lambda *_: {
        "items": [{"cotizacion_id": "c1", "nombre": "Sello para WC", "cantidad": 1}],
        "definitivos": {},
    })
    monkeypatch.setattr(
        "app.services.comparison_approval_service.get_item_quotes",
        lambda *_args, **_kwargs: {"quotes": [oferta]},
    )
    capturado = {}

    async def fake_elegir(list_id, request, _ctx):
        capturado["request"] = request
        return {"ok": True}

    monkeypatch.setattr("app.routers.listas.elegir_definitivo", fake_elegir)
    return capturado


def _oferta(**extra):
    base = {"resultado_id": "r1", "precio": None, "precio_cotizado": None, "relevante": True,
            "plazo_entrega": None, "stock": None, "proveedor": "Joaquín González",
            "url": None, "fuente": "gmail", "moneda": "CLP"}
    return {**base, **extra}


def test_select_final_sin_precio_y_sin_price_clp_sigue_siendo_409(monkeypatch):
    _preparar_seleccion(monkeypatch, _oferta())
    with pytest.raises(HTTPException) as error:
        asyncio.run(select_final_quote(
            MagicMock(), actor(), list_id="l1", quote_id="c1", result_id="r1",
            price_clp=None, confirmed=True,
        ))
    assert error.value.status_code == 409
    assert "price_clp" in error.value.detail


def test_select_final_sin_precio_acepta_override_manual(monkeypatch):
    capturado = _preparar_seleccion(monkeypatch, _oferta())
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"notas_respuesta": None})

    asyncio.run(select_final_quote(
        sb, actor(), list_id="l1", quote_id="c1", result_id="r1",
        price_clp=1750, confirmed=True,
    ))

    assert capturado["request"].precio == 1750.0
    assert capturado["request"].precio_clp == 1750.0
    assert capturado["request"].moneda == "CLP"


def test_override_manual_deja_nota_de_auditoria(monkeypatch):
    _preparar_seleccion(monkeypatch, _oferta())
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"notas_respuesta": "previa"})

    asyncio.run(select_final_quote(
        sb, actor(), list_id="l1", quote_id="c1", result_id="r1",
        price_clp=1750, confirmed=True,
    ))

    escrito = sb.table.return_value.update.call_args[0][0]
    assert escrito["precio_cotizado"] == 1750.0
    assert escrito["moneda_cotizada"] == "CLP"
    # El rastro importa: quien revise la OC debe poder distinguirlo de un precio cotizado.
    assert "manualmente" in escrito["notas_respuesta"]
    assert escrito["notas_respuesta"].startswith("previa")


def test_price_clp_no_pisa_un_precio_ya_cotizado(monkeypatch):
    """Con precio real persistido, price_clp no debe sobrescribirlo en la ruta CLP."""
    capturado = _preparar_seleccion(monkeypatch, _oferta(precio_cotizado=1750))
    sb = MagicMock()

    asyncio.run(select_final_quote(
        sb, actor(), list_id="l1", quote_id="c1", result_id="r1",
        price_clp=999, confirmed=True,
    ))

    assert capturado["request"].precio == 1750
    sb.table.return_value.update.assert_not_called()


def test_moneda_extranjera_sigue_exigiendo_price_clp(monkeypatch):
    _preparar_seleccion(monkeypatch, _oferta(precio_cotizado=100, moneda="USD"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(select_final_quote(
            MagicMock(), actor(), list_id="l1", quote_id="c1", result_id="r1",
            price_clp=None, confirmed=True,
        ))
    assert error.value.status_code == 422


def test_decide_request_confirmado_usa_token_solo_despues_de_autorizar(monkeypatch):
    request = {"id": "a1", "estado": "pendiente", "responsable_id": "resp-1", "token": "secret"}
    monkeypatch.setattr("app.services.comparison_approval_service._authorized_request", lambda *_: request)
    decide = MagicMock()

    async def fake_decide(token, req, ctx):
        # El ctx no es opcional: `decidir` vuelve a verificar la identidad
        # contra el autorizador designado, así que el actor tiene que viajar.
        decide(token, req.decision, ctx.actor_user_id)
        return {"ok": True, "estado": "aprobado"}

    monkeypatch.setattr("app.routers.aprobaciones.decidir", fake_decide)
    result = asyncio.run(decide_request(
        MagicMock(), actor(), request_id="a1", decision="aprobar", comment=None,
        item_decisions={}, confirmed=True,
    ))
    assert result["estado"] == "aprobado"
    decide.assert_called_once_with("secret", "aprobar", "approver-user")
