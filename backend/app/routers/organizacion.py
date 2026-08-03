"""API mínima de organización — FASE A.

Solo lectura del contexto propio, para que el frontend pueda mostrar en qué
organización está el usuario y (Fase C) qué otros miembros hay. Escritura
(invitar, cambiar rol) queda para Fase C con validación de admin.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/organizacion", tags=["organizacion"])


@router.get("/mia")
async def mi_organizacion(user_id: str):
    from app.services.organizacion import obtener_organizacion
    ctx = obtener_organizacion(user_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Sin organización")
    return ctx
