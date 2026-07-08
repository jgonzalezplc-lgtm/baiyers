from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


class RatingRequest(BaseModel):
    proveedor_id: str
    user_id: str
    resultado_id: Optional[str] = None
    oc_id: Optional[str] = None
    estrellas: int
    precio_cumplido: Optional[bool] = None
    plazo_cumplido: Optional[bool] = None
    comentario: Optional[str] = None


@router.get("")
async def listar_suppliers(user_id: str):
    from app.services.supabase import get_supabase

    sb = get_supabase()
    res = sb.table("proveedores").select("*").eq("user_id", user_id).order("score", desc=True).execute()

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
async def bloquear_supplier(proveedor_id: str, user_id: str):
    from app.services.supabase import get_supabase

    sb = get_supabase()
    sb.table("proveedores").update({"bloqueado": True, "categoria_score": "bloqueado_auto"}).eq("id", proveedor_id).eq("user_id", user_id).execute()
    return {"success": True}


@router.post("/{proveedor_id}/desbloquear")
async def desbloquear_supplier(proveedor_id: str, user_id: str):
    from app.services.supabase import get_supabase

    sb = get_supabase()
    sb.table("proveedores").update({"bloqueado": False}).eq("id", proveedor_id).eq("user_id", user_id).execute()
    return {"success": True}


@router.post("/rating")
async def guardar_rating(req: RatingRequest):
    from app.services.supabase import get_supabase
    from app.services.supplier_intelligence import calcular_score

    if not (1 <= req.estrellas <= 5):
        raise HTTPException(status_code=400, detail="estrellas debe ser 1-5")

    sb = get_supabase()
    sb.table("supplier_ratings").insert({
        "user_id": req.user_id,
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
async def historial_supplier(proveedor_id: str, user_id: str):
    from app.services.supabase import get_supabase

    sb = get_supabase()

    proveedor = sb.table("proveedores").select("*").eq("id", proveedor_id).eq("user_id", user_id).single().execute()
    if not proveedor.data:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    ratings = sb.table("supplier_ratings").select("*").eq("proveedor_id", proveedor_id).order("created_at", desc=True).execute()

    ocs = sb.table("ordenes_compra").select("numero_oc, estado, precio_total, moneda, created_at, confirmada_at").eq("user_id", user_id).eq("proveedor_nombre", proveedor.data["nombre"]).order("created_at", desc=True).execute()

    return {
        "proveedor": proveedor.data,
        "ratings": ratings.data,
        "ordenes": ocs.data,
    }
