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


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    owner_email: str = Field(min_length=5, max_length=254)


class MemberCreate(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    role: str = "member"


class AdminReason(BaseModel):
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


def _require_operator(admin: dict) -> None:
    if admin.get("rol") not in {"operator", "superadmin"}:
        raise HTTPException(status_code=403, detail="Esta acción requiere rol operator o superadmin")


def _require_superadmin(admin: dict) -> None:
    if admin.get("rol") != "superadmin":
        raise HTTPException(status_code=403, detail="Esta acción requiere rol superadmin")


def _audit(sb: Any, admin: dict, action: str, *, organization_id: str | None = None,
           user_id: str | None = None, reason: str | None = None, previous: Any = None,
           new: Any = None) -> None:
    sb.table("admin_audit_log").insert({
        "actor_admin_id": admin.get("id"), "target_organization_id": organization_id,
        "target_user_id": user_id, "action": action, "entity_type": "organization" if organization_id else "user",
        "entity_id": organization_id or user_id, "reason": reason,
        "previous_value": previous, "new_value": new,
    }).execute()


def _auth_user_by_email(sb: Any, email: str):
    normalized = email.strip().lower()
    users = sb.auth.admin.list_users()
    return next((user for user in (users or []) if (user.email or "").lower() == normalized), None)


def _operational_org_id(sb: Any, organization_id: str) -> str | None:
    owners = sb.table("organization_memberships").select("user_id").eq(
        "organization_id", organization_id
    ).eq("rol", "owner").neq("estado", "removed").limit(1).execute().data or []
    if not owners:
        owners = sb.table("organization_memberships").select("user_id").eq(
            "organization_id", organization_id
        ).eq("es_principal", True).limit(1).execute().data or []
    if not owners:
        return None
    rows = sb.table("organizaciones").select("id").eq("owner_user_id", owners[0]["user_id"]).limit(1).execute().data or []
    return str(rows[0]["id"]) if rows else None


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


@router.get("/organizations/{organization_id}")
def organization_detail(organization_id: str, _: Annotated[dict, Depends(_admin)]):
    sb = get_supabase()
    organizations = sb.table("capo_organization_overview").select("*").eq("id", organization_id).limit(1).execute().data or []
    if not organizations:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    users = sb.table("capo_user_overview").select("*").eq("organization_id", organization_id).order("created_at").execute().data or []
    return {"organization": organizations[0], "members": users}


@router.post("/organizations")
def create_organization(body: OrganizationCreate, admin: Annotated[dict, Depends(_admin)]):
    _require_operator(admin)
    sb = get_supabase()
    email = body.owner_email.strip().lower()
    user = _auth_user_by_email(sb, email)
    invited = False
    if not user:
        try:
            response = sb.auth.admin.invite_user_by_email(email, {"data": {"empresa": body.name}})
            user = response.user
            invited = True
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"No se pudo invitar al propietario: {exc}")
    if not user:
        raise HTTPException(status_code=500, detail="Supabase no devolvió el usuario propietario")
    memberships = sb.table("organization_memberships").select("organization_id,estado").eq(
        "user_id", user.id
    ).eq("es_principal", True).neq("estado", "removed").limit(1).execute().data or []
    if memberships:
        org_id = str(memberships[0]["organization_id"])
        org_rows = sb.table("organizations").select("id,tipo").eq("id", org_id).limit(1).execute().data or []
        if org_rows and org_rows[0].get("tipo") != "individual":
            raise HTTPException(status_code=409, detail="El propietario ya pertenece a una organización empresarial")
        sb.table("organizations").update({"nombre": body.name, "tipo": "company", "estado": "active"}).eq("id", org_id).execute()
        sb.table("organization_memberships").update({"rol": "owner", "estado": "active", "es_principal": True}).eq("organization_id", org_id).eq("user_id", user.id).execute()
    else:
        slug = f"org-{str(user.id)[:8]}"
        created = sb.table("organizations").insert({"nombre": body.name, "slug": slug, "tipo": "company"}).execute().data or []
        org_id = str(created[0]["id"])
        sb.table("organization_memberships").insert({"organization_id": org_id, "user_id": user.id, "rol": "owner", "estado": "active", "es_principal": True}).execute()
    operational = sb.table("organizaciones").select("id").eq("owner_user_id", user.id).limit(1).execute().data or []
    if operational:
        sb.table("organizaciones").update({"nombre": body.name}).eq("id", operational[0]["id"]).execute()
    else:
        legacy = sb.table("organizaciones").insert({"nombre": body.name, "owner_user_id": user.id}).execute().data[0]
        sb.table("membresias_organizacion").insert({"organizacion_id": legacy["id"], "user_id": user.id, "rol": "admin"}).execute()
    _audit(sb, admin, "organization.created", organization_id=org_id, user_id=user.id, new={"name": body.name, "owner_email": email})
    return {"id": org_id, "owner_user_id": user.id, "invited": invited}


@router.post("/organizations/{organization_id}/members")
def add_organization_member(organization_id: str, body: MemberCreate, admin: Annotated[dict, Depends(_admin)]):
    _require_operator(admin)
    if body.role not in {"owner", "admin", "member", "billing"}:
        raise HTTPException(status_code=400, detail="Rol inválido")
    sb = get_supabase()
    if not sb.table("organizations").select("id").eq("id", organization_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    email = body.email.strip().lower()
    user = _auth_user_by_email(sb, email)
    invited = False
    if not user:
        try:
            response = sb.auth.admin.invite_user_by_email(email)
            user = response.user
            invited = True
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"No se pudo invitar al miembro: {exc}")
    if not user:
        raise HTTPException(status_code=500, detail="Supabase no devolvió el usuario")
    sb.table("organization_memberships").update({"estado": "removed", "es_principal": False}).eq("user_id", user.id).neq("organization_id", organization_id).execute()
    existing = sb.table("organization_memberships").select("id").eq("organization_id", organization_id).eq("user_id", user.id).limit(1).execute().data or []
    values = {"rol": body.role, "estado": "active", "es_principal": True}
    if existing:
        sb.table("organization_memberships").update(values).eq("id", existing[0]["id"]).execute()
    else:
        sb.table("organization_memberships").insert({"organization_id": organization_id, "user_id": user.id, **values}).execute()
    operational_id = _operational_org_id(sb, organization_id)
    if operational_id:
        sb.table("membresias_organizacion").delete().eq("user_id", user.id).execute()
        sb.table("membresias_organizacion").insert({"organizacion_id": operational_id, "user_id": user.id, "rol": "admin" if body.role in {"owner", "admin"} else "miembro"}).execute()
    _audit(sb, admin, "organization.member_added", organization_id=organization_id, user_id=user.id, new={"email": email, "role": body.role})
    return {"user_id": user.id, "invited": invited}


@router.delete("/organizations/{organization_id}/members/{user_id}")
def remove_organization_member(organization_id: str, user_id: str, body: AdminReason, admin: Annotated[dict, Depends(_admin)]):
    _require_operator(admin)
    sb = get_supabase()
    membership = sb.table("organization_memberships").select("id,rol").eq("organization_id", organization_id).eq("user_id", user_id).eq("estado", "active").limit(1).execute().data or []
    if not membership:
        raise HTTPException(status_code=404, detail="Membresía no encontrada")
    if membership[0].get("rol") == "owner":
        raise HTTPException(status_code=409, detail="Transfiere o elimina la organización antes de remover al propietario")
    sb.table("organization_memberships").update({"estado": "removed", "es_principal": False}).eq("id", membership[0]["id"]).execute()
    operational_id = _operational_org_id(sb, organization_id)
    if operational_id:
        sb.table("membresias_organizacion").delete().eq("organizacion_id", operational_id).eq("user_id", user_id).execute()
    _audit(sb, admin, "organization.member_removed", organization_id=organization_id, user_id=user_id, reason=body.reason)
    return {"success": True}


@router.delete("/organizations/{organization_id}")
def delete_organization(organization_id: str, body: AdminReason, admin: Annotated[dict, Depends(_admin)]):
    _require_superadmin(admin)
    sb = get_supabase()
    rows = sb.table("organizations").select("id,nombre,estado").eq("id", organization_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    members = sb.table("organization_memberships").select("id,user_id,rol", count="exact").eq("organization_id", organization_id).neq("estado", "removed").execute()
    active_members = members.data or []
    non_owners = [row for row in active_members if row.get("rol") != "owner"]
    if non_owners or len(active_members) > 1:
        raise HTTPException(status_code=409, detail="No se puede eliminar: aún tiene miembros. Remuévelos primero")
    owner_id = str(active_members[0]["user_id"]) if active_members else None
    _audit(sb, admin, "organization.deleted", organization_id=organization_id, reason=body.reason, previous=rows[0])
    if owner_id:
        sb.table("organization_memberships").update({"estado": "removed", "es_principal": False}).eq("id", active_members[0]["id"]).execute()
        personal = sb.table("organizations").insert({
            "nombre": "Cuenta individual", "slug": f"personal-{owner_id}-{organization_id[:8]}", "tipo": "individual", "estado": "active", "plan": "free"
        }).execute().data[0]
        sb.table("organization_memberships").insert({
            "organization_id": personal["id"], "user_id": owner_id, "rol": "owner", "estado": "active", "es_principal": True
        }).execute()
        sb.table("organizaciones").update({"nombre": "Cuenta individual"}).eq("owner_user_id", owner_id).execute()
    sb.table("organizations").delete().eq("id", organization_id).execute()
    return {"success": True}


@router.post("/users/{user_id}/password-recovery")
def trigger_password_recovery(user_id: str, admin: Annotated[dict, Depends(_admin)]):
    _require_operator(admin)
    sb = get_supabase()
    try:
        response = sb.auth.admin.get_user_by_id(user_id)
        user = response.user
        if not user or not user.email:
            raise ValueError("Usuario sin correo")
        sb.auth.reset_password_email(user.email, {"redirect_to": "https://www.baiyer.cl/reset-password"})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo enviar la recuperación: {exc}")
    _audit(sb, admin, "user.password_recovery_requested", user_id=user_id)
    return {"success": True}


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
    conversations_query = sb.table("gmail_conversations").select(
        "id,proveedor_nombre,proveedor_email,subject,estado,last_message_at,created_at,lista_proyecto_id,cotizacion_id"
    )
    conversations = conversations_query.eq("lista_proyecto_id", project_id).order("last_message_at", desc=True).execute().data or []
    if quote_ids:
        by_quote = sb.table("gmail_conversations").select(
            "id,proveedor_nombre,proveedor_email,subject,estado,last_message_at,created_at,lista_proyecto_id,cotizacion_id"
        ).in_("cotizacion_id", quote_ids).order("last_message_at", desc=True).execute().data or []
        seen = {str(row.get("id")) for row in conversations}
        conversations.extend(row for row in by_quote if str(row.get("id")) not in seen)
    conversation_ids = [row["id"] for row in conversations if row.get("id")]
    message_counts: dict[str, int] = {}
    latest_previews: dict[str, str] = {}
    if conversation_ids:
        messages = sb.table("gmail_messages").select(
            "conversation_id,body_text,received_at,created_at"
        ).in_("conversation_id", conversation_ids).order("received_at", desc=True).execute().data or []
        for message in messages:
            conversation_id = str(message.get("conversation_id"))
            message_counts[conversation_id] = message_counts.get(conversation_id, 0) + 1
            if conversation_id not in latest_previews:
                latest_previews[conversation_id] = str(message.get("body_text") or "")[:240]
    for conversation in conversations:
        conversation_id = str(conversation.get("id"))
        conversation["message_count"] = message_counts.get(conversation_id, 0)
        conversation["latest_preview"] = latest_previews.get(conversation_id, "")
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
        "email_conversations": conversations,
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
