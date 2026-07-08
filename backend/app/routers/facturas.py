from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/facturas", tags=["facturas"])


class FacturaManualRequest(BaseModel):
    user_id: str
    proveedor_nombre: str
    numero_factura: Optional[str] = None
    fecha_factura: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    monto_neto: Optional[float] = None
    iva: Optional[float] = None
    monto_total: float
    moneda: str = "CLP"
    oc_id: Optional[str] = None


class PagarRequest(BaseModel):
    fecha_pago: Optional[str] = None


@router.get("")
async def listar_facturas(user_id: str, estado: Optional[str] = None, mes: Optional[str] = None):
    from app.services.supabase import get_supabase
    from datetime import date

    sb = get_supabase()
    query = sb.table("facturas").select("*").eq("user_id", user_id)

    if estado and estado != "todas":
        if estado == "vencidas":
            hoy = date.today().isoformat()
            query = query.neq("estado", "pagada").lt("fecha_vencimiento", hoy)
        else:
            query = query.eq("estado", estado)

    if mes:
        query = query.gte("fecha_factura", f"{mes}-01").lte("fecha_factura", f"{mes}-31")

    res = query.order("created_at", desc=True).execute()

    # Actualizar estado vencido automáticamente
    hoy = date.today().isoformat()
    facturas = []
    for f in res.data:
        if f.get("estado") == "pendiente" and f.get("fecha_vencimiento") and str(f["fecha_vencimiento"]) < hoy:
            sb.table("facturas").update({"estado": "vencida"}).eq("id", f["id"]).execute()
            f["estado"] = "vencida"
        facturas.append(f)

    return facturas


@router.post("")
async def crear_factura_manual(req: FacturaManualRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    # Buscar proveedor_id
    proveedor_id = None
    prov_res = sb.table("proveedores").select("id").eq("user_id", req.user_id).ilike("nombre", f"%{req.proveedor_nombre[:50]}%").limit(1).execute()
    if prov_res.data:
        proveedor_id = prov_res.data[0]["id"]

    row = {
        "user_id": req.user_id,
        "proveedor_id": proveedor_id,
        "proveedor_nombre": req.proveedor_nombre,
        "numero_factura": req.numero_factura,
        "fecha_factura": req.fecha_factura,
        "fecha_vencimiento": req.fecha_vencimiento,
        "monto_neto": req.monto_neto,
        "iva": req.iva,
        "monto_total": req.monto_total,
        "moneda": req.moneda,
        "estado": "pendiente",
        "oc_id": req.oc_id,
    }

    res = sb.table("facturas").insert(row).execute()
    return res.data[0]


@router.patch("/{factura_id}/pagar")
async def marcar_pagada(factura_id: str, user_id: str, req: PagarRequest):
    from app.services.supabase import get_supabase
    from datetime import date

    sb = get_supabase()
    existe = sb.table("facturas").select("id").eq("id", factura_id).eq("user_id", user_id).single().execute()
    if not existe.data:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    fecha_pago = req.fecha_pago or date.today().isoformat()
    sb.table("facturas").update({"estado": "pagada", "fecha_pago": fecha_pago}).eq("id", factura_id).execute()
    return {"success": True, "fecha_pago": fecha_pago}


@router.post("/scan-inbox")
async def scan_inbox(user_id: str):
    """Escanea el inbox de Gmail buscando facturas."""
    from app.services.factura_parser import scan_inbox as do_scan
    encontradas = await do_scan(user_id)
    return {"success": True, "facturas_encontradas": encontradas}


@router.get("/resumen")
async def resumen_facturas(user_id: str):
    """Totales pendiente / pagado / vencido."""
    from app.services.supabase import get_supabase
    from datetime import date

    sb = get_supabase()
    hoy = date.today().isoformat()
    mes_inicio = hoy[:7] + "-01"

    res = sb.table("facturas").select("monto_total, estado, fecha_vencimiento, moneda").eq("user_id", user_id).execute()

    total_pendiente = 0.0
    total_pagado_mes = 0.0
    total_vencido = 0.0

    for f in res.data:
        monto = float(f.get("monto_total") or 0)
        estado = f.get("estado", "pendiente")
        venc = str(f.get("fecha_vencimiento") or "")

        if estado == "pagada":
            total_pagado_mes += monto
        elif estado == "vencida" or (estado == "pendiente" and venc and venc < hoy):
            total_vencido += monto
            total_pendiente += monto
        else:
            total_pendiente += monto

    return {
        "total_pendiente": total_pendiente,
        "total_pagado_mes": total_pagado_mes,
        "total_vencido": total_vencido,
    }
