from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/calendario", tags=["calendario"])


from typing import Optional


@router.get("/eventos")
async def get_eventos(user_id: str, fecha_inicio: str, fecha_fin: str,
                      tipo: Optional[str] = None, proveedor: Optional[str] = None):
    """Agrega eventos de todas las tablas para el rango de fechas dado.
    Filtros opcionales (v2): tipo (csv de tipos) y proveedor (substring)."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    eventos = []

    # ── Cotizaciones ──────────────────────────────────────────────────────────
    try:
        cots = (sb.table("cotizaciones")
                .select("id, nombre_identificado, descripcion, created_at")
                .eq("user_id", user_id)
                .gte("created_at", fecha_inicio)
                .lte("created_at", fecha_fin + "T23:59:59")
                .execute())
        for c in cots.data:
            nombre = c.get("nombre_identificado") or c.get("descripcion", "Cotizacion")
            eventos.append({
                "id": f"cot-{c['id']}",
                "titulo": f"Cotizacion: {nombre[:50]}",
                "fecha_inicio": c["created_at"],
                "fecha_fin": c["created_at"],
                "tipo": "cotizacion",
                "color": "#6366f1",
                "datos": {"cotizacion_id": c["id"], "nombre": nombre},
            })
    except Exception as e:
        print(f"[Cal] cotizaciones: {e}")

    # ── Ordenes de compra ─────────────────────────────────────────────────────
    try:
        ocs = (sb.table("ordenes_compra")
               .select("id, numero_oc, proveedor_nombre, created_at, confirmada_at, fecha_entrega_estimada, fecha_entrega_efectiva")
               .eq("user_id", user_id)
               .execute())
        for oc in ocs.data:
            oc_id = oc["id"]
            num = oc.get("numero_oc", "")
            prov = oc.get("proveedor_nombre", "")

            def _en_rango(dt_str: str) -> bool:
                return fecha_inicio <= dt_str[:10] <= fecha_fin

            if oc.get("created_at") and _en_rango(oc["created_at"]):
                eventos.append({"id": f"oc-{oc_id}", "titulo": f"OC {num} — {prov}", "fecha_inicio": oc["created_at"], "fecha_fin": oc["created_at"], "tipo": "oc_emitida", "color": "#8b5cf6", "datos": {"oc_id": oc_id, "numero_oc": num, "proveedor": prov}})

            if oc.get("confirmada_at") and _en_rango(oc["confirmada_at"]):
                eventos.append({"id": f"oc-conf-{oc_id}", "titulo": f"Confirmada {num}", "fecha_inicio": oc["confirmada_at"], "fecha_fin": oc["confirmada_at"], "tipo": "oc_confirmada", "color": "#34d399", "datos": {"oc_id": oc_id, "numero_oc": num, "proveedor": prov}})

            if oc.get("fecha_entrega_estimada") and _en_rango(str(oc["fecha_entrega_estimada"])):
                dt = str(oc["fecha_entrega_estimada"])
                eventos.append({"id": f"oc-est-{oc_id}", "titulo": f"Entrega est. {num}", "fecha_inicio": dt, "fecha_fin": dt, "tipo": "entrega_estimada", "color": "#86efac", "datos": {"oc_id": oc_id, "numero_oc": num, "proveedor": prov}})

            if oc.get("fecha_entrega_efectiva") and _en_rango(str(oc["fecha_entrega_efectiva"])):
                dt = str(oc["fecha_entrega_efectiva"])
                eventos.append({"id": f"oc-efect-{oc_id}", "titulo": f"Llegada efectiva {num}", "fecha_inicio": dt, "fecha_fin": dt, "tipo": "entrega_efectiva", "color": "#059669", "datos": {"oc_id": oc_id, "numero_oc": num, "proveedor": prov}})
    except Exception as e:
        print(f"[Cal] OCs: {e}")

    # ── Recurrencias ──────────────────────────────────────────────────────────
    try:
        recs = sb.table("recurrencias").select("id, nombre, frecuencia, proxima_ejecucion").eq("user_id", user_id).eq("activa", True).execute()
        for r in recs.data:
            if r.get("proxima_ejecucion") and fecha_inicio <= r["proxima_ejecucion"][:10] <= fecha_fin:
                eventos.append({"id": f"rec-{r['id']}", "titulo": f"Recurrente: {r.get('nombre', '')}", "fecha_inicio": r["proxima_ejecucion"], "fecha_fin": r["proxima_ejecucion"], "tipo": "recurrencia", "color": "#f97316", "datos": {"recurrencia_id": r["id"], "nombre": r.get("nombre"), "frecuencia": r.get("frecuencia")}})
    except Exception as e:
        print(f"[Cal] recurrencias: {e}")

    # ── Facturas ──────────────────────────────────────────────────────────────
    try:
        facts = sb.table("facturas").select("id, proveedor_nombre, monto_total, moneda, fecha_factura, fecha_vencimiento, estado").eq("user_id", user_id).execute()
        for f in facts.data:
            monto = int(f.get("monto_total") or 0)
            prov = f.get("proveedor_nombre", "")
            if f.get("fecha_factura") and fecha_inicio <= str(f["fecha_factura"]) <= fecha_fin:
                eventos.append({"id": f"fac-{f['id']}", "titulo": f"Factura {prov} ${monto:,}", "fecha_inicio": str(f["fecha_factura"]), "fecha_fin": str(f["fecha_factura"]), "tipo": "factura", "color": "#94a3b8", "datos": {"factura_id": f["id"], "proveedor": prov, "monto": monto}})
            if f.get("fecha_vencimiento") and f.get("estado") != "pagada" and fecha_inicio <= str(f["fecha_vencimiento"]) <= fecha_fin:
                eventos.append({"id": f"fac-venc-{f['id']}", "titulo": f"Vence {prov} ${monto:,}", "fecha_inicio": str(f["fecha_vencimiento"]), "fecha_fin": str(f["fecha_vencimiento"]), "tipo": "factura_vencimiento", "color": "#f87171", "datos": {"factura_id": f["id"], "proveedor": prov, "monto": monto}})
    except Exception as e:
        print(f"[Cal] facturas: {e}")

    # Filtros v2
    if tipo:
        tipos = {t.strip() for t in tipo.split(",") if t.strip()}
        eventos = [e for e in eventos if e["tipo"] in tipos]
    if proveedor:
        p = proveedor.lower()
        eventos = [e for e in eventos if p in str(e.get("datos", {}).get("proveedor", "")).lower()]

    eventos.sort(key=lambda e: e["fecha_inicio"])
    return eventos


class LlegadaEfectivaRequest(BaseModel):
    oc_id: str
    fecha_llegada: str  # YYYY-MM-DD


@router.post("/llegada-efectiva")
async def marcar_llegada_efectiva(req: LlegadaEfectivaRequest):
    from app.services.supabase import get_supabase
    from app.services.supplier_intelligence import calcular_score, _get_or_create_proveedor

    sb = get_supabase()
    oc_res = sb.table("ordenes_compra").select("*").eq("id", req.oc_id).single().execute()
    if not oc_res.data:
        raise HTTPException(status_code=404, detail="OC no encontrada")

    oc = oc_res.data
    sb.table("ordenes_compra").update({"fecha_entrega_efectiva": req.fecha_llegada}).eq("id", req.oc_id).execute()

    # Calcular días de diferencia
    dias_diff = None
    if oc.get("fecha_entrega_estimada"):
        from datetime import date
        try:
            est = date.fromisoformat(str(oc["fecha_entrega_estimada"]))
            efect = date.fromisoformat(req.fecha_llegada)
            dias_diff = (efect - est).days
        except Exception:
            pass

    # Recalcular score
    try:
        proveedor_id = _get_or_create_proveedor(oc["user_id"], oc.get("proveedor_nombre", ""), oc.get("proveedor_email"))
        if proveedor_id:
            calcular_score(proveedor_id)
    except Exception as e:
        print(f"[Cal] Error actualizando score: {e}")

    return {"success": True, "dias_diferencia": dias_diff}
