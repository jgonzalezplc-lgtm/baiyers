"""Flujo compacto de cotización web para clientes MCP conversacionales."""
import asyncio
from typing import Any, Optional

from fastapi import HTTPException

from app.services.comparison_approval_service import compare_list
from app.services.mcp_context import ApplicationActorContext
from app.services.mcp_jobs import get_job
from app.services.web_quote_service import start_web_quote


def _price(offer: dict[str, Any]) -> Optional[float]:
    value = offer.get("precio_unitario")
    if value is None:
        value = offer.get("precio_cotizado")
    if value is None:
        value = offer.get("precio")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def build_web_quote_summary(comparison: dict[str, Any], *, offers_per_item: int = 3) -> dict[str, Any]:
    """Resumen pequeño, utilizable directamente por un asistente conversacional.

    El total es una estimación conservadora: suma la alternativa web relevante
    más barata en CLP por ítem. Las monedas extranjeras se muestran, pero no se
    mezclan silenciosamente en el total.
    """
    if not 1 <= offers_per_item <= 10:
        raise HTTPException(status_code=422, detail="offers_per_item debe estar entre 1 y 10")
    items = []
    total_clp = 0.0
    covered = 0
    for row in comparison.get("items", []):
        item = row.get("item") or {}
        quantity = float(item.get("cantidad") or 1)
        valid = [offer for offer in row.get("quotes", []) if offer.get("relevante") and _price(offer) is not None]
        valid.sort(key=lambda offer: (_price(offer) is None, _price(offer) or 0))
        offers = []
        clp_offers = []
        for offer in valid:
            price = _price(offer)
            currency = offer.get("moneda") or "CLP"
            serialized = {
                "proveedor": offer.get("proveedor"), "precio_unitario": price,
                "moneda": currency, "total_linea": price * quantity if price is not None else None,
                "fuente": offer.get("fuente"), "url": offer.get("url"),
                "plazo_entrega": offer.get("plazo_entrega"), "stock": offer.get("stock"),
            }
            offers.append(serialized)
            if currency == "CLP":
                clp_offers.append(serialized)
        best_clp = clp_offers[0] if clp_offers else None
        if best_clp:
            covered += 1
            total_clp += float(best_clp["total_linea"])
        items.append({
            "cotizacion_id": item.get("cotizacion_id"), "nombre": item.get("nombre"),
            "cantidad": quantity, "unidad": item.get("unidad") or "un",
            "ofertas": offers[:offers_per_item], "mejor_oferta_clp": best_clp,
            "estado": "cotizado" if best_clp else ("solo_moneda_extranjera" if offers else "sin_ofertas"),
        })
    return {
        "list_id": comparison.get("list_id"), "proyecto": comparison.get("nombre"),
        "items": items,
        "resumen": {
            "items_totales": len(items), "items_con_precio_clp": covered,
            "items_sin_precio_clp": len(items) - covered,
            "total_estimado_clp": round(total_clp),
            "metodo_total": "Suma de la alternativa web relevante más barata en CLP por ítem.",
        },
    }


async def quote_existing_list(
    sb, actor: ApplicationActorContext, *, list_id: str, idempotency_key: str,
    wait_seconds: int = 12, offers_per_item: int = 3,
) -> dict[str, Any]:
    """Inicia una búsqueda y espera brevemente para evitar un turno de polling."""
    if not 0 <= wait_seconds <= 20:
        raise HTTPException(status_code=422, detail="wait_seconds debe estar entre 0 y 20")
    started = await start_web_quote(
        sb, actor, list_id=list_id, quote_id=None, idempotency_key=idempotency_key,
    )
    job_id = started["job"]["id"]
    job = await asyncio.to_thread(get_job, sb, actor, job_id)
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while job.get("status") in {"queued", "running"} and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.5)
        job = await asyncio.to_thread(get_job, sb, actor, job_id)
    response: dict[str, Any] = {
        "list_id": list_id,
        "job": {"id": job_id, "status": job.get("status"), "progress": job.get("progress", 0)},
    }
    if job.get("status") == "completed":
        comparison = await asyncio.to_thread(compare_list, sb, actor, list_id)
        response["cotizacion_web"] = build_web_quote_summary(comparison, offers_per_item=offers_per_item)
        from app.services.rfq_mcp_service import suggest_suppliers
        response["siguiente_paso"] = {
            "tipo": "recomendar_rfq",
            "mensaje": "Ya hay precios web. Ahora puedes recomendar proveedores confiables de Baiyer para pedir cotizaciones por correo, sin enviar nada todavía.",
            "proveedores_recomendados": await suggest_suppliers(actor, list_id),
        }
    elif job.get("status") in {"failed", "cancelled"}:
        response["error"] = job.get("error") or {"message": "La búsqueda no terminó."}
    else:
        response["siguiente_paso"] = {
            "tipo": "esperar_resultados",
            "mensaje": "La búsqueda sigue en curso; vuelve a llamar quote_project con el mismo list_id para obtener el resumen cuando termine.",
        }
    return response


async def quote_new_project(
    sb, actor: ApplicationActorContext, *, description: str, idempotency_key: str,
    name: Optional[str] = None, industry: Optional[str] = None,
    wait_seconds: int = 12, offers_per_item: int = 3,
) -> dict[str, Any]:
    """Identifica y cotiza un proyecto nuevo sin convertir el chat en un wizard.

    Crear una lista de cotización y buscar precios no contacta a terceros ni
    selecciona una compra. Por eso se ejecutan de inmediato; las acciones
    externas posteriores (RFQ, OC, aprobación) siguen requiriendo confirmación.
    """
    if not description.strip():
        raise HTTPException(status_code=422, detail="La descripción del proyecto es requerida")
    actor.require_scope("lists:write")
    from app.services.lista_service import create_list_from_identified_items
    from app.services.mcp_jobs import commit_draft
    from app.services.project_intake import start_project_intake

    intake = await start_project_intake(sb, actor, description=description, industry=industry)
    compact_intake = {
        "draft_id": intake["draft_id"], "ready": bool(intake.get("ready_to_commit")),
        "items": intake.get("lista_items") or [], "preguntas": intake.get("preguntas") or [],
    }
    if not intake.get("ready_to_commit"):
        return {
            "estado": "requiere_datos", "intake": compact_intake,
            "siguiente_paso": {
                "tipo": "responder_preguntas",
                "mensaje": "Faltan datos para cotizar con precisión. Pide únicamente las preguntas indicadas y continúa el intake con las respuestas.",
            },
        }

    list_name = (name or intake.get("nombre_lista_sugerido") or "Proyecto cotizado").strip()
    created = await asyncio.to_thread(
        create_list_from_identified_items, sb, actor, name=list_name,
        source_description=description, items=intake["lista_items"],
        idempotency_key=f"{idempotency_key}:list",
    )
    # El draft es sólo trazabilidad del intake. Si el cliente reintenta con la
    # misma clave, la creación de lista es idempotente y este marcado es seguro.
    await asyncio.to_thread(
        commit_draft, sb, actor, intake["draft_id"], entity_type="list", entity_id=created["id"],
    )
    quoted = await quote_existing_list(
        sb, actor, list_id=created["id"], idempotency_key=f"{idempotency_key}:search",
        wait_seconds=wait_seconds, offers_per_item=offers_per_item,
    )
    return {"estado": "cotizando" if quoted["job"]["status"] != "completed" else "cotizado",
            "intake": compact_intake, "lista": {"id": created["id"], "nombre": list_name}, **quoted}
