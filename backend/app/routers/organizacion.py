"""API de organización — Fases A + C.

Lectura del contexto propio + invitación de nuevos miembros (solo admin).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/organizacion", tags=["organizacion"])


@router.get("/mia")
async def mi_organizacion(ctx_auth: AuthContext = Depends(get_auth_context)):
    from app.services.organizacion import obtener_organizacion, obtener_perfil_organizacion
    ctx = obtener_organizacion(ctx_auth.actor_user_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Sin organización")
    return {**ctx, **obtener_perfil_organizacion(ctx_auth.organization_id)}


class PerfilOrganizacionRequest(BaseModel):
    nombre: str
    industria: Optional[str] = None
    rut: Optional[str] = None
    pais: Optional[str] = None
    sitio_web: Optional[str] = None


@router.patch("/mia")
async def actualizar_mi_organizacion(
    req: PerfilOrganizacionRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Actualiza la fuente canónica que usan invitaciones y documentos.

    Antes Configuración solo modificaba `auth.user_metadata`, por lo que la
    pantalla podía decir Claria mientras las invitaciones salían por Copec.
    """
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede editar la organización")
    nombre = req.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre de la organización es obligatorio")

    from app.services.supabase import get_supabase
    valores = {
        "nombre": nombre,
        "industria": req.industria.strip() if req.industria else None,
        "rut": req.rut.strip() if req.rut else None,
        "pais": req.pais.strip() if req.pais else None,
        "sitio_web": req.sitio_web.strip() if req.sitio_web else None,
    }
    try:
        fila = get_supabase().table("organizaciones").update(valores).eq(
            "id", ctx.organization_id
        ).execute().data[0]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo actualizar la organización: {exc}")
    return fila


@router.get("/miembros")
async def miembros_organizacion(user_id: str):
    """Fase D — mapa user_id → nombre para el 'hecho por X' del frontend."""
    from app.services.organizacion import listar_miembros
    return listar_miembros(user_id)


class InvitarRequest(BaseModel):
    user_id: str            # el invitador (debe ser admin)
    email: str
    rol: str = "miembro"    # "admin" | "miembro"
    responsable_id: Optional[str] = None  # si viene del canvas del Workflow Builder


@router.post("/invitar")
async def invitar_miembro(req: InvitarRequest):
    """Fase C: dispara el correo de invitación de Supabase y registra la
    membresía. Idempotente si ya estaba en la organización."""
    from app.services.organizacion import invitar_a_organizacion
    try:
        return invitar_a_organizacion(
            req.user_id, req.email, req.rol, req.responsable_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
