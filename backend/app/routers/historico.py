"""Comparador histórico de precios."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/historico", tags=["historico"])


@router.get("/item")
async def historico_item(item_nombre: str, user_id: str):
    from app.services.precio_historico import buscar_precios_historicos
    return await buscar_precios_historicos(item_nombre, user_id)


class EvaluarRequest(BaseModel):
    precio: float
    item_nombre: str
    user_id: str


@router.post("/evaluar")
async def evaluar_precio(req: EvaluarRequest):
    from app.services.precio_historico import evaluar_precio_actual
    return await evaluar_precio_actual(req.precio, req.item_nombre, req.user_id)
