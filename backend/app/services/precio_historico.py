"""Servicio de comparación de precios históricos."""
from __future__ import annotations
import asyncio
from datetime import date, timedelta
from typing import Optional


async def buscar_precios_historicos(item_nombre: str, user_id: str) -> dict:
    """
    Busca el historial de precios del ítem en resultados y cotizaciones_proyecto.
    Usa coincidencia aproximada de nombres.
    """
    from app.services.supabase import get_supabase
    sb = get_supabase()

    try:
        from rapidfuzz import fuzz
        usar_fuzzy = True
    except ImportError:
        usar_fuzzy = False

    # ── Buscar en tabla resultados (cotizaciones individuales) ─────────────────
    nombre_lower = item_nombre.lower()[:60]
    keyword = nombre_lower.split()[0] if nombre_lower.split() else nombre_lower

    res_cotizaciones = sb.table("cotizaciones").select(
        "id, nombre_identificado, created_at, user_id"
    ).eq("user_id", user_id).ilike("nombre_identificado", f"%{keyword}%").order(
        "created_at", desc=True
    ).limit(100).execute()

    precios_raw: list[dict] = []

    for cot in (res_cotizaciones.data or []):
        # filtrar por similitud si disponible
        if usar_fuzzy:
            score = fuzz.partial_ratio(nombre_lower, (cot.get("nombre_identificado") or "").lower())
            if score < 55:
                continue

        res_resultados = sb.table("resultados").select(
            "precio, moneda, proveedor_nombre, created_at"
        ).eq("cotizacion_id", cot["id"]).not_.is_("precio", "null").order(
            "precio"
        ).limit(1).execute()

        if res_resultados.data:
            r = res_resultados.data[0]
            precios_raw.append({
                "precio": float(r["precio"]),
                "moneda": r.get("moneda", "CLP"),
                "proveedor": r.get("proveedor_nombre", ""),
                "fecha": cot.get("created_at", "")[:10],
            })

    # ── Buscar en cotizaciones_proyecto ────────────────────────────────────────
    items_proy = sb.table("items_proyecto").select(
        "item, precio_total, cantidad, proveedor_nombre, created_at"
    ).not_.is_("precio_total", "null").ilike("item", f"%{keyword}%").limit(50).execute()

    for it in (items_proy.data or []):
        if usar_fuzzy:
            score = fuzz.partial_ratio(nombre_lower, (it.get("item") or "").lower())
            if score < 55:
                continue
        cantidad = float(it.get("cantidad") or 1)
        precio_u = float(it.get("precio_total") or 0) / max(cantidad, 1)
        if precio_u > 0:
            precios_raw.append({
                "precio": precio_u,
                "moneda": "CLP",
                "proveedor": it.get("proveedor_nombre") or "",
                "fecha": (it.get("created_at") or "")[:10],
            })

    if not precios_raw:
        return {"sin_historial": True}

    # Convertir todo a CLP (aproximado, sin llamada externa)
    TASAS = {"USD": 950, "EUR": 1040, "CLP": 1}
    precios_clp = []
    for p in precios_raw:
        tasa = TASAS.get(p["moneda"].upper(), 950)
        precios_clp.append({**p, "precio_clp": p["precio"] * tasa})

    precios_clp.sort(key=lambda x: x["fecha"])
    valores = [p["precio_clp"] for p in precios_clp]

    precio_min = min(valores)
    precio_max = max(valores)
    precio_prom = sum(valores) / len(valores)

    # Tendencia: comparar primera mitad vs segunda mitad
    mitad = len(valores) // 2
    if mitad > 0:
        prom_ant = sum(valores[:mitad]) / mitad
        prom_rec = sum(valores[mitad:]) / max(len(valores) - mitad, 1)
        diff_pct = (prom_rec - prom_ant) / max(prom_ant, 1) * 100
        if diff_pct > 8:
            tendencia = "subiendo"
        elif diff_pct < -8:
            tendencia = "bajando"
        else:
            tendencia = "estable"
    else:
        tendencia = "estable"

    return {
        "sin_historial": False,
        "precio_min": round(precio_min),
        "precio_max": round(precio_max),
        "precio_promedio": round(precio_prom),
        "total_compras": len(precios_clp),
        "ultima_compra": precios_clp[-1]["fecha"] if precios_clp else None,
        "tendencia": tendencia,
        "historial": precios_clp[-20:],  # últimas 20 para el gráfico
        "mejor_proveedor": min(precios_clp, key=lambda x: x["precio_clp"])["proveedor"],
    }


async def evaluar_precio_actual(precio_actual_clp: float, item_nombre: str, user_id: str) -> dict:
    """Evalúa si un precio actual es deal, normal, alto o muy alto."""
    hist = await buscar_precios_historicos(item_nombre, user_id)

    if hist.get("sin_historial"):
        return {
            "evaluacion": "primera_vez",
            "emoji": "🆕",
            "color": "#94a3b8",
            "mensaje": "Primera vez que cotizas este ítem — sin historial de comparación.",
            "sin_historial": True,
        }

    prom = hist["precio_promedio"]
    ratio = precio_actual_clp / max(prom, 1)

    if ratio < 0.90:
        ev, emoji, color = "deal", "🟢", "#34d399"
        msg = f"Excelente precio. Tu promedio histórico es ${round(prom):,} CLP — este precio es {round((1-ratio)*100)}% más barato."
    elif ratio <= 1.10:
        ev, emoji, color = "normal", "⚪", "#94a3b8"
        msg = f"Precio en rango normal. Tu promedio histórico es ${round(prom):,} CLP."
    elif ratio <= 1.30:
        ev, emoji, color = "alto", "🟡", "#f59e0b"
        msg = f"Precio algo elevado. Tu promedio histórico es ${round(prom):,} CLP — este precio es {round((ratio-1)*100)}% más caro."
    else:
        ev, emoji, color = "muy_alto", "🔴", "#f87171"
        msg = f"Precio muy caro. Tu promedio histórico es ${round(prom):,} CLP — este precio es {round((ratio-1)*100)}% más caro."

    msg += f" Has comprado este ítem {hist['total_compras']} veces."

    return {
        "evaluacion": ev,
        "emoji": emoji,
        "color": color,
        "mensaje": msg,
        "precio_promedio_historico": prom,
        "precio_min_historico": hist["precio_min"],
        "precio_max_historico": hist["precio_max"],
        "total_compras": hist["total_compras"],
        "ultima_compra": hist.get("ultima_compra"),
        "tendencia": hist.get("tendencia"),
        "sin_historial": False,
    }
