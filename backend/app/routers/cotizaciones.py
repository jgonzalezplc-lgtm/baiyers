"""
Gestión de cotizaciones: listado, stats dashboard, resultados rankeados,
registro de respuesta de proveedor y comparador de proveedores.

Columnas reales:
  cotizaciones: id, user_id, descripcion, nombre_identificado, marca, numero_parte,
                categoria, terminos_busqueda_es, terminos_busqueda_en, estado,
                confianza_ia (nueva), created_at, updated_at
  resultados:   id, cotizacion_id, proveedor_nombre, proveedor_email, precio, moneda,
                url, pais, fuente, tipo_proveedor, relevante, solicitud_enviada_at,
                respuesta_recibida_at, precio_cotizado, moneda_cotizada (nueva),
                plazo_entrega, condiciones_pago, notas_respuesta (nueva), estado, created_at
  ordenes_compra: id, cotizacion_id, resultado_id, user_id, numero_oc, estado,
                  precio_total, precio_unitario, moneda, proveedor_nombre, ...
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["cotizaciones"])


# ─── Dashboard stats ──────────────────────────────────────────────────────────

@router.get("/dashboard/stats")
async def dashboard_stats(user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    now = datetime.now(timezone.utc)
    mes_inicio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    cots = sb.table("cotizaciones").select("id").eq("user_id", user_id).gte("created_at", mes_inicio).execute()
    n_cotizaciones = len(cots.data or [])

    cot_ids = [c["id"] for c in (cots.data or [])]

    # Proveedores contactados
    n_proveedores = 0
    if cot_ids:
        res_contactados = (
            sb.table("resultados")
            .select("proveedor_nombre")
            .eq("estado", "contactado")
            .in_("cotizacion_id", cot_ids)
            .execute()
        )
        n_proveedores = len(set(r["proveedor_nombre"] for r in (res_contactados.data or [])))

    # OC emitidas — la columna es precio_total no total
    n_ocs = 0
    total_oc = 0.0
    try:
        ocs = (
            sb.table("ordenes_compra")
            .select("id, precio_total")
            .eq("user_id", user_id)
            .gte("created_at", mes_inicio)
            .execute()
        )
        n_ocs = len(ocs.data or [])
        total_oc = sum(float(o.get("precio_total") or 0) for o in (ocs.data or []))
    except Exception:
        pass

    return {
        "cotizaciones": n_cotizaciones,
        "proveedores": n_proveedores,
        "ocs": n_ocs,
        "totalOC": total_oc,
    }


# ─── Listar cotizaciones ───────────────────────────────────────────────────────

@router.get("/cotizaciones")
async def listar_cotizaciones(user_id: str, limit: int = 100):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    # confianza_ia puede no existir si no se corrió la migración aún
    try:
        cots = (
            sb.table("cotizaciones")
            .select("id, nombre_identificado, marca, categoria, estado, confianza_ia, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        cots = (
            sb.table("cotizaciones")
            .select("id, nombre_identificado, marca, categoria, estado, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    rows = cots.data or []

    if not rows:
        return []

    cot_ids = [c["id"] for c in rows]

    # Resultados enriquecidos por cotización
    res_data = (
        sb.table("resultados")
        .select(
            "cotizacion_id, proveedor_nombre, precio, moneda, pais, fuente, estado, "
            "solicitud_enviada_at, respuesta_recibida_at, precio_cotizado, plazo_entrega"
        )
        .in_("cotizacion_id", cot_ids)
        .execute()
    )
    resultados_por_cot: dict[str, list] = {}
    for r in (res_data.data or []):
        resultados_por_cot.setdefault(r["cotizacion_id"], []).append(r)

    # OC por cotización
    oc_por_cot: dict[str, float] = {}
    try:
        ocs = (
            sb.table("ordenes_compra")
            .select("cotizacion_id, precio_total")
            .in_("cotizacion_id", cot_ids)
            .execute()
        )
        for o in (ocs.data or []):
            oc_por_cot[o["cotizacion_id"]] = float(o.get("precio_total") or 0)
    except Exception:
        pass

    resultado = []
    for c in rows:
        cid = c["id"]
        res_list = resultados_por_cot.get(cid, [])
        precios = [r["precio"] for r in res_list if r.get("precio") is not None]
        precios_cotizados = [r["precio_cotizado"] for r in res_list if r.get("precio_cotizado") is not None]

        n_encontrados = len(res_list)
        n_enviados = sum(1 for r in res_list if r.get("solicitud_enviada_at"))
        n_respondieron = sum(1 for r in res_list if r.get("respuesta_recibida_at"))
        precio_min = min(precios_cotizados) if precios_cotizados else (min(precios) if precios else None)

        resultado.append({
            "id": cid,
            "nombre_identificado": c.get("nombre_identificado", ""),
            "marca": c.get("marca"),
            "categoria": c.get("categoria"),
            "estado": c.get("estado", "identificado"),
            "confianza_ia": c.get("confianza_ia"),
            "created_at": c.get("created_at"),
            "n_encontrados": n_encontrados,
            "n_enviados": n_enviados,
            "n_respondieron": n_respondieron,
            "precio_min": precio_min,
            "total_oc": oc_por_cot.get(cid),
        })

    return resultado


# ─── Detalle de una cotización con todos sus resultados ───────────────────────

@router.get("/cotizaciones/{cotizacion_id}/detalle")
async def detalle_cotizacion(cotizacion_id: str):
    import asyncio
    from app.services.supabase import get_supabase
    sb = get_supabase()

    # Columnas base que siempre existen
    base_cols = (
        "id, cotizacion_id, proveedor_nombre, proveedor_email, precio, moneda, url, "
        "pais, fuente, tipo_proveedor, relevante, solicitud_enviada_at, "
        "respuesta_recibida_at, precio_cotizado, plazo_entrega, condiciones_pago, "
        "estado, created_at"
    )

    def _q_cotizacion():
        return sb.table("cotizaciones").select("*").eq("id", cotizacion_id).single().execute()

    def _q_resultados():
        # Intentar con columnas opcionales (pueden faltar si la migración 015 no corrió)
        try:
            return (sb.table("resultados")
                    .select(base_cols + ", notas_respuesta, moneda_cotizada, metadata")
                    .eq("cotizacion_id", cotizacion_id)
                    .order("created_at").execute())
        except Exception:
            return (sb.table("resultados")
                    .select(base_cols)
                    .eq("cotizacion_id", cotizacion_id)
                    .order("created_at").execute())

    def _q_ocs():
        try:
            return sb.table("ordenes_compra").select("*").eq("cotizacion_id", cotizacion_id).execute()
        except Exception:
            return None

    # Las 3 consultas en paralelo (el cliente supabase es síncrono)
    cot, res, ocs = await asyncio.gather(
        asyncio.to_thread(_q_cotizacion),
        asyncio.to_thread(_q_resultados),
        asyncio.to_thread(_q_ocs),
    )

    if not cot.data:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    rows = res.data or []

    # Calcular score de ranking
    precios_efectivos = []
    for r in rows:
        p = r.get("precio_cotizado") or r.get("precio")
        if p is not None:
            precios_efectivos.append(p)

    p_min = min(precios_efectivos) if precios_efectivos else None
    p_max = max(precios_efectivos) if precios_efectivos else None

    def calc_score(r: dict) -> float:
        score = 50.0
        p = r.get("precio_cotizado") or r.get("precio")
        if p and p_min is not None and p_max is not None and p_max != p_min:
            score += (1 - (p - p_min) / (p_max - p_min)) * 30
        elif p and p_min is not None and p == p_min:
            score += 30
        if r.get("respuesta_recibida_at"):
            score += 15
        if r.get("pais") == "CL":
            score += 5
        return round(score, 1)

    enriched = []
    for r in rows:
        r["ranking_score"] = calc_score(r)
        r["compra_nacional"] = r.get("pais") == "CL"
        enriched.append(r)

    enriched.sort(key=lambda x: x["ranking_score"], reverse=True)

    # OC emitidas para esta cotización (ya consultadas en paralelo arriba)
    ocs_data = (ocs.data or []) if ocs else []

    return {
        "cotizacion": cot.data,
        "resultados": enriched,
        "ordenes_compra": ocs_data,
    }


# ─── Selección para el comparador ─────────────────────────────────────────────

class SeleccionComparadorRequest(BaseModel):
    urls: list[str]


@router.post("/cotizaciones/{cotizacion_id}/comparador")
async def seleccionar_comparador(cotizacion_id: str, req: SeleccionComparadorRequest):
    """Marca qué resultados van al comparador: relevante=true para los
    seleccionados, false para el resto aún no contactado."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    rows = (sb.table("resultados")
            .select("id, url, solicitud_enviada_at")
            .eq("cotizacion_id", cotizacion_id)
            .execute()).data or []

    urls_sel = set(req.urls)
    ids_seleccionados = [r["id"] for r in rows if r.get("url") in urls_sel]
    # solo se descartan los que no fueron contactados por correo
    ids_descartados = [
        r["id"] for r in rows
        if r.get("url") not in urls_sel and not r.get("solicitud_enviada_at")
    ]

    # Dos updates en lote, en paralelo (el cliente supabase es síncrono)
    import asyncio

    def _marcar(ids: list, valor: bool):
        if ids:
            sb.table("resultados").update({"relevante": valor}).in_("id", ids).execute()

    await asyncio.gather(
        asyncio.to_thread(_marcar, ids_seleccionados, True),
        asyncio.to_thread(_marcar, ids_descartados, False),
    )

    return {"success": True, "seleccionados": len(ids_seleccionados)}


# ─── Descartar un resultado del comparador ────────────────────────────────────

@router.post("/resultados/{resultado_id}/descartar")
async def descartar_resultado(resultado_id: str):
    """Saca un proveedor del comparador (relevante=false). Se puede recuperar
    volviendo a la búsqueda y seleccionándolo de nuevo."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("resultados").update({"relevante": False}).eq("id", resultado_id).execute()
    return {"success": True}


# ─── Datos para el informe de cotización (PDF) ────────────────────────────────

def _extraer_descripcion_html(html: str) -> Optional[str]:
    """Extrae descripción de una página: og:description > meta description > <title>."""
    import re as _re
    for pat in (
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<title[^>]*>([^<]+)</title>',
    ):
        m = _re.search(pat, html, _re.IGNORECASE)
        if m:
            texto = m.group(1).strip()
            if len(texto) > 20:
                return texto[:400]
    return None


@router.get("/cotizaciones/{cotizacion_id}/informe")
async def datos_informe(cotizacion_id: str):
    """Datos para el Informe de Cotización en PDF: ítem + proveedores del
    comparador con descripción (metadata o scrapeada en vivo de la página),
    precio y URL de origen."""
    import asyncio
    import json as _json
    import httpx
    from app.services.supabase import get_supabase
    sb = get_supabase()

    cot = sb.table("cotizaciones").select("*").eq("id", cotizacion_id).single().execute()
    if not cot.data:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    base_cols = (
        "id, proveedor_nombre, proveedor_email, precio, moneda, url, pais, fuente, "
        "relevante, solicitud_enviada_at, precio_cotizado, plazo_entrega, condiciones_pago"
    )
    try:
        res = sb.table("resultados").select(base_cols + ", metadata").eq("cotizacion_id", cotizacion_id).execute()
    except Exception:
        res = sb.table("resultados").select(base_cols).eq("cotizacion_id", cotizacion_id).execute()

    # Mismo criterio que el comparador: seleccionados o ya contactados
    rows = [r for r in (res.data or []) if r.get("relevante") is not False or r.get("solicitud_enviada_at")]

    proveedores = []
    for r in rows:
        meta: dict = {}
        try:
            meta = _json.loads(r["metadata"]) if r.get("metadata") else {}
        except Exception:
            pass
        proveedores.append({
            "proveedor": r.get("proveedor_nombre"),
            "fuente": meta.get("fuente_label") or r.get("fuente"),
            "precio": r.get("precio"),
            "moneda": r.get("moneda") or "CLP",
            "precio_cotizado": r.get("precio_cotizado"),
            "plazo_entrega": r.get("plazo_entrega") or meta.get("plazo_entrega_estimado"),
            "ubicacion": meta.get("ubicacion_vendedor") or ("Chile" if r.get("pais") == "CL" else r.get("pais")),
            "contacto": r.get("proveedor_email"),
            "url": r.get("url") or "",
            "descripcion": meta.get("descripcion") or meta.get("titulo"),
        })

    # Scrapear descripción en vivo para los que no la tienen (best-effort).
    # Las URLs de resultados de Google Shopping son páginas de búsqueda: se omiten.
    pendientes = [
        p for p in proveedores
        if not p["descripcion"] and p["url"].startswith("http") and "google.com/search" not in p["url"]
    ]
    if pendientes:
        sem = asyncio.Semaphore(6)

        async def scrape(p: dict):
            async with sem:
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=6.0) as client:
                        resp = await client.get(p["url"], headers={"User-Agent": "Mozilla/5.0 (Macintosh) Claria/1.0"})
                        if resp.status_code == 200:
                            p["descripcion"] = _extraer_descripcion_html(resp.text)
                except Exception:
                    pass

        await asyncio.gather(*(scrape(p) for p in pendientes))

    return {
        "cotizacion": {
            "id": cot.data["id"],
            "nombre": cot.data.get("nombre_identificado") or cot.data.get("descripcion") or "Ítem",
            "marca": cot.data.get("marca"),
            "numero_parte": cot.data.get("numero_parte"),
            "categoria": cot.data.get("categoria"),
            "created_at": cot.data.get("created_at"),
        },
        "proveedores": proveedores,
    }


# ─── Registrar respuesta de proveedor ─────────────────────────────────────────

class RespuestaProveedorRequest(BaseModel):
    precio_cotizado: Optional[float] = None
    moneda_cotizada: Optional[str] = "CLP"
    plazo_entrega: Optional[str] = None
    condiciones_pago: Optional[str] = None
    notas_respuesta: Optional[str] = None
    tipo_proveedor: Optional[str] = None


@router.post("/resultados/{resultado_id}/respuesta")
async def registrar_respuesta(resultado_id: str, req: RespuestaProveedorRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    now_iso = datetime.now(timezone.utc).isoformat()
    update_data: dict = {
        "respuesta_recibida_at": now_iso,
        "estado": "respondio",
    }
    if req.precio_cotizado is not None:
        update_data["precio_cotizado"] = req.precio_cotizado
    if req.moneda_cotizada:
        update_data["moneda_cotizada"] = req.moneda_cotizada
    if req.plazo_entrega:
        update_data["plazo_entrega"] = req.plazo_entrega
    if req.condiciones_pago:
        update_data["condiciones_pago"] = req.condiciones_pago
    if req.notas_respuesta:
        try:
            update_data["notas_respuesta"] = req.notas_respuesta
        except Exception:
            pass
    if req.tipo_proveedor:
        TIPOS = {"distribuidor", "fabricante", "retail", "desconocido"}
        if req.tipo_proveedor in TIPOS:
            update_data["tipo_proveedor"] = req.tipo_proveedor

    # Primero actualizar los campos base (siempre existen)
    base_update = {k: v for k, v in update_data.items() if k not in ("moneda_cotizada", "notas_respuesta")}
    sb.table("resultados").update(base_update).eq("id", resultado_id).execute()

    # Columnas opcionales (pueden no existir si no se corrió la migración)
    optional_fields = {k: v for k, v in update_data.items() if k in ("moneda_cotizada", "notas_respuesta") and v}
    if optional_fields:
        try:
            sb.table("resultados").update(optional_fields).eq("id", resultado_id).execute()
        except Exception:
            pass  # columnas aún no migradas

    return {"ok": True, "respuesta_recibida_at": now_iso}


# ─── Actualizar estado de cotización ──────────────────────────────────────────

class EstadoRequest(BaseModel):
    estado: str


@router.patch("/cotizaciones/{cotizacion_id}/estado")
async def actualizar_estado(cotizacion_id: str, req: EstadoRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("cotizaciones").update({"estado": req.estado}).eq("id", cotizacion_id).execute()
    return {"ok": True}
