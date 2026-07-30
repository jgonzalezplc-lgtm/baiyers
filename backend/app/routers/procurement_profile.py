"""API del perfil de procurement (Fase 1 de Supplier Capability Intelligence)."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/procurement-profile", tags=["procurement-profile"])


class GenerarPerfilRequest(BaseModel):
    user_id: str
    empresa: Optional[str] = None
    dominio: Optional[str] = None
    industria: Optional[str] = None
    pais: Optional[str] = None
    categorias_probables: list[str] = []
    descripcion_actividad: Optional[str] = None
    origen: str = "onboarding"


@router.post("/generar")
async def generar_perfil(req: GenerarPerfilRequest):
    from app.services.procurement_profile import crear_o_actualizar_perfil
    return crear_o_actualizar_perfil(
        req.user_id, req.empresa, req.dominio, req.industria, req.pais,
        req.categorias_probables, req.descripcion_actividad, req.origen,
    )


@router.get("")
async def obtener_perfil(user_id: str):
    from app.services.procurement_profile import listar_perfil
    perfil = listar_perfil(user_id)
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return perfil


class AgregarCategoriaRequest(BaseModel):
    user_id: str
    categoria: str


@router.post("/categorias")
async def agregar_categoria(req: AgregarCategoriaRequest):
    from app.services.procurement_profile import agregar_categoria_manual
    return agregar_categoria_manual(req.user_id, req.categoria)


@router.post("/categorias/{categoria_id}/confirmar")
async def confirmar_categoria(categoria_id: str, user_id: str, confirmar: bool = True):
    from app.services.procurement_profile import confirmar_categoria as _confirmar
    try:
        return _confirmar(user_id, categoria_id, confirmar)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/categorias/{categoria_id}")
async def eliminar_categoria(categoria_id: str, user_id: str):
    from app.services.procurement_profile import eliminar_categoria as _eliminar
    try:
        _eliminar(user_id, categoria_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}
