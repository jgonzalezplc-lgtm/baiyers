"""API privada de solo lectura para CapoDiTutti.

La service role nunca sale del backend. Cada request primero valida el JWT de
Supabase y luego exige una fila activa en `admin_users`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.services.supabase import get_supabase

router = APIRouter(prefix="/api/admin-control-plane", tags=["admin-control-plane"])


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
