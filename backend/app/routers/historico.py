"""Comparador histórico de precios."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/historico", tags=["historico"])


@router.get("/item")
async def historico_item(item_nombre: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.precio_historico import buscar_precios_historicos
    return await buscar_precios_historicos(item_nombre, ctx.actor_user_id)


class EvaluarRequest(BaseModel):
    precio: float
    item_nombre: str


@router.post("/evaluar")
async def evaluar_precio(req: EvaluarRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.precio_historico import evaluar_precio_actual
    return await evaluar_precio_actual(req.precio, req.item_nombre, ctx.actor_user_id)
