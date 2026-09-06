import asyncio

import pytest
from fastapi import HTTPException

from app.services.empleado.ejecutor import AutorizacionHumana, EjecutorTools
from app.services.mcp_context import ApplicationActorContext


@pytest.fixture
def actor():
    return ApplicationActorContext(
        "u-1", "org-1", "Empresa", ("u-1",),
        scopes=frozenset({"quotes:read", "rfq:send", "po:write"}),
    )


def test_lectura_allowlisteada_se_ejecuta(actor):
    eventos = []
    ejecutor = EjecutorTools(
        {"get_item_quotes": lambda _actor, args: {"id": args["quote_id"]}},
        validar_autorizacion=lambda _actor, _aprobacion: False,
        auditar=eventos.append,
    )
    assert ejecutor.ejecutar(actor, "get_item_quotes", {"quote_id": "q-1"}) == {"id": "q-1"}
    assert eventos[-1].resultado == "ejecutada"


def test_externo_no_acepta_confirmed_del_modelo(actor):
    called = False
    def handler(_actor, _args):
        nonlocal called
        called = True
    ejecutor = EjecutorTools({"send_rfq": handler}, validar_autorizacion=lambda *_: True)
    with pytest.raises(HTTPException, match="autorización humana"):
        ejecutor.ejecutar(actor, "send_rfq", {"confirmed": True})
    assert not called


def test_dinero_exige_aprobacion_valida_y_nunca_pasa_confirmed(actor):
    recibido = {}
    ejecutor = EjecutorTools(
        {"create_purchase_order": lambda _actor, args: recibido.update(args)},
        validar_autorizacion=lambda _actor, aprobacion: aprobacion.responsable_id == "r-1",
    )
    aprobacion = AutorizacionHumana("a-1", "r-1", "create_purchase_order", vigente=True)
    ejecutor.ejecutar(actor, "create_purchase_order", {"list_id": "l-1", "confirmed": True}, autorizacion=aprobacion)
    assert recibido == {"list_id": "l-1"}


def test_handler_no_declarado_no_puede_correr(actor):
    ejecutor = EjecutorTools({"inventada": lambda *_: None}, validar_autorizacion=lambda *_: True)
    with pytest.raises(KeyError):
        ejecutor.ejecutar(actor, "inventada", {})


def test_handler_async_usa_el_borde_async(actor):
    async def handler(_actor, args):
        await asyncio.sleep(0)
        return args
    ejecutor = EjecutorTools({"get_item_quotes": handler}, validar_autorizacion=lambda *_: True)
    assert asyncio.run(ejecutor.ejecutar_async(actor, "get_item_quotes", {"quote_id": "q-1"})) == {"quote_id": "q-1"}
