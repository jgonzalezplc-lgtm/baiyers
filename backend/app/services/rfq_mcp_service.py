"""Fachada MCP para matriz, RFQ y respuestas del agente de correo existente."""
from typing import Any, Optional

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext


def _confirmed(value: bool, action: str) -> None:
    if value is not True:
        raise HTTPException(status_code=409, detail=f"Se requiere confirmación explícita para {action}")


async def get_supplier_matrix(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.listas import matriz_proveedores_confianza
    return await matriz_proveedores_confianza(list_id, actor.to_auth_context())


async def set_supplier_matrix(actor: ApplicationActorContext, list_id: str, selections: list[dict[str, Any]]) -> dict:
    from app.routers.listas import GuardarMatrizConfianzaRequest, guardar_matriz_proveedores_confianza
    try:
        request = GuardarMatrizConfianzaRequest(selecciones=selections)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Selecciones de proveedor inválidas") from exc
    return await guardar_matriz_proveedores_confianza(list_id, request, actor.to_auth_context())


async def prepare_rfq(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.rfq import PrepararRFQRequest, preparar_rfq
    return await preparar_rfq(list_id, PrepararRFQRequest(), actor.to_auth_context())


async def get_rfq_preview(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.rfq import listar_rfq
    return await listar_rfq(list_id, actor.to_auth_context())


async def update_rfq_draft(
    actor: ApplicationActorContext, list_id: str, batch_id: str,
    *, recipient_email: str, subject: str, body: str,
) -> dict:
    from app.routers.rfq import EditarRFQRequest, editar_rfq
    request = EditarRFQRequest(destinatario_email=recipient_email, subject=subject, body=body)
    return await editar_rfq(list_id, batch_id, request, actor.to_auth_context())


async def send_rfq(
    actor: ApplicationActorContext, list_id: str, batch_id: str, *, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "enviar la RFQ")
    from app.routers.rfq import EnviarRFQRequest, enviar_rfq
    return await enviar_rfq(list_id, batch_id, EnviarRFQRequest(), actor.to_auth_context())


async def get_rfq_status(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.rfq import listar_rfq
    from app.routers.gmail import listar_conversaciones
    preview = await listar_rfq(list_id, actor.to_auth_context())
    conversations = await listar_conversaciones(actor.to_auth_context())
    related = [row for row in conversations if row.get("lista_proyecto_id") == list_id]
    batches = preview.get("batches") or []
    raw_states = [row.get("estado") for row in batches]
    replied = sum(1 for row in related if row.get("estado") in {
        "supplier_replied", "partially_answered", "complete", "closed"
    })
    if not batches: canonical = "draft"
    elif any(state == "delivery_uncertain" for state in raw_states): canonical = "delivery_uncertain"
    elif any(state in {"draft", "ready_to_send"} for state in raw_states): canonical = "ready"
    elif any(state == "sending" for state in raw_states): canonical = "sending"
    elif replied == len(batches) and batches: canonical = "answered"
    elif replied: canonical = "partially_answered"
    elif all(state == "sent" for state in raw_states): canonical = "sent"
    elif any(state == "failed" for state in raw_states): canonical = "failed"
    else: canonical = "draft"
    return {"list_id": list_id, "canonical_status": canonical, "batches": batches,
            "conversations": related, "replied": replied}


async def sync_supplier_replies(actor: ApplicationActorContext, *, confirmed: bool) -> dict:
    _confirmed(confirmed, "sincronizar el correo")
    from app.routers.gmail import sincronizar_respuestas
    return await sincronizar_respuestas(actor.to_auth_context())


async def list_supplier_replies(actor: ApplicationActorContext, list_id: Optional[str] = None) -> dict:
    from app.routers.gmail import listar_conversaciones
    rows = await listar_conversaciones(actor.to_auth_context())
    if list_id is not None:
        rows = [row for row in rows if row.get("lista_proyecto_id") == list_id]
    return {"total": len(rows), "replies": rows}


async def get_supplier_reply(actor: ApplicationActorContext, conversation_id: str) -> dict:
    from app.routers.gmail import detalle_conversacion
    return await detalle_conversacion(conversation_id, actor.to_auth_context())


async def apply_reply_proposal(
    actor: ApplicationActorContext, proposal_id: str, *, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "aplicar la propuesta")
    from app.routers.gmail import RevisarPropuestaRequest, aplicar_propuesta
    return await aplicar_propuesta(proposal_id, RevisarPropuestaRequest(), actor.to_auth_context())


async def reject_reply_proposal(
    actor: ApplicationActorContext, proposal_id: str, *, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "rechazar la propuesta")
    from app.routers.gmail import RevisarPropuestaRequest, rechazar_propuesta
    return await rechazar_propuesta(proposal_id, RevisarPropuestaRequest(), actor.to_auth_context())
