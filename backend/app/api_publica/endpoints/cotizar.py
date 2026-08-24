"""API publica — endpoints de cotizacion."""
import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional

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

async def _cotizar_uno(req: CotizarRequest, user_id: str, is_test: bool) -> dict:
    """Identificar -> guardar -> buscar, en proceso.

    Antes esto le pegaba por HTTP a la propia API en localhost:8000. Además de
    obligar a dejar `/api/identificar` y `/api/buscar` sin autenticación (no
    había JWT que mandar), estaba roto: el cuerpo que enviaba a `/api/buscar`
    no correspondía a `BuscarRequest` (422) y leía un `item_id` de la respuesta
    de identificar que ese endpoint nunca devolvió. Este endpoint fallaba
    siempre con `item_not_identified`.
    """
    from app.services.cotizacion_pipeline import cotizar_descripcion

    t0 = time.monotonic()
    try:
        salida = await asyncio.wait_for(
            cotizar_descripcion(
                user_id=user_id, descripcion=req.item, cantidad=req.cantidad,
                marca=req.marca, numero_parte=req.numero_parte,
            ),
            timeout=60.0,
        )
    except ValueError:
        error_item_not_identified(req.item)
    except asyncio.TimeoutError:
        error_item_not_identified(req.item)

    resultados = salida["resultados"]
    id_data = {
        "nombre_tecnico": salida["nombre"],
        "marca": req.marca or "",
        "categoria": salida["categoria"] or "",
        "confianza": "medio",
    }
    elapsed_ms = round((time.monotonic() - t0) * 1000)

    # Filter by fuentes if specified
    if req.fuentes and resultados:
        resultados = [r for r in resultados if r.get("fuente", "chile") in req.fuentes] or resultados

    # Sort by price
    resultados.sort(key=lambda r: r.get("precio") or 999_999_999)

    cotizacion_id = salida["cotizacion_id"] or f"cot_{uuid.uuid4().hex[:12]}"

    proveedores_out = [
        {
            "id": f"prov_{r.get('proveedor_id', uuid.uuid4().hex[:8])}",
            "nombre": r.get("proveedor", ""),
            "precio_unitario": r.get("precio") or 0,
            "precio_total": (r.get("precio") or 0) * req.cantidad,
            "moneda": r.get("moneda") or "CLP",
            "plazo_entrega_dias": r.get("plazo_entrega_estimado"),
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

    return await _cotizar_uno(body, user_id, client_ctx["is_test"])


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

    tasks = [
        _cotizar_uno(
            CotizarRequest(item=it.item, cantidad=it.cantidad, unidad=it.unidad,
                           numero_parte=it.numero_parte, marca=it.marca),
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
