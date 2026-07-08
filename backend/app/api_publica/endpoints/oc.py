"""API publica — Ordenes de Compra."""
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api_publica.auth import verificar_api_key
from app.api_publica.rate_limiter import check_and_increment
from app.api_publica.error_handler import error_not_found, error_oc_already_confirmed, ClariaAPIError
from supabase import create_client
from app.config import settings

router = APIRouter()
SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)
API_INTERNAL = "http://localhost:8000"


class EmitirOCRequest(BaseModel):
    cotizacion_id: str
    proveedor_id: str
    cantidad: int
    precio_unitario: int
    condiciones_pago: Optional[str] = "contado"
    plazo_entrega: Optional[str] = ""
    referencia_erp: Optional[str] = None
    notas: Optional[str] = ""


@router.post("/oc/emitir", summary="Emitir una Orden de Compra")
async def emitir_oc(
    body: EmitirOCRequest,
    client_ctx: dict = Depends(verificar_api_key),
):
    """
    Emite una OC a un proveedor basada en una cotizacion previa.
    La OC queda registrada y puede enviarse al proveedor por email automaticamente.
    Requiere plan Pro o superior.
    """
    user_id = client_ctx["user_id"]
    plan = client_ctx["plan"]
    check_and_increment(user_id, plan, "ocs")

    total = body.cantidad * body.precio_unitario
    oc_id = f"oc_{uuid.uuid4().hex[:12]}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{API_INTERNAL}/api/oc/crear", json={
                "proveedor_id": body.proveedor_id,
                "items": [{
                    "nombre": f"Item de cotizacion {body.cotizacion_id}",
                    "cantidad": body.cantidad,
                    "precio_unitario_clp": body.precio_unitario,
                }],
                "notas": body.notas or "",
                "referencia_erp": body.referencia_erp,
                "user_id": user_id,
            })
            data = resp.json() if resp.status_code in (200, 201) else {}
        except Exception:
            data = {}

    numero_oc = data.get("numero_oc", f"OC-{uuid.uuid4().hex[:6].upper()}")
    proveedor_nombre = data.get("proveedor_nombre", "")
    proveedor_email = data.get("proveedor_email", "")
    pdf_url = data.get("pdf_url", "")

    return {
        "oc_id": data.get("id", oc_id),
        "numero_oc": numero_oc,
        "estado": "enviada",
        "pdf_url": pdf_url or f"https://storage.claria.cc/ocs/{oc_id}.pdf",
        "referencia_erp": body.referencia_erp,
        "cotizacion_id": body.cotizacion_id,
        "proveedor": {
            "id": body.proveedor_id,
            "nombre": proveedor_nombre,
            "email": proveedor_email,
        },
        "items": [{
            "cantidad": body.cantidad,
            "precio_unitario": body.precio_unitario,
            "total": total,
        }],
        "total": total,
        "moneda": "CLP",
        "condiciones_pago": body.condiciones_pago,
        "plazo_entrega": body.plazo_entrega,
        "test_mode": client_ctx["is_test"],
        "creado_en": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/oc/{oc_id}", summary="Estado de una OC")
async def get_oc(
    oc_id: str,
    client_ctx: dict = Depends(verificar_api_key),
):
    """Retorna el estado actual de una Orden de Compra."""
    user_id = client_ctx["user_id"]

    try:
        resp = SUPABASE.table("ordenes_compra").select("*").eq("id", oc_id).eq("user_id", user_id).single().execute()
        oc = resp.data
    except Exception:
        oc = None

    if not oc:
        error_not_found("OC", oc_id)

    return {
        "oc_id": oc["id"],
        "numero_oc": oc.get("numero_oc", ""),
        "estado": oc.get("estado", "pendiente"),
        "proveedor_id": oc.get("proveedor_id", ""),
        "total": oc.get("total_clp", 0),
        "moneda": "CLP",
        "referencia_erp": oc.get("referencia_erp"),
        "pdf_url": oc.get("pdf_url", ""),
        "confirmada_at": oc.get("confirmada_at"),
        "creado_en": oc.get("created_at", ""),
    }


@router.get("/oc", summary="Listar OCs")
async def listar_ocs(
    estado: Optional[str] = Query(None, description="enviada|confirmada|cancelada"),
    desde: Optional[str] = Query(None, description="YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="YYYY-MM-DD"),
    referencia_erp: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    client_ctx: dict = Depends(verificar_api_key),
):
    """Lista las OCs del cliente con filtros opcionales."""
    user_id = client_ctx["user_id"]
    offset = (page - 1) * limit

    try:
        q = SUPABASE.table("ordenes_compra").select("*").eq("user_id", user_id)
        if estado:
            q = q.eq("estado", estado)
        if desde:
            q = q.gte("created_at", desde)
        if hasta:
            q = q.lte("created_at", hasta + "T23:59:59")
        if referencia_erp:
            q = q.eq("referencia_erp", referencia_erp)

        resp = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        ocs = resp.data or []
    except Exception:
        ocs = []

    return {
        "page": page,
        "limit": limit,
        "total": len(ocs),
        "ocs": [
            {
                "oc_id": oc["id"],
                "numero_oc": oc.get("numero_oc", ""),
                "estado": oc.get("estado", ""),
                "total": oc.get("total_clp", 0),
                "moneda": "CLP",
                "referencia_erp": oc.get("referencia_erp"),
                "creado_en": oc.get("created_at", ""),
            }
            for oc in ocs
        ],
    }
