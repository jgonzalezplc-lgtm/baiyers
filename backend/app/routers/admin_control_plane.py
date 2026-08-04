"""API privada de solo lectura para CapoDiTutti.

La service role nunca sale del backend. Cada request primero valida el JWT de
Supabase y luego exige una fila activa en `admin_users`.
"""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.supabase import get_supabase

router = APIRouter(prefix="/api/admin-control-plane", tags=["admin-control-plane"])

PLAN_CATALOG = {
    "free": {"label": "Gratis", "price": 0, "limits": {"users": 3, "searches_month": 100, "ai_calls_month": 100}},
    "starter": {"label": "Starter interno", "price": 0, "limits": {"users": 10, "searches_month": 500, "ai_calls_month": 500}},
    "trial": {"label": "Prueba", "price": 0, "limits": {"users": 10, "searches_month": 1000, "ai_calls_month": 1000}},
    "pro": {"label": "Pro interno", "price": 0, "limits": {"users": 25, "searches_month": 5000, "ai_calls_month": 5000}},
    "business": {"label": "Business interno", "price": 0, "limits": {"users": 100, "searches_month": 25000, "ai_calls_month": 25000}},
    "enterprise": {"label": "Enterprise interno", "price": 0, "limits": {"users": None, "searches_month": None, "ai_calls_month": None}},
}


class PlanUpdate(BaseModel):
    plan: str
    reason: str = Field(min_length=3, max_length=500)


def _admin(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token requerido")
    token = authorization.split(" ", 1)[1].strip()
    sb = get_supabase()
    try:
        auth_result = sb.auth.get_user(token)
        user = auth_result.user
    except Exception:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida")
    rows = sb.table("admin_users").select("id, user_id, rol, activo").eq("user_id", user.id).eq("activo", True).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=403, detail="Acceso administrativo no autorizado")
    return rows[0]


@router.get("/dashboard")
def dashboard(_: Annotated[dict, Depends(_admin)], limit: int = Query(default=20, ge=1, le=100)):
    sb = get_supabase()
    metrics = sb.rpc("capo_dashboard_metrics").execute().data or {}
    organizations = sb.table("capo_organization_overview").select("*").order("ai_cost_30d", desc=True).limit(limit).execute().data or []
    users = sb.table("capo_user_overview").select("*").order("last_sign_in_at", desc=True, nullsfirst=False).limit(limit).execute().data or []
    usage = sb.table("ai_usage_events").select(
        "id, occurred_at, organization_id, user_id, feature, provider, effective_model, input_tokens, output_tokens, latency_ms, estimated_cost_usd, status"
    ).order("occurred_at", desc=True).limit(limit).execute().data or []
    activity = sb.table("product_events").select(
        "id, occurred_at, organization_id, user_id, event_type, entity_type, entity_id, status, metadata"
    ).order("occurred_at", desc=True).limit(limit).execute().data or []
    return {"metrics": metrics, "organizations": organizations, "users": users, "usage": usage, "activity": activity}


@router.get("/organizations")
def organizations(_: Annotated[dict, Depends(_admin)], limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return get_supabase().table("capo_organization_overview").select("*").order("nombre").range(offset, offset + limit - 1).execute().data or []


@router.get("/users")
def users(_: Annotated[dict, Depends(_admin)], limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return get_supabase().table("capo_user_overview").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute().data or []


@router.get("/ai-usage")
def ai_usage(_: Annotated[dict, Depends(_admin)], limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return get_supabase().table("ai_usage_events").select("*").order("occurred_at", desc=True).range(offset, offset + limit - 1).execute().data or []


@router.get("/activity")
def activity(_: Annotated[dict, Depends(_admin)], limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return get_supabase().table("product_events").select("*").order("occurred_at", desc=True).range(offset, offset + limit - 1).execute().data or []


def _page(query: Any, *, limit: int, offset: int) -> dict:
    result = query.range(offset, offset + limit - 1).execute()
    return {"items": result.data or [], "total": result.count, "limit": limit, "offset": offset}


def _identity_maps(sb: Any) -> tuple[dict[str, dict], dict[str, str]]:
    users = sb.table("capo_user_overview").select(
        "id, name, email, organization_id, organization"
    ).limit(5000).execute().data or []
    user_map = {str(row["id"]): row for row in users if row.get("id")}
    organizations = sb.table("capo_organization_overview").select("id,nombre").limit(5000).execute().data or []
    org_map = {str(row["id"]): str(row.get("nombre") or "Sin organización") for row in organizations if row.get("id")}
    return user_map, org_map


def _project_context(sb: Any) -> tuple[dict[str, dict], dict[str, dict]]:
    """Indexa proyectos y la relación cotización→proyecto guardada en descripcion."""
    projects = sb.table("proyectos").select(
        "id,user_id,nombre,descripcion,estado,monto_total,created_at"
    ).limit(5000).execute().data or []
    project_map: dict[str, dict] = {}
    quote_map: dict[str, dict] = {}
    for project in projects:
        project_id = str(project.get("id") or "")
        if not project_id:
            continue
        project_map[project_id] = project
        try:
            payload = json.loads(project.get("descripcion") or "{}")
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            continue
        for item in payload.get("items") or []:
            if isinstance(item, dict) and item.get("cotizacion_id"):
                quote_map[str(item["cotizacion_id"])] = {
                    "project_id": project_id,
                    "project_name": project.get("nombre") or "Proyecto sin nombre",
                }
    return project_map, quote_map


def _attach_project(row: dict, project_map: dict[str, dict], quote_map: dict[str, dict]) -> None:
    project_id = str(row.get("lista_proyecto_id") or "")
    context = None
    if project_id and project_id in project_map:
        project = project_map[project_id]
        context = {"project_id": project_id, "project_name": project.get("nombre") or "Proyecto sin nombre"}
    elif row.get("cotizacion_id"):
        context = quote_map.get(str(row["cotizacion_id"]))
    if context:
        row.update(context)


@router.get("/searches")
def searches(
    _: Annotated[dict, Depends(_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    mode: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
):
    sb = get_supabase()
    query = sb.table("search_sessions").select(
        "id,user_id,cotizacion_id,lista_proyecto_id,item_nombre,categoria_predicha,categorias_usadas,terminos,modo,session_padre_id,n_resultados,estado,created_at",
        count="exact",
    ).order("created_at", desc=True)
    if mode:
        query = query.eq("modo", mode)
    if status:
        query = query.eq("estado", status)
    if user_id:
        query = query.eq("user_id", user_id)
    page = _page(query, limit=limit, offset=offset)
    user_map, _ = _identity_maps(sb)
    project_map, quote_map = _project_context(sb)
    for row in page["items"]:
        identity = user_map.get(str(row.get("user_id")), {})
        row["user_name"] = identity.get("name") or "Usuario"
        row["user_email"] = identity.get("email")
        row["organization_id"] = identity.get("organization_id")
        row["organization"] = identity.get("organization") or "Sin organización"
        _attach_project(row, project_map, quote_map)
    return page


@router.get("/emails")
def emails(
    _: Annotated[dict, Depends(_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
):
    sb = get_supabase()
    query = sb.table("gmail_conversations").select(
        "id,user_id,proveedor_nombre,proveedor_email,lista_proyecto_id,cotizacion_id,subject,estado,last_message_at,created_at",
        count="exact",
    ).order("created_at", desc=True)
    if status:
        query = query.eq("estado", status)
    if user_id:
        query = query.eq("user_id", user_id)
    page = _page(query, limit=limit, offset=offset)
    ids = [row["id"] for row in page["items"] if row.get("id")]
    counts: dict[str, dict[str, int]] = {}
    if ids:
        messages = sb.table("gmail_messages").select(
            "conversation_id,direction,procesado"
        ).in_("conversation_id", ids).execute().data or []
        for message in messages:
            key = str(message.get("conversation_id"))
            bucket = counts.setdefault(key, {"total": 0, "inbound": 0, "outbound": 0, "pending": 0})
            bucket["total"] += 1
            direction = message.get("direction")
            if direction in {"inbound", "outbound"}:
                bucket[direction] += 1
            if direction == "inbound" and not message.get("procesado"):
                bucket["pending"] += 1
    user_map, _ = _identity_maps(sb)
    project_map, quote_map = _project_context(sb)
    for row in page["items"]:
        identity = user_map.get(str(row.get("user_id")), {})
        row["user_name"] = identity.get("name") or "Usuario"
        row["user_email"] = identity.get("email")
        row["organization_id"] = identity.get("organization_id")
        row["organization"] = identity.get("organization") or "Sin organización"
        row["messages"] = counts.get(str(row.get("id")), {"total": 0, "inbound": 0, "outbound": 0, "pending": 0})
        _attach_project(row, project_map, quote_map)
    return page


@router.get("/projects/{project_id}")
def project_detail(project_id: str, _: Annotated[dict, Depends(_admin)]):
    sb = get_supabase()
    projects, _ = _project_context(sb)
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    try:
        payload = json.loads(project.get("descripcion") or "{}")
    except (TypeError, ValueError):
        payload = {}
    items = payload.get("items") if isinstance(payload, dict) else []
    items = items if isinstance(items, list) else []
    quote_ids = [str(item.get("cotizacion_id")) for item in items if isinstance(item, dict) and item.get("cotizacion_id")]
    quotes = []
    if quote_ids:
        quotes = sb.table("cotizaciones").select(
            "id,nombre_identificado,categoria,estado,created_at"
        ).in_("id", quote_ids).execute().data or []
    quote_by_id = {str(row.get("id")): row for row in quotes}
    detailed_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = quote_by_id.get(str(item.get("cotizacion_id")), {})
        detailed_items.append({
            "cotizacion_id": item.get("cotizacion_id"),
            "name": item.get("nombre") or quote.get("nombre_identificado") or "Ítem sin nombre",
            "quantity": item.get("cantidad") or 1,
            "compared": bool(item.get("comparado")),
            "category": quote.get("categoria"),
            "status": quote.get("estado"),
        })
    user_map, _ = _identity_maps(sb)
    identity = user_map.get(str(project.get("user_id")), {})
    return {
        "id": project_id,
        "name": project.get("nombre") or "Proyecto sin nombre",
        "status": project.get("estado"),
        "total": project.get("monto_total"),
        "created_at": project.get("created_at"),
        "organization_id": identity.get("organization_id"),
        "organization": identity.get("organization") or "Sin organización",
        "actor": identity.get("name") or "Usuario",
        "actor_email": identity.get("email"),
        "summary": str(payload.get("resumen") or "") if isinstance(payload, dict) else str(project.get("descripcion") or ""),
        "items": detailed_items,
    }


@router.get("/emails/{conversation_id}")
def email_detail(conversation_id: str, _: Annotated[dict, Depends(_admin)]):
    sb = get_supabase()
    rows = sb.table("gmail_conversations").select(
        "id,user_id,proveedor_nombre,proveedor_email,lista_proyecto_id,cotizacion_id,subject,estado,last_message_at,created_at"
    ).eq("id", conversation_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conversation = rows[0]
    messages = sb.table("gmail_messages").select(
        "id,direction,from_email,to_email,subject,body_text,received_at,procesado,created_at"
    ).eq("conversation_id", conversation_id).order("received_at").execute().data or []
    message_ids = [row["id"] for row in messages if row.get("id")]
    attachments = []
    if message_ids:
        attachments = sb.table("gmail_attachments").select(
            "id,message_id,filename,mime_type,created_at"
        ).in_("message_id", message_ids).execute().data or []
    attachments_by_message: dict[str, list[dict]] = {}
    for attachment in attachments:
        attachments_by_message.setdefault(str(attachment.get("message_id")), []).append(attachment)
    for message in messages:
        body = str(message.pop("body_text", "") or "")
        message["body_preview"] = body[:4000]
        message["attachments"] = attachments_by_message.get(str(message.get("id")), [])
    user_map, _ = _identity_maps(sb)
    identity = user_map.get(str(conversation.get("user_id")), {})
    projects, quotes = _project_context(sb)
    _attach_project(conversation, projects, quotes)
    return {
        **conversation,
        "user_name": identity.get("name") or "Usuario",
        "user_email": identity.get("email"),
        "organization_id": identity.get("organization_id"),
        "organization": identity.get("organization") or "Sin organización",
        "messages": messages,
    }


DATA_RESOURCES = {
    "organizations": ("capo_organization_overview", "*", "created_at"),
    "users": ("capo_user_overview", "*", "created_at"),
    "searches": ("search_sessions", "id,user_id,cotizacion_id,lista_proyecto_id,item_nombre,categoria_predicha,modo,n_resultados,estado,created_at", "created_at"),
    "projects": ("proyectos", "id,user_id,nombre,estado,created_at", "created_at"),
    "quotes": ("cotizaciones", "id,user_id,nombre_identificado,categoria,estado,created_at", "created_at"),
    "suppliers": ("proveedores", "id,user_id,nombre,categoria_score,pais,score,bloqueado,created_at", "created_at"),
    "email_conversations": ("gmail_conversations", "id,user_id,lista_proyecto_id,cotizacion_id,proveedor_nombre,subject,estado,last_message_at,created_at", "created_at"),
    "product_events": ("product_events", "id,organization_id,user_id,event_type,entity_type,entity_id,status,occurred_at", "occurred_at"),
    "ai_usage": ("ai_usage_events", "id,organization_id,user_id,feature,provider,effective_model,input_tokens,output_tokens,latency_ms,estimated_cost_usd,status,occurred_at", "occurred_at"),
}


@router.get("/database")
def database(_: Annotated[dict, Depends(_admin)]):
    sb = get_supabase()
    resources = []
    for key, (table, _fields, _order) in DATA_RESOURCES.items():
        try:
            result = sb.table(table).select("*", count="exact").limit(1).execute()
            resources.append({"key": key, "table": table, "count": result.count or 0, "available": True})
        except Exception as exc:
            resources.append({"key": key, "table": table, "count": 0, "available": False, "error": type(exc).__name__})
    return {"resources": resources}


@router.get("/database/{resource}")
def database_resource(
    resource: str,
    _: Annotated[dict, Depends(_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    config = DATA_RESOURCES.get(resource)
    if not config:
        raise HTTPException(status_code=404, detail="Recurso administrativo no permitido")
    table, fields, order = config
    sb = get_supabase()
    query = sb.table(table).select(fields, count="exact").order(order, desc=True)
    page = _page(query, limit=limit, offset=offset)
    user_map, org_map = _identity_maps(sb)
    project_map, quote_map = _project_context(sb)
    enriched = []
    for row in page["items"]:
        # En vistas de usuarios, `id` es el UID. En el resto se usa user_id.
        actor_id = str(row.get("user_id") or (row.get("id") if resource == "users" else ""))
        identity = user_map.get(actor_id, {})
        organization_id = str(
            row.get("organization_id")
            or identity.get("organization_id")
            or (row.get("id") if resource == "organizations" else "")
        )
        organization_name = (
            str(row.get("organization") or "")
            or (str(row.get("nombre") or "") if resource == "organizations" else "")
            or org_map.get(organization_id)
            or "Sin organización"
        )
        actor_name = str(row.get("name") or identity.get("name") or ("Sistema" if not actor_id else "Usuario"))
        actor_email = row.get("email") or identity.get("email")
        if resource in {"quotes", "searches", "email_conversations"}:
            _attach_project(row, project_map, quote_map)
        project_fields = {
            "project_id": row.get("project_id"),
            "project_name": row.get("project_name"),
        } if resource in {"quotes", "searches", "email_conversations"} else {}
        enriched.append({
            "organization": organization_name,
            "actor": actor_name,
            "actor_email": actor_email,
            **project_fields,
            **row,
        })
    page["items"] = enriched
    return {"resource": resource, **page}


@router.get("/plans")
def plans(_: Annotated[dict, Depends(_admin)]):
    organizations = get_supabase().table("capo_organization_overview").select("*").order("nombre").execute().data or []
    return {"catalog": PLAN_CATALOG, "organizations": organizations, "billing_enabled": False}


@router.patch("/plans/organizations/{organization_id}")
def update_organization_plan(
    organization_id: str,
    body: PlanUpdate,
    admin: Annotated[dict, Depends(_admin)],
):
    if body.plan not in PLAN_CATALOG:
        raise HTTPException(status_code=400, detail="Plan interno inválido")
    sb = get_supabase()
    previous_rows = sb.table("organizations").select("id,nombre,plan").eq("id", organization_id).limit(1).execute().data or []
    if not previous_rows:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    previous = previous_rows[0]
    updated = sb.table("organizations").update({"plan": body.plan}).eq("id", organization_id).execute().data or []
    sb.table("admin_audit_log").insert({
        "actor_admin_id": admin.get("id"),
        "target_organization_id": organization_id,
        "action": "organization.plan_changed",
        "entity_type": "organization",
        "entity_id": organization_id,
        "reason": body.reason,
        "previous_value": {"plan": previous.get("plan")},
        "new_value": {"plan": body.plan, "billing_enabled": False},
    }).execute()
    return {"organization": (updated[0] if updated else {**previous, "plan": body.plan}), "catalog_entry": PLAN_CATALOG[body.plan]}
