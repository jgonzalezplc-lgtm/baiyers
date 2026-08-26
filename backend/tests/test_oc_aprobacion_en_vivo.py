"""El candado de aprobación lee el estado ahora, no la foto del borrador.

Caso real (2026-08-26): se preparó la OC, Baiyer la bloqueó por falta de
aprobación, el responsable aprobó… y crear la OC seguía fallando. Hubo que
regenerar el borrador para que la aprobación "existiera".

Causa: `prepare_purchase_order` guardaba `approval_status` dentro del payload del
draft, y `create_purchase_order` evaluaba ese valor congelado. Entre preparar y
crear es normal —y esperado— que alguien apruebe.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import purchase_invoice_service as svc
from app.services.mcp_context import ApplicationActorContext


def actor():
    return ApplicationActorContext("user-1", "org-1", "Org", ("owner", "user-1"), client_id="codex")


PAYLOAD = {
    "list_id": "lista-1", "cotizacion_id": "cot-1", "resultado_id": "res-1",
    "nombre_item": "Ampolleta LED E27 100W", "proveedor_nombre": "Joaquín González",
    "proveedor_email": "joaquin.gonzalez.pl@usach.cl", "cantidad": 1.0,
    "precio_unitario": 19990.0, "moneda": "CLP", "condiciones_pago": "Transferencia",
    "plazo_entrega": "48h",
    # La foto vieja: cuando se preparó el borrador todavía estaba pendiente.
    "approval_status": "pendiente",
}


def _crear(monkeypatch, estado_actual, hay_workflow=True):
    """Ejecuta create_purchase_order con un estado de aprobación real dado."""
    monkeypatch.setattr(svc, "get_active_draft", lambda *_a, **_k: {
        "draft_type": "purchase_order", "payload": dict(PAYLOAD),
    })
    monkeypatch.setattr(svc, "commit_draft", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.services.workflow_execution.obtener_workflow_activo",
        lambda *_a, **_k: {"id": "wf-1"} if hay_workflow else None,
    )
    monkeypatch.setattr(svc, "get_list", lambda *_a, **_k: {"aprobacion": {"estado": estado_actual}})

    creada = {}

    async def fake_crear_oc(request, _ctx):
        creada["request"] = request
        return {"id": "oc-1", "numero_oc": "OC-2026-BVITAL-0001"}

    monkeypatch.setattr("app.routers.oc.crear_oc", fake_crear_oc)
    resultado = asyncio.run(svc.create_purchase_order(
        MagicMock(), actor(), draft_id="draft-1", notes=None, confirmed=True,
    ))
    return resultado, creada


# ─── El bug: aprobar después de preparar ─────────────────────────────────────

def test_aprobar_despues_de_preparar_ya_no_exige_regenerar(monkeypatch):
    """El borrador dice "pendiente" pero la lista YA está aprobada."""
    resultado, creada = _crear(monkeypatch, "aprobado")
    assert resultado["numero_oc"] == "OC-2026-BVITAL-0001"
    assert creada["request"].precio_unitario == 19990.0


def test_sigue_bloqueando_si_de_verdad_esta_pendiente(monkeypatch):
    with pytest.raises(HTTPException) as error:
        _crear(monkeypatch, "pendiente")
    assert error.value.status_code == 409
    assert error.value.detail["estado_actual"] == "pendiente"


def test_rechazo_posterior_no_se_cuela_con_la_foto_vieja(monkeypatch):
    """El caso inverso, más peligroso: aprobada al preparar, rechazada después."""
    payload_aprobado = {**PAYLOAD, "approval_status": "aprobado"}
    monkeypatch.setattr(svc, "get_active_draft", lambda *_a, **_k: {
        "draft_type": "purchase_order", "payload": payload_aprobado,
    })
    monkeypatch.setattr(
        "app.services.workflow_execution.obtener_workflow_activo", lambda *_a, **_k: {"id": "wf-1"}
    )
    monkeypatch.setattr(svc, "get_list", lambda *_a, **_k: {"aprobacion": {"estado": "rechazado"}})
    with pytest.raises(HTTPException) as error:
        asyncio.run(svc.create_purchase_order(
            MagicMock(), actor(), draft_id="draft-1", notes=None, confirmed=True,
        ))
    assert error.value.detail["estado_actual"] == "rechazado"


# ─── Los mensajes dicen qué hacer ────────────────────────────────────────────

@pytest.mark.parametrize("estado,fragmento", [
    ("pendiente", "no hace falta regenerar el borrador"),
    ("rechazado", "volvé a solicitarla"),
    ("aprobado_con_observaciones", "aprobación limpia"),
    ("expirado", "request_approval"),
    (None, "request_approval"),
])
def test_cada_estado_explica_el_siguiente_paso(monkeypatch, estado, fragmento):
    """Un 409 que no nombra la acción siguiente obliga al cliente a adivinar."""
    with pytest.raises(HTTPException) as error:
        _crear(monkeypatch, estado)
    assert fragmento in error.value.detail["mensaje"]


def test_sin_aprobacion_solicitada_lo_dice_explicito(monkeypatch):
    with pytest.raises(HTTPException) as error:
        _crear(monkeypatch, None)
    assert error.value.detail["estado_actual"] == "no_solicitada"


# ─── Casos borde ─────────────────────────────────────────────────────────────

def test_sin_workflow_activo_no_se_exige_aprobacion(monkeypatch):
    """Organizaciones sin ciclo configurado conservan el flujo de siempre."""
    resultado, _ = _crear(monkeypatch, None, hay_workflow=False)
    assert resultado["id"] == "oc-1"


def test_un_fallo_al_releer_no_se_asume_aprobado(monkeypatch):
    """Emitir una OC sin autorización confirmada es peor que fallar."""
    def explota(*_a, **_k):
        raise RuntimeError("supabase caído")
    monkeypatch.setattr(svc, "get_list", explota)
    assert svc._estado_aprobacion_actual(MagicMock(), actor(), "lista-1") is None


def test_sin_list_id_no_consulta(monkeypatch):
    with patch.object(svc, "get_list") as consulta:
        assert svc._estado_aprobacion_actual(MagicMock(), actor(), None) is None
        consulta.assert_not_called()
