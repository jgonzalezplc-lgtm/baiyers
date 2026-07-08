"""API publica — Proveedores."""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr

from app.api_publica.auth import verificar_api_key
from app.api_publica.error_handler import error_not_found
from supabase import create_client
from app.config import settings

router = APIRouter()
SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)


class ProveedorCreate(BaseModel):
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    rubro: Optional[str] = None
    ciudad: Optional[str] = None
    pais: str = "Chile"
    sitio_web: Optional[str] = None
    notas: Optional[str] = None


@router.get("/proveedores", summary="Listar proveedores")
async def listar_proveedores(
    categoria: Optional[str] = Query(None),
    ciudad: Optional[str] = Query(None),
    pais: Optional[str] = Query(None),
    score_min: int = Query(0, ge=0, le=100),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    client_ctx: dict = Depends(verificar_api_key),
):
    """Lista los proveedores del cliente con scores y metricas."""
    user_id = client_ctx["user_id"]
    offset = (page - 1) * limit

    try:
        q = SUPABASE.table("proveedores").select(
            "id, nombre, email, telefono, rubro, ciudad, pais, score, total_cotizaciones, created_at"
        ).eq("user_id", user_id)

        if categoria:
            q = q.ilike("rubro", f"%{categoria}%")
        if ciudad:
            q = q.ilike("ciudad", f"%{ciudad}%")
        if pais:
            q = q.ilike("pais", f"%{pais}%")
        if score_min > 0:
            q = q.gte("score", score_min)

        resp = q.order("score", desc=True).range(offset, offset + limit - 1).execute()
        proveedores = resp.data or []
    except Exception:
        proveedores = []

    return {
        "page": page,
        "limit": limit,
        "total": len(proveedores),
        "proveedores": proveedores,
    }


@router.get("/proveedores/{proveedor_id}", summary="Detalle de un proveedor")
async def get_proveedor(
    proveedor_id: str,
    client_ctx: dict = Depends(verificar_api_key),
):
    user_id = client_ctx["user_id"]

    try:
        resp = SUPABASE.table("proveedores").select("*").eq("id", proveedor_id).eq("user_id", user_id).single().execute()
        p = resp.data
    except Exception:
        p = None

    if not p:
        error_not_found("Proveedor", proveedor_id)

    return p


@router.post("/proveedores", summary="Agregar proveedor", status_code=201)
async def crear_proveedor(
    body: ProveedorCreate,
    client_ctx: dict = Depends(verificar_api_key),
):
    """Agrega un nuevo proveedor a la base del cliente."""
    user_id = client_ctx["user_id"]

    resp = SUPABASE.table("proveedores").insert({
        **body.model_dump(exclude_none=True),
        "user_id": user_id,
        "score": 50,
        "total_cotizaciones": 0,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()

    return resp.data[0] if resp.data else {"error": "No se pudo crear el proveedor"}


@router.post("/proveedores/import", summary="Importar proveedores masivamente")
async def importar_proveedores(
    proveedores: list[ProveedorCreate],
    client_ctx: dict = Depends(verificar_api_key),
):
    """Importa hasta 500 proveedores en una sola llamada."""
    if len(proveedores) > 500:
        from fastapi import HTTPException
        raise HTTPException(400, "Maximo 500 proveedores por importacion")

    user_id = client_ctx["user_id"]
    now = datetime.utcnow().isoformat()

    rows = [
        {**p.model_dump(exclude_none=True), "user_id": user_id, "score": 50, "total_cotizaciones": 0, "created_at": now}
        for p in proveedores
    ]

    try:
        resp = SUPABASE.table("proveedores").upsert(rows, on_conflict="user_id,email").execute()
        importados = len(resp.data or [])
    except Exception as e:
        importados = 0

    return {
        "importados": importados,
        "total_enviados": len(proveedores),
        "mensaje": f"{importados} proveedores importados exitosamente",
    }
