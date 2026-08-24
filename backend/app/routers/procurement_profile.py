"""API del perfil de procurement (Fase 1 de Supplier Capability Intelligence)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/procurement-profile", tags=["procurement-profile"])


class GenerarPerfilRequest(BaseModel):
    empresa: Optional[str] = None
    dominio: Optional[str] = None
    industria: Optional[str] = None
    pais: Optional[str] = None
    categorias_probables: list[str] = []
    descripcion_actividad: Optional[str] = None
    origen: str = "onboarding"


@router.post("/generar")
async def generar_perfil(req: GenerarPerfilRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.procurement_profile import crear_o_actualizar_perfil
    return crear_o_actualizar_perfil(
        ctx.actor_user_id, req.empresa, req.dominio, req.industria, req.pais,
        req.categorias_probables, req.descripcion_actividad, req.origen,
    )


@router.get("")
async def obtener_perfil(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.procurement_profile import listar_perfil
    perfil = listar_perfil(ctx.actor_user_id)
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return perfil


class AgregarCategoriaRequest(BaseModel):
    categoria: str


@router.post("/categorias")
async def agregar_categoria(req: AgregarCategoriaRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.procurement_profile import agregar_categoria_manual
    return agregar_categoria_manual(ctx.actor_user_id, req.categoria)


@router.post("/categorias/{categoria_id}/confirmar")
async def confirmar_categoria(
    categoria_id: str, confirmar: bool = True, ctx: AuthContext = Depends(get_auth_context),
):
    from app.services.procurement_profile import confirmar_categoria as _confirmar
    try:
        return _confirmar(ctx.actor_user_id, categoria_id, confirmar)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/categorias/{categoria_id}")
async def eliminar_categoria(categoria_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.procurement_profile import eliminar_categoria as _eliminar
    try:
        _eliminar(ctx.actor_user_id, categoria_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}
