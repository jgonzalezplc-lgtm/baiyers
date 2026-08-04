"""API de organización — Fases A + C.

Lectura del contexto propio + invitación de nuevos miembros (solo admin).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/organizacion", tags=["organizacion"])


@router.get("/mia")
async def mi_organizacion(user_id: str):
    from app.services.organizacion import obtener_organizacion
    ctx = obtener_organizacion(user_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Sin organización")
    return ctx


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
