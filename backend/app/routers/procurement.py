"""
Flujo de procurement como funnel secuencial (estilo Kayak/Google Flights).

Eje central: la Lista de Cotización (purchase_event → quote_items → quote_suppliers).
Cada acción del funnel registra un evento en procurement_timeline (append-only).

Tablas (migración 013_procurement_flow.sql):
  purchase_events      evento de compra, agrupa ítems
  quote_items          ítem/producto del evento
  quote_suppliers      proveedor por ítem (fila del funnel, con estado + badge)
  procurement_timeline log append-only de eventos
  suppliers            base de proveedores (se puebla al emitir OC)

Estados de quote_suppliers:
  pendiente_cotizar → correo_enviado → respuesta_recibida → seleccionado → oc_emitida
  (descartado en cualquier momento)
"""
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timeline(sb, purchase_event_id: str, tipo: str, descripcion: str = "",
              quote_supplier_id: Optional[str] = None, quote_item_id: Optional[str] = None,
              metadata: Optional[dict] = None) -> None:
    """Registra un evento en el timeline. Nunca falla el flujo principal."""
    try:
        sb.table("procurement_timeline").insert({
            "purchase_event_id": purchase_event_id,
            "quote_supplier_id": quote_supplier_id,
            "quote_item_id": quote_item_id,
            "tipo": tipo,
            "descripcion": descripcion,
            "metadata": metadata or {},
        }).execute()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# PASO 2 — Lista de Cotización (evento de compra)
# ═══════════════════════════════════════════════════════════════════════════

class ProveedorInput(BaseModel):
    proveedor_nombre: str
    proveedor_email: Optional[str] = None
    fuente: Optional[str] = None
    url_referencia: Optional[str] = None
    precio_referencial: Optional[float] = None
    moneda_referencial: Optional[str] = "CLP"
    plazo_entrega_estimado: Optional[str] = None
    plazo_entrega_dias: Optional[int] = None
    badge: Optional[str] = None


class ItemInput(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    numero_parte: Optional[str] = None
    marca: Optional[str] = None
    cantidad: int = 1
    unidad: str = "und"
    resultado_id: Optional[str] = None
    proveedores: List[ProveedorInput] = []


class CrearEventoRequest(BaseModel):
    user_id: str
    nombre: str
    descripcion: Optional[str] = None
    cotizacion_id: Optional[str] = None
    items: List[ItemInput] = []


BADGES_VALIDOS = {"mas_conveniente", "mas_economico", "disponibilidad_inmediata"}


@router.post("/eventos")
async def crear_evento(req: CrearEventoRequest):
    """Crea un evento de compra con sus ítems y proveedores iniciales."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    ev = sb.table("purchase_events").insert({
        "user_id": req.user_id,
        "nombre": req.nombre,
        "descripcion": req.descripcion,
        "cotizacion_id": req.cotizacion_id,
        "estado": "borrador",
    }).execute()
    evento = ev.data[0]
    evento_id = evento["id"]
    _timeline(sb, evento_id, "evento_creado", f"Evento «{req.nombre}» creado")

    for orden, item in enumerate(req.items):
        _crear_item(sb, evento_id, item, orden)

    return await detalle_evento(evento_id, req.user_id)


def _crear_item(sb, evento_id: str, item: ItemInput, orden: int) -> dict:
    it = sb.table("quote_items").insert({
        "purchase_event_id": evento_id,
        "nombre": item.nombre,
        "descripcion": item.descripcion,
        "numero_parte": item.numero_parte,
        "marca": item.marca,
        "cantidad": item.cantidad,
        "unidad": item.unidad,
        "resultado_id": item.resultado_id,
        "orden": orden,
    }).execute()
    item_row = it.data[0]
    for prov in item.proveedores:
        _agregar_proveedor(sb, evento_id, item_row["id"], prov)
    return item_row


def _agregar_proveedor(sb, evento_id: str, item_id: str, prov: ProveedorInput) -> dict:
    badge = prov.badge if prov.badge in BADGES_VALIDOS else None
    qs = sb.table("quote_suppliers").insert({
        "quote_item_id": item_id,
        "proveedor_nombre": prov.proveedor_nombre,
        "proveedor_email": prov.proveedor_email,
        "fuente": prov.fuente,
        "url_referencia": prov.url_referencia,
        "precio_referencial": prov.precio_referencial,
        "moneda_referencial": prov.moneda_referencial or "CLP",
        "plazo_entrega_estimado": prov.plazo_entrega_estimado,
        "plazo_entrega_dias": prov.plazo_entrega_dias,
        "badge": badge,
        "estado": "pendiente_cotizar",
    }).execute()
    row = qs.data[0]
    _timeline(sb, evento_id, "proveedor_agregado",
              f"Proveedor «{prov.proveedor_nombre}» agregado",
              quote_supplier_id=row["id"], quote_item_id=item_id)
    return row


# ─── Listar eventos ────────────────────────────────────────────────────────

@router.get("/eventos")
async def listar_eventos(user_id: str, limit: int = 100):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    evs = (
        sb.table("purchase_events")
        .select("id, nombre, descripcion, estado, cotizacion_id, created_at, updated_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = evs.data or []
    if not rows:
        return []

    ev_ids = [e["id"] for e in rows]
    items = sb.table("quote_items").select("id, purchase_event_id").in_("purchase_event_id", ev_ids).execute()
    items_por_ev: dict[str, list] = {}
    item_ids: list[str] = []
    for it in (items.data or []):
        items_por_ev.setdefault(it["purchase_event_id"], []).append(it["id"])
        item_ids.append(it["id"])

    qs_por_item: dict[str, list] = {}
    if item_ids:
        qs = sb.table("quote_suppliers").select("quote_item_id, estado").in_("quote_item_id", item_ids).execute()
        for q in (qs.data or []):
            qs_por_item.setdefault(q["quote_item_id"], []).append(q)

    out = []
    for e in rows:
        eid = e["id"]
        its = items_por_ev.get(eid, [])
        provs = [q for i in its for q in qs_por_item.get(i, [])]
        out.append({
            **e,
            "n_items": len(its),
            "n_proveedores": len(provs),
            "n_cotizados": sum(1 for p in provs if p["estado"] in ("correo_enviado", "respuesta_recibida", "seleccionado", "oc_emitida")),
            "n_oc": sum(1 for p in provs if p["estado"] == "oc_emitida"),
        })
    return out


# ─── Detalle de evento (Lista de Cotización completa) ──────────────────────

@router.get("/eventos/{evento_id}")
async def detalle_evento(evento_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    ev = sb.table("purchase_events").select("*").eq("id", evento_id).eq("user_id", user_id).single().execute()
    if not ev.data:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    items = (
        sb.table("quote_items").select("*")
        .eq("purchase_event_id", evento_id).order("orden").execute()
    )
    item_rows = items.data or []
    item_ids = [i["id"] for i in item_rows]

    qs_por_item: dict[str, list] = {}
    if item_ids:
        qs = sb.table("quote_suppliers").select("*").in_("quote_item_id", item_ids).order("created_at").execute()
        for q in (qs.data or []):
            qs_por_item.setdefault(q["quote_item_id"], []).append(q)

    items_out = [{**it, "proveedores": qs_por_item.get(it["id"], [])} for it in item_rows]

    tl = (
        sb.table("procurement_timeline").select("*")
        .eq("purchase_event_id", evento_id).order("created_at", desc=True).execute()
    )

    return {"evento": ev.data, "items": items_out, "timeline": tl.data or []}


# ─── Agregar ítem / proveedor a evento existente ───────────────────────────

@router.post("/eventos/{evento_id}/items")
async def agregar_item(evento_id: str, item: ItemInput):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    cnt = sb.table("quote_items").select("id").eq("purchase_event_id", evento_id).execute()
    orden = len(cnt.data or [])
    row = _crear_item(sb, evento_id, item, orden)
    return {"ok": True, "item_id": row["id"]}


@router.post("/items/{item_id}/proveedores")
async def agregar_proveedor(item_id: str, prov: ProveedorInput):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    it = sb.table("quote_items").select("purchase_event_id").eq("id", item_id).single().execute()
    if not it.data:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")
    row = _agregar_proveedor(sb, it.data["purchase_event_id"], item_id, prov)
    return {"ok": True, "quote_supplier_id": row["id"]}


@router.delete("/proveedores/{qs_id}")
async def quitar_proveedor(qs_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("quote_suppliers").delete().eq("id", qs_id).execute()
    return {"ok": True}


@router.delete("/items/{item_id}")
async def quitar_item(item_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("quote_items").delete().eq("id", item_id).execute()
    return {"ok": True}


# ─── Reasignar badge ───────────────────────────────────────────────────────

class BadgeRequest(BaseModel):
    badge: Optional[str] = None  # None = quitar badge


@router.patch("/proveedores/{qs_id}/badge")
async def asignar_badge(qs_id: str, req: BadgeRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    badge = req.badge if req.badge in BADGES_VALIDOS else None
    sb.table("quote_suppliers").update({"badge": badge, "updated_at": _now()}).eq("id", qs_id).execute()
    return {"ok": True, "badge": badge}


# ═══════════════════════════════════════════════════════════════════════════
# PASO 3 — Cotización por correo
# ═══════════════════════════════════════════════════════════════════════════

class CotizarRequest(BaseModel):
    user_id: str
    quote_supplier_ids: List[str]  # uno o varios (acción masiva)


def _evento_de_qs(sb, qs_id: str) -> tuple[str, str]:
    """Devuelve (evento_id, item_id) de un quote_supplier."""
    qs = sb.table("quote_suppliers").select("quote_item_id").eq("id", qs_id).single().execute()
    item_id = qs.data["quote_item_id"]
    it = sb.table("quote_items").select("purchase_event_id").eq("id", item_id).single().execute()
    return it.data["purchase_event_id"], item_id


@router.post("/cotizar")
async def cotizar(req: CotizarRequest):
    """Marca proveedores como correo_enviado y registra timeline.
    El envío real del correo se hace vía /api/gmail/enviar desde el front (Gmail OAuth)."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    now = _now()
    actualizados = []
    for qs_id in req.quote_supplier_ids:
        evento_id, item_id = _evento_de_qs(sb, qs_id)
        sb.table("quote_suppliers").update({
            "estado": "correo_enviado", "correo_enviado_at": now, "updated_at": now,
        }).eq("id", qs_id).execute()
        prov = sb.table("quote_suppliers").select("proveedor_nombre").eq("id", qs_id).single().execute()
        _timeline(sb, evento_id, "cotizacion_enviada",
                  f"Cotización enviada a «{prov.data['proveedor_nombre']}»",
                  quote_supplier_id=qs_id, quote_item_id=item_id)
        actualizados.append(qs_id)
        _actualizar_estado_evento(sb, evento_id)
    return {"ok": True, "actualizados": actualizados}


# ═══════════════════════════════════════════════════════════════════════════
# PASO 4 — Recepción de respuesta
# ═══════════════════════════════════════════════════════════════════════════

class RespuestaRequest(BaseModel):
    precio_cotizado: Optional[float] = None
    moneda_cotizada: Optional[str] = "CLP"
    plazo_entrega_estimado: Optional[str] = None
    plazo_entrega_dias: Optional[int] = None
    condiciones: Optional[str] = None


@router.post("/proveedores/{qs_id}/respuesta")
async def registrar_respuesta(qs_id: str, req: RespuestaRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    evento_id, item_id = _evento_de_qs(sb, qs_id)
    update = {"estado": "respuesta_recibida", "updated_at": _now()}
    if req.precio_cotizado is not None:
        update["precio_cotizado"] = req.precio_cotizado
        update["moneda_cotizada"] = req.moneda_cotizada or "CLP"
    if req.plazo_entrega_estimado:
        update["plazo_entrega_estimado"] = req.plazo_entrega_estimado
    if req.plazo_entrega_dias is not None:
        update["plazo_entrega_dias"] = req.plazo_entrega_dias
    if req.condiciones:
        update["condiciones"] = req.condiciones
    sb.table("quote_suppliers").update(update).eq("id", qs_id).execute()
    _timeline(sb, evento_id, "respuesta_recibida",
              "Respuesta recibida" + (f" — ${req.precio_cotizado:,.0f}" if req.precio_cotizado else ""),
              quote_supplier_id=qs_id, quote_item_id=item_id,
              metadata={"precio": req.precio_cotizado, "plazo_dias": req.plazo_entrega_dias})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# PASO 5 — Selección y emisión de OC
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/proveedores/{qs_id}/seleccionar")
async def seleccionar_proveedor(qs_id: str):
    """Marca este proveedor como seleccionado y descarta los otros del mismo ítem."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    evento_id, item_id = _evento_de_qs(sb, qs_id)
    # descartar los demás del ítem que no tengan OC
    otros = sb.table("quote_suppliers").select("id, estado").eq("quote_item_id", item_id).neq("id", qs_id).execute()
    for o in (otros.data or []):
        if o["estado"] != "oc_emitida":
            sb.table("quote_suppliers").update({"estado": "descartado", "updated_at": _now()}).eq("id", o["id"]).execute()
    sb.table("quote_suppliers").update({"estado": "seleccionado", "updated_at": _now()}).eq("id", qs_id).execute()
    prov = sb.table("quote_suppliers").select("proveedor_nombre").eq("id", qs_id).single().execute()
    _timeline(sb, evento_id, "proveedor_seleccionado",
              f"«{prov.data['proveedor_nombre']}» seleccionado como ganador",
              quote_supplier_id=qs_id, quote_item_id=item_id)
    return {"ok": True}


class EmitirOCRequest(BaseModel):
    user_id: str
    oc_numero: Optional[str] = None
    recurrente: bool = False
    frecuencia: Optional[str] = None  # semanal | mensual | trimestral


FREQ_DIAS = {"semanal": 7, "mensual": 30, "trimestral": 90}


def _upsert_supplier(sb, user_id: str, qs: dict, monto: float) -> Optional[str]:
    """Crea o actualiza el proveedor en la base `suppliers` al emitir OC."""
    nombre = qs["proveedor_nombre"]
    email = qs.get("proveedor_email")
    fuente = qs.get("fuente")
    now = _now()
    existente = None
    try:
        if email:
            r = sb.table("suppliers").select("*").eq("user_id", user_id).eq("email", email).limit(1).execute()
            existente = (r.data or [None])[0]
        if not existente:
            r = sb.table("suppliers").select("*").eq("user_id", user_id).eq("nombre", nombre).limit(1).execute()
            existente = (r.data or [None])[0]
    except Exception:
        existente = None

    if existente:
        sb.table("suppliers").update({
            "total_ocs": (existente.get("total_ocs") or 0) + 1,
            "monto_total_clp": int((existente.get("monto_total_clp") or 0) + monto),
            "ultima_oc_at": now,
            "updated_at": now,
        }).eq("id", existente["id"]).execute()
        return existente["id"]
    ins = sb.table("suppliers").insert({
        "user_id": user_id,
        "nombre": nombre,
        "email": email,
        "fuente": fuente,
        "sitio_web": qs.get("url_referencia"),
        "total_ocs": 1,
        "monto_total_clp": int(monto),
        "ultima_oc_at": now,
    }).execute()
    return ins.data[0]["id"]


@router.post("/proveedores/{qs_id}/emitir-oc")
async def emitir_oc(qs_id: str, req: EmitirOCRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    evento_id, item_id = _evento_de_qs(sb, qs_id)
    qs = sb.table("quote_suppliers").select("*").eq("id", qs_id).single().execute().data
    item = sb.table("quote_items").select("cantidad").eq("id", item_id).single().execute().data

    precio = qs.get("precio_cotizado") or qs.get("precio_referencial") or 0
    cantidad = item.get("cantidad") or 1
    monto_total = float(precio) * cantidad
    now = _now()
    oc_numero = req.oc_numero or f"OC-{datetime.now().strftime('%Y%m%d')}-{qs_id[:6].upper()}"

    sb.table("quote_suppliers").update({
        "estado": "oc_emitida", "oc_numero": oc_numero, "oc_emitida_at": now, "updated_at": now,
    }).eq("id", qs_id).execute()

    # Poblar/actualizar base de proveedores
    supplier_id = _upsert_supplier(sb, req.user_id, qs, monto_total)
    if supplier_id:
        sb.table("quote_suppliers").update({"supplier_id": supplier_id}).eq("id", qs_id).execute()

    # Compra recurrente → marca supplier + próxima compra
    proxima = None
    if req.recurrente and req.frecuencia in FREQ_DIAS and supplier_id:
        proxima = (date.today() + timedelta(days=FREQ_DIAS[req.frecuencia])).isoformat()
        try:
            sb.table("suppliers").update({
                "recurrente": True, "frecuencia": req.frecuencia, "proxima_compra_at": proxima,
            }).eq("id", supplier_id).execute()
        except Exception:
            pass

    _timeline(sb, evento_id, "oc_emitida",
              f"OC {oc_numero} emitida — ${monto_total:,.0f}" + (" (recurrente)" if req.recurrente else ""),
              quote_supplier_id=qs_id, quote_item_id=item_id,
              metadata={"oc_numero": oc_numero, "monto_total": monto_total,
                        "recurrente": req.recurrente, "frecuencia": req.frecuencia, "proxima_compra": proxima})
    _actualizar_estado_evento(sb, evento_id)

    # Ledger (fuente de verdad) — Fase 4
    from app.routers.ledger import registrar_movimiento
    item_full = sb.table("quote_items").select("nombre").eq("id", item_id).single().execute().data
    registrar_movimiento(
        req.user_id, item_full["nombre"], qs["proveedor_nombre"], "oc_enviada",
        supplier_id=supplier_id, cantidad=cantidad,
        precio_unitario=float(precio) if precio else None,
        moneda=qs.get("moneda_cotizada") or "CLP",
        numero_oc=oc_numero, quote_supplier_id=qs_id, purchase_event_id=evento_id,
    )
    return {"ok": True, "oc_numero": oc_numero, "monto_total": monto_total,
            "supplier_id": supplier_id, "proxima_compra_at": proxima}


# ═══════════════════════════════════════════════════════════════════════════
# PASO 6 — Recepción de despacho
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/proveedores/{qs_id}/recibir")
async def recibir_despacho(qs_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    evento_id, item_id = _evento_de_qs(sb, qs_id)
    now = _now()
    sb.table("quote_suppliers").update({"despacho_recibido_at": now, "updated_at": now}).eq("id", qs_id).execute()
    prov = sb.table("quote_suppliers").select("proveedor_nombre").eq("id", qs_id).single().execute()
    _timeline(sb, evento_id, "despacho_recibido",
              f"Despacho recibido de «{prov.data['proveedor_nombre']}»",
              quote_supplier_id=qs_id, quote_item_id=item_id)
    _actualizar_estado_evento(sb, evento_id)

    # Ledger — despacho recibido = entregado
    from app.routers.ledger import registrar_movimiento
    ev = sb.table("purchase_events").select("user_id").eq("id", evento_id).single().execute().data
    item_full = sb.table("quote_items").select("nombre").eq("id", item_id).single().execute().data
    registrar_movimiento(
        ev["user_id"], item_full["nombre"], prov.data["proveedor_nombre"], "entregado",
        fecha_entrega_real=now[:10], quote_supplier_id=qs_id, purchase_event_id=evento_id,
    )
    return {"ok": True}


def _actualizar_estado_evento(sb, evento_id: str) -> None:
    """Deriva el estado del evento a partir de sus proveedores."""
    items = sb.table("quote_items").select("id").eq("purchase_event_id", evento_id).execute()
    item_ids = [i["id"] for i in (items.data or [])]
    if not item_ids:
        return
    qs = sb.table("quote_suppliers").select("estado, despacho_recibido_at").in_("quote_item_id", item_ids).execute()
    estados = [q["estado"] for q in (qs.data or [])]
    if not estados:
        return
    todas_oc = all(e in ("oc_emitida", "descartado") for e in estados) and any(e == "oc_emitida" for e in estados)
    todas_recibidas = all(q.get("despacho_recibido_at") for q in (qs.data or []) if q["estado"] == "oc_emitida")
    if todas_oc and todas_recibidas:
        nuevo = "cerrado"
    elif any(e == "oc_emitida" for e in estados):
        nuevo = "oc_emitida"
    elif any(e in ("correo_enviado", "respuesta_recibida", "seleccionado") for e in estados):
        nuevo = "en_cotizacion"
    else:
        nuevo = "borrador"
    sb.table("purchase_events").update({"estado": nuevo, "updated_at": _now()}).eq("id", evento_id).execute()


# ═══════════════════════════════════════════════════════════════════════════
# Calendario — eventos de compra activos + hitos de compras recurrentes
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/calendario")
async def calendario_procurement(user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    hitos = []

    # Compras recurrentes → próximas fechas
    try:
        provs = (
            sb.table("suppliers").select("id, nombre, frecuencia, proxima_compra_at")
            .eq("user_id", user_id).eq("recurrente", True).execute()
        )
        for p in (provs.data or []):
            if p.get("proxima_compra_at"):
                hitos.append({
                    "tipo": "compra_recurrente",
                    "fecha": p["proxima_compra_at"],
                    "titulo": f"Recompra {p['nombre']}",
                    "frecuencia": p.get("frecuencia"),
                    "supplier_id": p["id"],
                })
    except Exception:
        pass

    # Eventos de compra activos (con OC emitida sin despacho)
    evs = (
        sb.table("purchase_events").select("id, nombre, estado, created_at")
        .eq("user_id", user_id).in_("estado", ["en_cotizacion", "oc_emitida"]).execute()
    )
    for e in (evs.data or []):
        hitos.append({
            "tipo": "evento_activo",
            "fecha": (e.get("created_at") or "")[:10],
            "titulo": e["nombre"],
            "estado": e["estado"],
            "evento_id": e["id"],
        })

    hitos.sort(key=lambda h: h.get("fecha") or "")
    return hitos
