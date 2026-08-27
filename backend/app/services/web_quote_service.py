"""Búsqueda web persistente para MCP, reutilizando el motor real de Baiyer."""
import asyncio
import json
from typing import Any, Optional

from fastapi import HTTPException

from app.services.lista_service import get_list
from app.services.mcp_context import ApplicationActorContext
from app.services.mcp_jobs import create_job, get_job, update_job

_tasks: set[asyncio.Task] = set()
_running_ids: set[str] = set()


def _quote(sb, actor: ApplicationActorContext, quote_id: str) -> dict:
    result = (
        sb.table("cotizaciones").select(
            "id, nombre_identificado, descripcion, terminos_busqueda_es, "
            "terminos_busqueda_en, categoria, user_id"
        ).eq("id", quote_id).in_("user_id", list(actor.organization_user_ids)).limit(1).execute()
    )
    row = (result.data or [None])[0]
    if not row:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return row


def _target_quotes(sb, actor: ApplicationActorContext, *, list_id: Optional[str], quote_id: Optional[str]) -> list[dict]:
    if bool(list_id) == bool(quote_id):
        raise HTTPException(status_code=422, detail="Indica exactamente list_id o cotizacion_id")
    ids = [quote_id] if quote_id else [item["cotizacion_id"] for item in get_list(sb, actor, list_id)["items"]]
    return [_quote(sb, actor, value) for value in ids]


def _serialize_result(row: dict) -> dict:
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try: metadata = json.loads(metadata)
        except (TypeError, ValueError): metadata = {}
    return {
        "resultado_id": row.get("id"), "cotizacion_id": row.get("cotizacion_id"),
        "proveedor": row.get("proveedor_nombre"), "precio": row.get("precio"),
        "precio_cotizado": row.get("precio_cotizado"),
        "moneda": row.get("moneda_cotizada") or row.get("moneda") or "CLP",
        # False = la moneda no se pudo verificar (la fuente no la dijo y el
        # dominio no la delata). El monto puede no ser comparable: hay que
        # advertirlo, no mostrarlo como si fuera un precio local.
        "moneda_confirmada": bool(metadata.get("moneda_confirmada", True)),
        "fuente": metadata.get("fuente_label") or row.get("fuente"),
        "url": row.get("url") or "", "pais": row.get("pais"),
        "relevante": row.get("relevante") is not False,
        "plazo_entrega": row.get("plazo_entrega") or metadata.get("plazo_entrega_estimado"),
        "descripcion": metadata.get("descripcion") or metadata.get("titulo"),
        "rating": metadata.get("rating"), "stock": metadata.get("stock_disponible") or metadata.get("stock"),
        "condiciones_pago": row.get("condiciones_pago"),
        "notas_respuesta": row.get("notas_respuesta"),
        "respuesta_recibida_at": row.get("respuesta_recibida_at"),
    }


def get_item_quotes(sb, actor: ApplicationActorContext, quote_id: str, *, limit: int = 50) -> dict:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit debe estar entre 1 y 100")
    quote = _quote(sb, actor, quote_id)
    result = (
        sb.table("resultados").select(
            "id, cotizacion_id, proveedor_nombre, precio, precio_cotizado, moneda, moneda_cotizada, "
            "url, pais, fuente, relevante, plazo_entrega, condiciones_pago, notas_respuesta, "
            "respuesta_recibida_at, metadata"
        ).eq("cotizacion_id", quote_id).order("precio", desc=False).limit(limit).execute()
    )
    rows = [_serialize_result(row) for row in (result.data or [])]
    return {"item": {"cotizacion_id": quote_id, "nombre": quote.get("nombre_identificado")},
            "total": len(rows), "quotes": rows}


def get_list_coverage(sb, actor: ApplicationActorContext, list_id: str) -> dict:
    current = get_list(sb, actor, list_id)
    items = []
    for item in current["items"]:
        quotes = get_item_quotes(sb, actor, item["cotizacion_id"], limit=100)["quotes"]
        relevant = [row for row in quotes if row["relevante"]]
        priced = [row for row in relevant if row.get("precio") is not None or row.get("precio_cotizado") is not None]
        items.append({
            "cotizacion_id": item["cotizacion_id"], "nombre": item.get("nombre"),
            "resultados": len(quotes), "relevantes": len(relevant), "con_precio": len(priced),
            "covered": bool(priced),
        })
    return {"list_id": list_id, "items": items, "covered": sum(1 for row in items if row["covered"]),
            "total": len(items)}


async def _run(job_id: str, actor: ApplicationActorContext) -> None:
    from app.config import settings
    from app.routers.buscar import BuscarRequest, _buscar_fuentes, _filtrar_gemini, _guardar_supabase
    from app.services.supabase import get_supabase

    sb = get_supabase()
    try:
        job = await asyncio.to_thread(get_job, sb, actor, job_id)
        if job.get("status") == "cancelled": return
        await asyncio.to_thread(update_job, sb, actor, job_id, status="running", progress=1)
        payload = job.get("input") or {}
        quotes = await asyncio.to_thread(
            _target_quotes, sb, actor, list_id=payload.get("list_id"), quote_id=payload.get("cotizacion_id")
        )
        summaries = []
        for index, quote in enumerate(quotes):
            current = await asyncio.to_thread(get_job, sb, actor, job_id)
            if current.get("status") == "cancelled": return
            request = BuscarRequest(
                cotizacion_id=quote["id"], terminos_es=quote.get("terminos_busqueda_es") or [],
                terminos_en=quote.get("terminos_busqueda_en") or [],
                nombre_item=quote.get("nombre_identificado") or quote.get("descripcion") or "",
                categoria=quote.get("categoria"), user_id=actor.actor_user_id,
                busqueda_expandida=bool(payload.get("expanded")),
            )
            rows = await _buscar_fuentes(request)
            if rows and settings.gemini_api_key:
                rows = await _filtrar_gemini(rows, request.nombre_item, settings.gemini_api_key)
            current = await asyncio.to_thread(get_job, sb, actor, job_id)
            if current.get("status") == "cancelled": return
            ordered = [row for row in rows if row.get("precio") is not None] + [row for row in rows if row.get("precio") is None]
            await asyncio.to_thread(_guardar_supabase, quote["id"], ordered[:50])
            resumen_item = {"cotizacion_id": quote["id"], "nombre": request.nombre_item,
                            "resultados": min(len(ordered), 50)}
            # Si no hubo resultados, el job debe decir POR QUÉ. Un cero mudo hace
            # indistinguible "no existe el producto" de "la API está caída".
            if not ordered and request.diagnostico_fuentes:
                resumen_item["diagnostico"] = request.diagnostico_fuentes
            summaries.append(resumen_item)
            progress = max(1, int(((index + 1) / len(quotes)) * 100))
            await asyncio.to_thread(update_job, sb, actor, job_id, status="running", progress=progress,
                                    output={"items": summaries})
        await asyncio.to_thread(update_job, sb, actor, job_id, status="completed", progress=100,
                                output={"items": summaries, "expanded": bool(payload.get("expanded"))})
    except Exception as exc:
        try:
            current = await asyncio.to_thread(get_job, sb, actor, job_id)
            if current.get("status") == "cancelled": return
            await asyncio.to_thread(update_job, sb, actor, job_id, status="failed", progress=100,
                                    error={"type": type(exc).__name__, "message": str(exc)[:500]})
        except Exception:
            pass


def _schedule(job_id: str, actor: ApplicationActorContext) -> None:
    if job_id in _running_ids:
        return
    _running_ids.add(job_id)
    task = asyncio.create_task(_run(job_id, actor))
    _tasks.add(task)
    def done(completed: asyncio.Task) -> None:
        _tasks.discard(completed)
        _running_ids.discard(job_id)
    task.add_done_callback(done)


async def start_web_quote(
    sb, actor: ApplicationActorContext, *, list_id: Optional[str], quote_id: Optional[str],
    idempotency_key: str, expanded: bool = False,
) -> dict:
    quotes = await asyncio.to_thread(_target_quotes, sb, actor, list_id=list_id, quote_id=quote_id)
    job = await asyncio.to_thread(
        create_job, sb, actor, "web_quote", {
            "list_id": list_id, "cotizacion_id": quote_id, "expanded": expanded,
            "quote_count": len(quotes),
        }, idempotency_key=idempotency_key,
    )
    if job.get("status") == "queued": _schedule(job["id"], actor)
    return {"status": job["status"], "job": {"id": job["id"], "type": "web_quote",
            "progress": job.get("progress", 0), "created_at": job.get("created_at")}}


async def recover_web_quote_jobs() -> None:
    """Reanuda jobs interrumpidos por un restart del único worker Railway."""
    from app.services.organizacion import resolver_organizacion
    from app.services.supabase import get_supabase
    sb = get_supabase()
    try:
        result = await asyncio.to_thread(
            lambda: sb.table("integration_jobs").select("*").eq("job_type", "web_quote")
            .in_("status", ["queued", "running"]).limit(25).execute()
        )
    except Exception:
        return
    for job in result.data or []:
        organization = await asyncio.to_thread(resolver_organizacion, job["actor_user_id"])
        if not organization or organization.organizacion_id != job["organization_id"]:
            continue
        actor = ApplicationActorContext(
            actor_user_id=job["actor_user_id"], organization_id=organization.organizacion_id,
            organization_name=organization.nombre,
            organization_user_ids=tuple(organization.user_ids_miembros), is_admin=organization.es_admin,
            client_id=job.get("client_id") or "recovery", scopes=frozenset({"quotes:write"}),
            request_id=job.get("request_id"),
        )
        _schedule(job["id"], actor)
