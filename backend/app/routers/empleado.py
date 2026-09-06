"""Centro de control del empleado digital (F1)."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/empleado", tags=["empleado-digital"])


class CanalCorreoRequest(BaseModel):
    direccion_operativa: str
    etiqueta_gmail: str = Field(default="Baiyer/Compras", min_length=1, max_length=100)


@router.get("/canales")
async def listar_canales(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.empleado.canales import obtener_canales
    from app.services.supabase import get_supabase
    return obtener_canales(get_supabase(), ctx)


@router.put("/canales/correo")
async def configurar_correo(req: CanalCorreoRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.empleado.canales import crear_canal_correo
    from app.services.supabase import get_supabase
    return crear_canal_correo(
        get_supabase(), ctx,
        direccion_operativa=req.direccion_operativa,
        etiqueta_gmail=req.etiqueta_gmail,
    )
