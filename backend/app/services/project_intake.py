"""Intake conversacional y documental compartido por web e integraciones MCP."""
import hashlib
from typing import Any, Optional

from fastapi import HTTPException

from app.services.lista_service import create_list_from_identified_items
from app.services.mcp_context import ApplicationActorContext
from app.services.mcp_jobs import commit_draft, create_draft, get_active_draft, update_active_draft


# Señales de que el usuario mandó un documento y el cliente lo resumió en texto.
# Cortas y de alta señal a propósito: una lista larga bloquearía intakes legítimos.
_SENALES_ADJUNTO = (
    "adjunto", "adjunta", "adjuntos", "adjuntas", "adjunté", "adjunte",
    "el pdf", "este pdf", "el documento", "el archivo", "la planilla",
    "el excel", "la cotización que envío", "lo que envío", "el presupuesto que mando",
)


def menciona_adjunto(texto: Optional[str]) -> bool:
    """¿El texto delata un documento que no llegó como archivo?

    `identify_intake` enciende el modo de cubicación cuando NO hay archivo
    (`modo_cubicacion_conversacional=not bool(file_base64)`). Si el cliente
    resume un PDF en texto, Baiyer no tiene las cantidades y entra a dimensionar
    desde cero: para un proyecto solar eso significa pedir el consumo en kWh/mes.

    Pasó de verdad (2026-08-26): el usuario adjuntó un PDF con 15 ítems ya
    itemizados y 6,5 kWp definidos, el cliente llamó `start_project_intake` con
    un resumen, y Baiyer preguntó el consumo — un dato que estaba en la página 1
    y que además ya no hacía falta.
    """
    plano = (texto or "").lower()
    return any(senal in plano for senal in _SENALES_ADJUNTO)


def _normalize_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for position, raw in enumerate(result.get("lista_items") or []):
        name = str(raw.get("nombre_tecnico") or "").strip()
        quantity = raw.get("cantidad")
        unit = str(raw.get("unidad") or "").strip()
        issues = []
        if not name: issues.append("nombre_faltante")
        if quantity in (None, "", 0): issues.append("cantidad_faltante")
        if not unit: issues.append("unidad_faltante")
        items.append({**raw, "position": position, "nombre_tecnico": name,
                      "cantidad": quantity, "unidad": unit, "issues": issues})
    return items


async def identify_intake(
    actor: ApplicationActorContext,
    *,
    description: Optional[str] = None,
    file_base64: Optional[str] = None,
    file_name: Optional[str] = None,
    file_mime: Optional[str] = None,
    industry: Optional[str] = None,
    answers: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Reutiliza el identificador canónico sin una llamada HTTP interna."""
    from app.routers.identificar import IdentificarRequest, identificar_item
    request = IdentificarRequest(
        descripcion=description, archivo_base64=file_base64,
        archivo_nombre=file_name, archivo_mime=file_mime,
        industria_empresa=industry, modo_cubicacion_conversacional=not bool(file_base64),
        respuestas_cubicacion=answers, user_id=actor.actor_user_id,
    )
    # `ctx=None` explícito: acá no hay request HTTP, el actor ya viene verificado
    # aguas arriba y viaja en `req.user_id`. Sin esto, el parámetro toma el
    # objeto `Depends` como valor y revienta con AttributeError.
    result = await identificar_item(request, ctx=None)
    result = dict(result)
    result["lista_items"] = _normalize_items(result)
    result["ready_to_commit"] = (
        result.get("estado_flujo") == "listo"
        and bool(result["lista_items"])
        and not any(item["issues"] for item in result["lista_items"])
    )
    return result


async def preview_document_import(
    sb,
    actor: ApplicationActorContext,
    *,
    file_base64: str,
    file_name: str,
    file_mime: str,
    description: Optional[str] = None,
    industry: Optional[str] = None,
) -> dict:
    result = await identify_intake(
        actor, description=description, file_base64=file_base64,
        file_name=file_name, file_mime=file_mime, industry=industry,
    )
    try:
        source_hash = hashlib.sha256(file_base64.encode("ascii")).hexdigest()
    except UnicodeEncodeError as exc:
        raise HTTPException(status_code=422, detail="El documento debe enviarse como base64") from exc
    draft = create_draft(
        sb, actor, "document_list_import", result,
        source_name=file_name, source_mime=file_mime, source_hash=source_hash,
    )
    return {"draft_id": draft["id"], "expires_at": draft.get("expires_at"), **result}


async def start_project_intake(
    sb, actor: ApplicationActorContext, *, description: str,
    industry: Optional[str] = None, sin_archivo_disponible: bool = False,
) -> dict:
    # Se corta ANTES de llamar al modelo: seguir costaría una llamada a Gemini y
    # un turno entero para terminar preguntando datos que el documento ya trae.
    # `sin_archivo_disponible` es la salida para cuando el usuario efectivamente
    # no puede mandar el archivo — si no, esto sería un callejón sin salida.
    if not sin_archivo_disponible and menciona_adjunto(description):
        raise HTTPException(status_code=409, detail={
            "error": "documento_no_adjuntado",
            "mensaje": (
                "El texto menciona un documento pero no llegó ningún archivo. Enviá el "
                "archivo con `preview_document_import`: trae las cantidades y evita que "
                "Baiyer las tenga que calcular preguntando."
            ),
            "accion": "preview_document_import",
            "override": "Si el usuario no tiene el archivo, repetí esta llamada con sin_archivo_disponible=true.",
        })
    result = await identify_intake(actor, description=description, industry=industry)
    payload = {**result, "conversation": description, "industry": industry}
    draft = create_draft(sb, actor, "project_intake", payload, source_name="prompt")
    return {"draft_id": draft["id"], "expires_at": draft.get("expires_at"), **result}


async def continue_project_intake(
    sb, actor: ApplicationActorContext, *, draft_id: str,
    answers: dict[str, Any],
) -> dict:
    draft = get_active_draft(sb, actor, draft_id)
    if draft.get("draft_type") != "project_intake":
        raise HTTPException(status_code=422, detail="El draft no corresponde a un proyecto")
    previous = draft.get("payload") or {}
    result = await identify_intake(
        actor, description=previous.get("conversation"),
        industry=previous.get("industry"), answers=answers,
    )
    payload = {**result, "conversation": previous.get("conversation"),
               "industry": previous.get("industry"), "answers": answers}
    update_active_draft(sb, actor, draft_id, payload)
    return {"draft_id": draft_id, **result}


def commit_project_intake(
    sb, actor: ApplicationActorContext, *, draft_id: str,
    list_name: Optional[str], idempotency_key: str, confirmed: bool,
) -> dict:
    if confirmed is not True:
        raise HTTPException(status_code=409, detail="Se requiere confirmación explícita para crear la lista")
    draft = get_active_draft(sb, actor, draft_id)
    if draft.get("draft_type") != "project_intake":
        raise HTTPException(status_code=422, detail="El draft no corresponde a un proyecto")
    payload = draft.get("payload") or {}
    if not payload.get("ready_to_commit"):
        raise HTTPException(status_code=409, detail="El intake todavía requiere datos")
    name = (list_name or payload.get("nombre_lista_sugerido") or "Proyecto cotizado").strip()
    result = create_list_from_identified_items(
        sb, actor, name=name, source_description=payload.get("conversation"),
        items=payload["lista_items"], idempotency_key=idempotency_key,
    )
    commit_draft(sb, actor, draft_id, entity_type="list", entity_id=result["id"])
    return result


def commit_document_import(
    sb,
    actor: ApplicationActorContext,
    *,
    draft_id: str,
    list_name: Optional[str],
    idempotency_key: str,
    confirmed: bool,
) -> dict:
    if confirmed is not True:
        raise HTTPException(status_code=409, detail="Se requiere confirmación explícita para importar")
    draft = get_active_draft(sb, actor, draft_id)
    if draft.get("draft_type") != "document_list_import":
        raise HTTPException(status_code=422, detail="El draft no es una importación de documento")
    payload = draft.get("payload") or {}
    if not payload.get("ready_to_commit"):
        raise HTTPException(status_code=409, detail="El draft tiene datos pendientes por corregir")
    name = (list_name or payload.get("nombre_lista_sugerido") or draft.get("source_name") or "Lista importada").strip()
    result = create_list_from_identified_items(
        sb, actor, name=name, source_description=f"Importado desde {draft.get('source_name') or 'documento'}",
        items=payload["lista_items"], idempotency_key=idempotency_key,
    )
    commit_draft(sb, actor, draft_id, entity_type="list", entity_id=result["id"])
    return result
