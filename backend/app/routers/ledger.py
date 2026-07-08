"""
Procurement Ledger — fuente de verdad del ciclo de compra (Fase 4, Smart Procurement).

Cada ítem comprado deja una fila en procurement_ledger que evoluciona por estados:
  cotizacion_pendiente → oc_enviada → en_transito → entregado → facturado

Se auto-puebla desde el flujo de procurement (emitir OC, despacho recibido) vía
registrar_movimiento(), y expone consulta histórica para sugerencias y análisis.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

ESTADOS = ["cotizacion_pendiente", "oc_enviada", "en_transito", "entregado", "facturado"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── API pública del servicio (usada por otros routers) ───────────────────────

def registrar_movimiento(
    user_id: str,
    item_name: str,
    proveedor_nombre: str,
    estado: str,
    *,
    categoria: Optional[str] = None,
    supplier_id: Optional[str] = None,
    cantidad: int = 1,
    precio_unitario: Optional[float] = None,
    moneda: str = "CLP",
    numero_oc: Optional[str] = None,
    factura: Optional[str] = None,
    fecha_entrega_esperada: Optional[str] = None,
    fecha_entrega_real: Optional[str] = None,
    observaciones: Optional[str] = None,
    cotizacion_id: Optional[str] = None,
    quote_supplier_id: Optional[str] = None,
    purchase_event_id: Optional[str] = None,
) -> Optional[str]:
    """Crea o actualiza la fila del ledger para (item, proveedor, referencia).

    Si existe una fila abierta para el mismo quote_supplier_id (o item+proveedor
    sin estado terminal), la actualiza; si no, crea una nueva. Nunca lanza.
    """
    try:
        from app.services.supabase import get_supabase
        sb = get_supabase()
        now = _now()

        existente = None
        if quote_supplier_id:
            r = sb.table("procurement_ledger").select("*").eq("quote_supplier_id", quote_supplier_id).limit(1).execute()
            existente = (r.data or [None])[0]
        if not existente:
            r = (
                sb.table("procurement_ledger").select("*")
                .eq("user_id", user_id).eq("item_name", item_name)
                .eq("proveedor_nombre", proveedor_nombre)
                .neq("estado", "facturado")
                .order("created_at", desc=True).limit(1).execute()
            )
            existente = (r.data or [None])[0]

        update: dict = {"estado": estado, "updated_at": now}
        if precio_unitario is not None:
            update["precio_unitario"] = precio_unitario
            update["precio_total"] = precio_unitario * cantidad
            update["moneda"] = moneda
        if estado == "cotizacion_pendiente":
            update["fecha_cotizacion"] = now
        if estado == "oc_enviada":
            update["fecha_oc"] = now
        if fecha_entrega_esperada:
            update["fecha_entrega_esperada"] = fecha_entrega_esperada
        if fecha_entrega_real:
            update["fecha_entrega_real"] = fecha_entrega_real
        if observaciones:
            update["observaciones"] = observaciones

        if existente:
            if numero_oc:
                update["numeros_oc"] = list({*(existente.get("numeros_oc") or []), numero_oc})
            if factura:
                update["facturas_asociadas"] = list({*(existente.get("facturas_asociadas") or []), factura})
            sb.table("procurement_ledger").update(update).eq("id", existente["id"]).execute()
            return existente["id"]

        ins = sb.table("procurement_ledger").insert({
            "user_id": user_id,
            "item_name": item_name,
            "categoria": categoria,
            "supplier_id": supplier_id,
            "proveedor_nombre": proveedor_nombre,
            "cantidad_solicitada": cantidad,
            "estado": estado,
            "numeros_oc": [numero_oc] if numero_oc else [],
            "facturas_asociadas": [factura] if factura else [],
            "cotizacion_id": cotizacion_id,
            "quote_supplier_id": quote_supplier_id,
            "purchase_event_id": purchase_event_id,
            **{k: v for k, v in update.items() if k not in ("updated_at",)},
        }).execute()
        return ins.data[0]["id"]
    except Exception as e:
        print(f"[ledger] Error registrando movimiento: {e}")
        return None


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/search")
async def buscar_ledger(
    user_id: str,
    item: Optional[str] = None,
    proveedor: Optional[str] = None,
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    limit: int = 100,
):
    """Búsqueda con filtros sobre el ledger."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    q = sb.table("procurement_ledger").select("*").eq("user_id", user_id)
    if item:
        q = q.ilike("item_name", f"%{item}%")
    if proveedor:
        q = q.ilike("proveedor_nombre", f"%{proveedor}%")
    if estado and estado in ESTADOS:
        q = q.eq("estado", estado)
    if categoria:
        q = q.eq("categoria", categoria)
    if desde:
        q = q.gte("created_at", desde)
    if hasta:
        q = q.lte("created_at", hasta)
    res = q.order("created_at", desc=True).limit(limit).execute()
    return res.data or []


@router.get("/sugerencias")
async def sugerencias_item(user_id: str, item: str):
    """Histórico de compras del ítem: para mostrar 'Compraste a X hace N meses'."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = (
        sb.table("procurement_ledger").select(
            "proveedor_nombre, supplier_id, precio_unitario, moneda, estado, "
            "fecha_oc, fecha_entrega_esperada, fecha_entrega_real, created_at"
        )
        .eq("user_id", user_id).ilike("item_name", f"%{item}%")
        .order("created_at", desc=True).limit(20).execute()
    )
    rows = res.data or []
    # Agregado por proveedor
    por_prov: dict[str, dict] = {}
    for r in rows:
        p = r["proveedor_nombre"]
        if p not in por_prov:
            por_prov[p] = {
                "proveedor_nombre": p,
                "supplier_id": r.get("supplier_id"),
                "n_compras": 0,
                "ultimo_precio": r.get("precio_unitario"),
                "moneda": r.get("moneda", "CLP"),
                "ultima_compra": r.get("fecha_oc") or r.get("created_at"),
            }
        por_prov[p]["n_compras"] += 1
    return {"historial": rows, "por_proveedor": list(por_prov.values())}


@router.get("/{ledger_id}")
async def detalle_ledger(ledger_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("procurement_ledger").select("*").eq("id", ledger_id).eq("user_id", user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    return res.data


class ActualizarLedgerRequest(BaseModel):
    estado: Optional[str] = None
    fecha_entrega_real: Optional[str] = None
    observaciones: Optional[str] = None
    factura: Optional[str] = None


@router.patch("/{ledger_id}")
async def actualizar_ledger(ledger_id: str, user_id: str, req: ActualizarLedgerRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    row = sb.table("procurement_ledger").select("*").eq("id", ledger_id).eq("user_id", user_id).single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    update: dict = {"updated_at": _now()}
    if req.estado:
        if req.estado not in ESTADOS:
            raise HTTPException(status_code=400, detail=f"Estado inválido. Válidos: {ESTADOS}")
        update["estado"] = req.estado
    if req.fecha_entrega_real:
        update["fecha_entrega_real"] = req.fecha_entrega_real
    if req.observaciones is not None:
        update["observaciones"] = req.observaciones
    if req.factura:
        update["facturas_asociadas"] = list({*(row.data.get("facturas_asociadas") or []), req.factura})
    sb.table("procurement_ledger").update(update).eq("id", ledger_id).execute()
    return {"ok": True}
