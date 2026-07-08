"""API publica — endpoints de cotizacion."""
import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from app.api_publica.auth import verificar_api_key
from app.api_publica.rate_limiter import check_and_increment, get_plan_config
from app.api_publica.error_handler import (
    error_item_not_identified,
    error_batch_not_available,
    ClariaAPIError,
)

router = APIRouter()
API_INTERNAL = "http://localhost:8000"


# ─── Request / Response models ────────────────────────────────────────────────

class CotizarRequest(BaseModel):
    item: str = Field(..., description="Descripcion del item a cotizar")
    cantidad: int = Field(1, ge=1, description="Cantidad requerida")
    unidad: str = Field("unidad", description="Unidad de medida")
    numero_parte: Optional[str] = Field(None, description="Numero de parte del fabricante")
    marca: Optional[str] = Field(None, description="Marca preferida o requerida")
    urgente: bool = Field(False, description="Priorizar disponibilidad inmediata")
    fuentes: Optional[list[str]] = Field(None, description="Fuentes a usar: chile, global, industrial")


class BatchItem(BaseModel):
    item: str
    cantidad: int = 1
    unidad: str = "unidad"
    numero_parte: Optional[str] = None
    marca: Optional[str] = None


class BatchCotizarRequest(BaseModel):
    items: list[BatchItem] = Field(..., max_length=100)
    proyecto_nombre: Optional[str] = None


# ─── Core logic ───────────────────────────────────────────────────────────────

async def _cotizar_uno(client: httpx.AsyncClient, req: CotizarRequest, user_id: str, is_test: bool) -> dict:
    """Llama al pipeline interno: identificar -> buscar."""
    t0 = time.monotonic()

    # Enrich descripcion with numero_parte and marca if provided
    descripcion = req.item
    if req.marca:
        descripcion = f"{req.marca} {descripcion}"
    if req.numero_parte:
        descripcion += f" (P/N: {req.numero_parte})"

    # Step 1: Identify
    try:
        id_resp = await asyncio.wait_for(
            client.post(f"{API_INTERNAL}/api/identificar", json={"descripcion": descripcion, "user_id": user_id}),
            timeout=20.0,
        )
        id_data = id_resp.json() if id_resp.status_code == 200 else {}
    except Exception:
        id_data = {}

    item_id = id_data.get("id") or id_data.get("item_id")
    if not item_id:
        error_item_not_identified(req.item)

    # Step 2: Search prices
    try:
        buscar_resp = await asyncio.wait_for(
            client.post(f"{API_INTERNAL}/api/buscar", json={
                "item_id": item_id,
                "cantidad": req.cantidad,
                "user_id": user_id,
            }),
            timeout=40.0,
        )
        resultados = buscar_resp.json() if buscar_resp.status_code == 200 else []
    except Exception:
        resultados = []

    elapsed_ms = round((time.monotonic() - t0) * 1000)

    # Filter by fuentes if specified
    if req.fuentes and resultados:
        resultados = [r for r in resultados if r.get("fuente", "chile") in req.fuentes] or resultados

    # Sort by price
    resultados.sort(key=lambda r: r.get("precio_clp", 999_999_999))

    cotizacion_id = f"cot_{uuid.uuid4().hex[:12]}"

    proveedores_out = [
        {
            "id": f"prov_{r.get('proveedor_id', uuid.uuid4().hex[:8])}",
            "nombre": r.get("proveedor", ""),
            "precio_unitario": r.get("precio_clp", 0),
            "precio_total": r.get("precio_clp", 0) * req.cantidad,
            "moneda": "CLP",
            "plazo_entrega_dias": r.get("plazo_dias"),
            "disponibilidad": "en_stock" if not req.urgente else r.get("disponibilidad", "consultar"),
            "url": r.get("url", ""),
            "fuente": r.get("fuente", "chile"),
            "es_proveedor_conocido": bool(r.get("proveedor_id")),
            "score_claria": r.get("score", 0),
            "email": r.get("email", ""),
        }
        for r in resultados[:20]
    ]

    return {
        "cotizacion_id": cotizacion_id,
        "item_identificado": {
            "nombre_tecnico": id_data.get("nombre_tecnico", req.item),
            "marca": id_data.get("marca", req.marca or ""),
            "categoria": id_data.get("categoria", ""),
            "confianza": id_data.get("confianza", "medio"),
        },
        "proveedores": proveedores_out,
        "total_proveedores": len(proveedores_out),
        "tiempo_busqueda_ms": elapsed_ms,
        "link_claria": f"https://claria.cc/cotizar/{cotizacion_id}",
        "test_mode": is_test,
        "creado_en": datetime.utcnow().isoformat() + "Z",
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/cotizar", summary="Cotizar un item")
async def cotizar(
    body: CotizarRequest,
    client_ctx: dict = Depends(verificar_api_key),
):
    """
    Busca precios para un item en multiples proveedores chilenos e internacionales.
    Retorna lista ordenada por precio con disponibilidad y plazo de entrega.
    """
    user_id = client_ctx["user_id"]
    plan = client_ctx["plan"]
    check_and_increment(user_id, plan, "cotizaciones")

    async with httpx.AsyncClient(timeout=65.0) as client:
        result = await _cotizar_uno(client, body, user_id, client_ctx["is_test"])
    return result


@router.post("/cotizar/batch", summary="Cotizar multiples items (Business+)")
async def cotizar_batch(
    body: BatchCotizarRequest,
    client_ctx: dict = Depends(verificar_api_key),
):
    """
    Cotiza hasta 100 items en paralelo. Solo disponible en plan Business y Enterprise.
    Ideal para cubicaciones y listas de materiales de proyectos.
    """
    plan = client_ctx["plan"]
    config = get_plan_config(plan)

    if not config.batch:
        error_batch_not_available(plan)

    user_id = client_ctx["user_id"]
    is_test = client_ctx["is_test"]

    # Charge all cotizaciones upfront
    for _ in body.items:
        check_and_increment(user_id, plan, "cotizaciones")

    async with httpx.AsyncClient(timeout=90.0) as http_client:
        tasks = [
            _cotizar_uno(
                http_client,
                CotizarRequest(item=it.item, cantidad=it.cantidad, unidad=it.unidad, numero_parte=it.numero_parte, marca=it.marca),
                user_id,
                is_test,
            )
            for it in body.items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    cotizaciones = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            cotizaciones.append({
                "item": body.items[i].item,
                "error": str(res),
                "cotizacion_id": None,
            })
        else:
            cotizaciones.append(res)

    return {
        "proyecto_nombre": body.proyecto_nombre,
        "total_items": len(body.items),
        "cotizaciones": cotizaciones,
        "exitosas": sum(1 for c in cotizaciones if c.get("cotizacion_id")),
        "con_error": sum(1 for c in cotizaciones if c.get("error")),
        "creado_en": datetime.utcnow().isoformat() + "Z",
    }
