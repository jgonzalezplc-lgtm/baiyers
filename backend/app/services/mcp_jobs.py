"""Persistencia común de jobs y drafts de integraciones conversacionales."""
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.supabase import ejecutar_maybe_single

JOB_STATES = frozenset({"queued", "running", "awaiting_input", "completed", "failed", "cancelled"})
DRAFT_STATES = frozenset({"active", "committed", "discarded", "expired"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(sb, actor: ApplicationActorContext, job_type: str, input_data: dict, *, idempotency_key: str) -> dict:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail="idempotency_key es requerido")
    existing = ejecutar_maybe_single(
        sb.table("integration_jobs").select("*")
        .eq("organization_id", actor.organization_id).eq("idempotency_key", idempotency_key).maybe_single()
    )
    if existing.data:
        return existing.data
    row = {
        "id": str(uuid4()), "organization_id": actor.organization_id,
        "actor_user_id": actor.actor_user_id, "client_id": actor.client_id,
        "job_type": job_type, "status": "queued", "progress": 0,
        "input": input_data, "idempotency_key": idempotency_key,
        "request_id": actor.request_id,
    }
    result = sb.table("integration_jobs").insert(row).execute()
    return result.data[0]


def get_job(sb, actor: ApplicationActorContext, job_id: str) -> dict:
    result = ejecutar_maybe_single(
        sb.table("integration_jobs").select("*").eq("id", job_id)
        .eq("organization_id", actor.organization_id).maybe_single()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return result.data


def list_jobs(
    sb, actor: ApplicationActorContext, *, status: Optional[str] = None,
    job_type: Optional[str] = None, limit: int = 50,
) -> list[dict]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit debe estar entre 1 y 100")
    if status is not None and status not in JOB_STATES:
        raise HTTPException(status_code=422, detail="Estado de job inválido")
    query = sb.table("integration_jobs").select("*").eq("organization_id", actor.organization_id)
    if status: query = query.eq("status", status)
    if job_type: query = query.eq("job_type", job_type)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


def cancel_job(sb, actor: ApplicationActorContext, job_id: str) -> dict:
    current = get_job(sb, actor, job_id)
    if current.get("status") in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="El job ya terminó")
    return update_job(sb, actor, job_id, status="cancelled", progress=int(current.get("progress") or 0))


def update_job(sb, actor: ApplicationActorContext, job_id: str, *, status: str, progress: int, output: Optional[dict] = None, error: Optional[dict] = None) -> dict:
    if status not in JOB_STATES or not 0 <= progress <= 100:
        raise HTTPException(status_code=422, detail="Estado o progreso de job inválido")
    get_job(sb, actor, job_id)
    changes: dict[str, Any] = {"status": status, "progress": progress, "updated_at": _now()}
    if output is not None: changes["output"] = output
    if error is not None: changes["error"] = error
    if status == "running": changes["started_at"] = _now()
    if status in {"completed", "failed", "cancelled"}: changes["finished_at"] = _now()
    result = sb.table("integration_jobs").update(changes).eq("id", job_id).eq("organization_id", actor.organization_id).execute()
    return result.data[0]


def create_draft(sb, actor: ApplicationActorContext, draft_type: str, payload: dict, *, source_name: Optional[str] = None, source_mime: Optional[str] = None, source_hash: Optional[str] = None) -> dict:
    result = sb.table("integration_drafts").insert({
        "id": str(uuid4()), "organization_id": actor.organization_id,
        "actor_user_id": actor.actor_user_id, "client_id": actor.client_id,
        "draft_type": draft_type, "status": "active", "payload": payload,
        "source_name": source_name, "source_mime": source_mime,
        "source_hash": source_hash, "request_id": actor.request_id,
    }).execute()
    return result.data[0]


def get_active_draft(sb, actor: ApplicationActorContext, draft_id: str) -> dict:
    result = ejecutar_maybe_single(
        sb.table("integration_drafts").select("*").eq("id", draft_id)
        .eq("organization_id", actor.organization_id).eq("status", "active").maybe_single()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Draft activo no encontrado")
    return result.data


def commit_draft(
    sb,
    actor: ApplicationActorContext,
    draft_id: str,
    *,
    entity_type: str,
    entity_id: str,
) -> dict:
    """Marca un draft como consumido, siempre dentro de la organización activa."""
    get_active_draft(sb, actor, draft_id)
    result = (
        sb.table("integration_drafts")
        .update({
            "status": "committed",
            "committed_entity_type": entity_type,
            "committed_entity_id": entity_id,
            "updated_at": _now(),
        })
        .eq("id", draft_id)
        .eq("organization_id", actor.organization_id)
        .eq("status", "active")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=409, detail="El draft ya no está activo")
    return result.data[0]


def update_active_draft(sb, actor: ApplicationActorContext, draft_id: str, payload: dict) -> dict:
    get_active_draft(sb, actor, draft_id)
    result = (
        sb.table("integration_drafts").update({"payload": payload, "updated_at": _now()})
        .eq("id", draft_id).eq("organization_id", actor.organization_id)
        .eq("status", "active").execute()
    )
    if not result.data:
        raise HTTPException(status_code=409, detail="El draft ya no está activo")
    return result.data[0]
