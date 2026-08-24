"""API de la campanita de notificaciones (ver 022_notificaciones.sql)."""
from fastapi import APIRouter, Depends, HTTPException

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])


@router.get("")
async def listar_notificaciones(limit: int = 30, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("notificaciones").select("*").eq("user_id", ctx.actor_user_id).order(
        "created_at", desc=True
    ).limit(limit).execute()
    no_leidas = sb.table("notificaciones").select("id", count="exact").eq(
        "user_id", ctx.actor_user_id
    ).eq("leido", False).execute()
    return {"notificaciones": res.data or [], "no_leidas": no_leidas.count or 0}


@router.post("/{notificacion_id}/leer")
async def marcar_leida(notificacion_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("notificaciones").update({"leido": True}).eq("id", notificacion_id).eq(
        "user_id", ctx.actor_user_id
    ).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    return {"ok": True}


@router.post("/leer-todas")
async def marcar_todas_leidas(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("notificaciones").update({"leido": True}).eq("user_id", ctx.actor_user_id).eq(
        "leido", False
    ).execute()
    return {"ok": True}
