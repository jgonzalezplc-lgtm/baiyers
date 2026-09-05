from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


class RatingRequest(BaseModel):
    proveedor_id: str
    resultado_id: Optional[str] = None
    oc_id: Optional[str] = None
    estrellas: int
    precio_cumplido: Optional[bool] = None
    plazo_cumplido: Optional[bool] = None
    comentario: Optional[str] = None


@router.get("")
async def listar_suppliers(ctx: AuthContext = Depends(get_auth_context)):
    """Piloto de AuthContext (PLAN_DATA_FOUNDATION.md): ya no confía en un
    `user_id` de query — el actor y su organización se verifican contra el
    token real de Supabase. Requiere que el frontend llame con authFetch."""
    from app.services.supabase import get_supabase

    sb = get_supabase()
    res = sb.table("proveedores").select("*").in_("user_id", ctx.user_ids_organizacion).order("score", desc=True).execute()

    proveedores = []
    for p in res.data:
        tasa = (p.get("total_respuestas") or 0) / max(p.get("total_solicitudes") or 1, 1)
        proveedores.append({
            **p,
            "tasa_respuesta": round(tasa * 100),
            "total_transacciones": (p.get("total_oc_enviadas") or 0),
        })
    return proveedores


@router.post("/{proveedor_id}/bloquear")
async def bloquear_supplier(proveedor_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase

    sb = get_supabase()
    sb.table("proveedores").update({"bloqueado": True, "categoria_score": "bloqueado_auto"}).eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).execute()
    return {"success": True}


@router.post("/{proveedor_id}/desbloquear")
async def desbloquear_supplier(proveedor_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase

    sb = get_supabase()
    sb.table("proveedores").update({"bloqueado": False}).eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).execute()
    return {"success": True}


@router.post("/rating")
async def guardar_rating(req: RatingRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    from app.services.supplier_intelligence import calcular_score

    if not (1 <= req.estrellas <= 5):
        raise HTTPException(status_code=400, detail="estrellas debe ser 1-5")

    sb = get_supabase()
    sb.table("supplier_ratings").insert({
        "user_id": ctx.actor_user_id,
        "proveedor_id": req.proveedor_id,
        "resultado_id": req.resultado_id,
        "estrellas": req.estrellas,
        "precio_cumplido": req.precio_cumplido,
        "plazo_cumplido": req.plazo_cumplido,
        "comentario": req.comentario,
    }).execute()

    nuevo_score = calcular_score(req.proveedor_id)
    return {"success": True, "nuevo_score": nuevo_score}


@router.get("/{proveedor_id}/historial")
async def historial_supplier(proveedor_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import ejecutar_maybe_single, get_supabase

    sb = get_supabase()
    ids = ctx.user_ids_organizacion

    proveedor = ejecutar_maybe_single(
        sb.table("proveedores").select("*").eq("id", proveedor_id)
        .in_("user_id", ids).maybe_single()
    )
    if not proveedor.data:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    # supplier_ratings no existe hoy en producción (tabla nunca aplicada pese
    # a estar referenciada en código) — no dejar que eso tumbe el resto de la
    # ficha, que sí tiene datos reales.
    try:
        ratings = sb.table("supplier_ratings").select("*").eq("proveedor_id", proveedor_id).order("created_at", desc=True).execute().data or []
    except Exception:
        ratings = []

    ocs = sb.table("ordenes_compra").select("numero_oc, estado, precio_total, moneda, created_at, confirmada_at").in_("user_id", ids).eq("proveedor_nombre", proveedor.data["nombre"]).order("created_at", desc=True).execute()

    from app.services.supplier_capability_intelligence import listar_capacidades
    capacidades = listar_capacidades(ctx.actor_user_id, proveedor_id)

    return {
        "proveedor": proveedor.data,
        "ratings": ratings,
        "ordenes": ocs.data,
        "capacidades": capacidades,
    }
