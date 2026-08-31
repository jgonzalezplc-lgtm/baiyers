"""Comparación, selección y aprobaciones seguras para clientes MCP."""
from typing import Any, Optional

from fastapi import HTTPException

from app.services.lista_service import get_list
from app.services.mcp_context import ApplicationActorContext
from app.services.supabase import ejecutar_maybe_single
from app.services.web_quote_service import get_item_quotes


def _confirmed(value: bool, action: str) -> None:
    if value is not True:
        raise HTTPException(status_code=409, detail=f"Se requiere confirmación explícita para {action}")


def compare_item(sb, actor: ApplicationActorContext, list_id: str, quote_id: str) -> dict:
    current = get_list(sb, actor, list_id)
    item = next((row for row in current["items"] if row.get("cotizacion_id") == quote_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado en la lista")
    offers = get_item_quotes(sb, actor, quote_id, limit=100)["quotes"]
    quantity = float(item.get("cantidad") or 1)
    for offer in offers:
        unit = offer.get("precio_cotizado") if offer.get("precio_cotizado") is not None else offer.get("precio")
        offer["precio_unitario"] = unit
        offer["total_linea"] = unit * quantity if unit is not None else None
        offer["selected"] = offer.get("resultado_id") == (current.get("definitivos", {}).get(quote_id) or {}).get("resultado_id")
        missing = []
        if unit is None: missing.append("precio")
        if not offer.get("plazo_entrega"): missing.append("plazo_entrega")
        if not offer.get("stock"): missing.append("disponibilidad")
        offer["missing_fields"] = missing
    offers.sort(key=lambda row: (row["precio_unitario"] is None, row["precio_unitario"] or 0))
    return {"list_id": list_id, "item": {**item, "cantidad": quantity}, "quotes": offers,
            "definitive": current.get("definitivos", {}).get(quote_id)}


def compare_list(sb, actor: ApplicationActorContext, list_id: str) -> dict:
    current = get_list(sb, actor, list_id)
    items = [compare_item(sb, actor, list_id, row["cotizacion_id"]) for row in current["items"]]
    return {"list_id": list_id, "nombre": current.get("nombre"), "monto_total": current.get("monto_total", 0),
            "items": items, "selected": len(current.get("definitivos", {})), "total": len(items)}


def explain_quote_recommendation(sb, actor: ApplicationActorContext, list_id: str, quote_id: str) -> dict:
    comparison = compare_item(sb, actor, list_id, quote_id)
    eligible = [row for row in comparison["quotes"] if row["relevante"] and row["precio_unitario"] is not None]
    if not eligible:
        return {"recommended": None, "reason": "No existen ofertas relevantes con precio.", "warnings": []}
    ranked = sorted(eligible, key=lambda row: (
        len(row["missing_fields"]), row["precio_unitario"], -(float(row.get("rating") or 0))
    ))
    best = ranked[0]
    warnings = []
    if best["missing_fields"]: warnings.append("La oferta tiene campos operativos pendientes")
    return {"recommended": best, "reason": "Menor precio entre ofertas relevantes, priorizando datos completos y rating.",
            "warnings": warnings, "alternatives_considered": len(eligible)}


def _registrar_precio_manual(sb, result_id: str, precio: float, actor: ApplicationActorContext) -> None:
    """Persiste un precio ingresado a mano dejando rastro de que NO lo cotizó el proveedor.

    Sin esto el precio aparecería después indistinguible de uno extraído del correo, y
    quien revise la OC no tendría cómo saber que lo tipeó una persona.
    """
    actual = ejecutar_maybe_single(
        sb.table("resultados").select("notas_respuesta").eq("id", result_id).maybe_single()
    )
    previa = (actual.data or {}).get("notas_respuesta") or ""
    nota = f"precio ingresado manualmente por {actor.actor_user_id}: {precio:.0f} CLP"
    sb.table("resultados").update({
        "precio_cotizado": precio,
        "moneda_cotizada": "CLP",
        "notas_respuesta": (previa + f"\n{nota}").strip(),
    }).eq("id", result_id).execute()


async def select_final_quote(
    sb, actor: ApplicationActorContext, *, list_id: str, quote_id: str,
    result_id: str, price_clp: Optional[float], confirmed: bool,
) -> dict:
    _confirmed(confirmed, "seleccionar la oferta definitiva")
    comparison = compare_item(sb, actor, list_id, quote_id)
    offer = next((row for row in comparison["quotes"] if row.get("resultado_id") == result_id), None)
    if not offer:
        raise HTTPException(status_code=404, detail="Oferta no encontrada para este ítem")
    unit = offer.get("precio_cotizado") if offer.get("precio_cotizado") is not None else offer.get("precio")
    currency = offer.get("moneda") or "CLP"
    # `price_clp` cumple dos roles distintos y ambos son legítimos:
    #  1. conversión: la oferta está en moneda extranjera y hace falta su equivalente CLP;
    #  2. override manual: la oferta no tiene precio persistido (ej: el proveedor respondió
    #     por correo pero la extracción no alcanzó a aplicarse) y el actor lo ingresa a mano.
    # Antes el 409 de "oferta sin precio" se evaluaba ANTES de mirar price_clp, así que el
    # caso 2 era inalcanzable y el parámetro quedaba muerto en la ruta CLP.
    override_manual = unit is None
    if override_manual:
        if price_clp is None or price_clp <= 0:
            raise HTTPException(
                status_code=409,
                detail="No se puede seleccionar una oferta sin precio: enviá price_clp para fijarlo manualmente",
            )
        unit, currency = float(price_clp), "CLP"
    elif currency != "CLP" and (price_clp is None or price_clp <= 0):
        raise HTTPException(status_code=422, detail="price_clp es requerido para ofertas en moneda extranjera")
    from app.routers.listas import DefinitivoRequest, elegir_definitivo
    if override_manual:
        _registrar_precio_manual(sb, result_id, unit, actor)
    request = DefinitivoRequest(
        cotizacion_id=quote_id, resultado_id=result_id, proveedor=offer.get("proveedor"),
        precio=unit, moneda=currency, url=offer.get("url"), fuente=offer.get("fuente"),
        precio_clp=unit if currency == "CLP" else price_clp,
    )
    return await elegir_definitivo(list_id, request, actor.to_auth_context())


async def clear_final_quote(
    actor: ApplicationActorContext, *, list_id: str, quote_id: str, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "quitar la oferta definitiva")
    from app.routers.listas import DefinitivoRequest, elegir_definitivo
    return await elegir_definitivo(
        list_id, DefinitivoRequest(cotizacion_id=quote_id, quitar=True), actor.to_auth_context()
    )


def get_approval_status(sb, actor: ApplicationActorContext, list_id: str) -> dict:
    current = get_list(sb, actor, list_id)
    requests = (
        sb.table("approval_requests").select(
            "id,referencia,estado,aprobador_email,expira_at,decidido_at,comentario,"
            "workflow_instance_id,workflow_nodo_id,responsable_id,created_at"
        ).eq("referencia", f"lista:{list_id}").in_("user_id", list(actor.organization_user_ids))
        .order("created_at", desc=True).execute().data or []
    )
    raw = (current.get("aprobacion") or {}).get("estado")
    canonical = {None: "not_requested", "pendiente": "pending", "aprobado": "approved",
                 "aprobado_con_observaciones": "approved_with_observations",
                 "rechazado": "rejected", "expirado": "expired"}.get(raw, raw)
    return {"list_id": list_id, "canonical_status": canonical, "raw_status": raw,
            "approval": current.get("aprobacion"), "requests": requests}


def get_approval_route(sb, actor: ApplicationActorContext, list_id: str) -> dict:
    current = get_list(sb, actor, list_id)
    from app.services.workflow_execution import previsualizar_autorizadores
    route = previsualizar_autorizadores(actor.actor_user_id, float(current.get("monto_total") or 0))
    return {"list_id": list_id, "monto_total": current.get("monto_total") or 0,
            "mode": "workflow" if route else "legacy", "route": route}


async def request_approval(
    actor: ApplicationActorContext, *, list_id: str, approver_email: Optional[str],
    justifications: dict[str, str], requester_name: str, company: str, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "solicitar aprobación")
    from app.routers.listas import SolicitarAprobacionRequest, solicitar_aprobacion
    request = SolicitarAprobacionRequest(
        aprobador_email=approver_email, justificaciones=justifications,
        nombre_solicitante=requester_name, empresa=company,
    )
    return await solicitar_aprobacion(list_id, request, actor.to_auth_context())


def _authorized_request(sb, actor: ApplicationActorContext, request_id: str) -> dict:
    request = ejecutar_maybe_single(
        sb.table("approval_requests").select("*").eq("id", request_id)
        .in_("user_id", list(actor.organization_user_ids)).maybe_single()
    ).data
    if not request:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if request.get("estado") != "pendiente":
        raise HTTPException(status_code=409, detail=f"Solicitud ya está en estado '{request.get('estado')}'")
    responsable_id = request.get("responsable_id")
    if not responsable_id:
        raise HTTPException(status_code=403, detail="La solicitud legacy sólo puede decidirse mediante su magic link")
    responsible = ejecutar_maybe_single(
        sb.table("responsables").select("id,usuario_baiyer_id,activo")
        .eq("id", responsable_id).eq("usuario_baiyer_id", actor.actor_user_id)
        .eq("activo", True).maybe_single()
    ).data
    if not responsible:
        raise HTTPException(status_code=403, detail="El actor no es el responsable asignado a esta solicitud")
    return request


async def decide_request(
    sb, actor: ApplicationActorContext, *, request_id: str, decision: str,
    comment: Optional[str], item_decisions: dict[str, dict], confirmed: bool,
) -> dict:
    _confirmed(confirmed, "decidir la solicitud")
    request = _authorized_request(sb, actor, request_id)
    from app.routers.aprobaciones import DecisionRequest, decidir
    return await decidir(request["token"], DecisionRequest(
        decision=decision, comentario=comment, item_decisions=item_decisions,
    ), actor.to_auth_context())


def list_workflow_events(sb, actor: ApplicationActorContext, list_id: str) -> dict:
    get_list(sb, actor, list_id)
    instances = (
        sb.table("workflow_instances").select("id").eq("lista_proyecto_id", list_id)
        .in_("user_id", list(actor.organization_user_ids)).execute().data or []
    )
    ids = [row["id"] for row in instances]
    if not ids: return {"list_id": list_id, "events": []}
    events = sb.table("workflow_events").select("*").in_("instance_id", ids).order("created_at").execute().data or []
    return {"list_id": list_id, "events": events}
