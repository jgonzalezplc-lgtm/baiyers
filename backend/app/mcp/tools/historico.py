"""MCP tool: historico_precios — historial de precios de un item."""
import httpx

API_BASE = "http://localhost:8000"


async def historico_precios(
    item_nombre: str,
    precio_actual_clp: int = 0,
    user_id: str = "",
) -> dict:
    """
    Consulta el historial de precios de un item comprado anteriormente.

    Args:
        item_nombre: Nombre del item a consultar
        precio_actual_clp: Precio actual para comparar (0 = no comparar)
        user_id: ID del usuario Claria

    Returns:
        Historial con estadisticas, tendencia y evaluacion del precio actual
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(
                f"{API_BASE}/api/historico/item",
                params={"item_nombre": item_nombre, "user_id": user_id}
            )
            data = resp.json() if resp.status_code == 200 else {"sin_historial": True}
        except Exception:
            data = {"sin_historial": True}

    if data.get("sin_historial"):
        return {
            "item_nombre": item_nombre,
            "sin_historial": True,
            "mensaje": "No hay historial de precios previo para este item",
        }

    result = {
        "item_nombre": item_nombre,
        "sin_historial": False,
        "total_compras": data.get("total_compras", 0),
        "precio_minimo_clp": data.get("precio_min", 0),
        "precio_maximo_clp": data.get("precio_max", 0),
        "precio_promedio_clp": data.get("precio_promedio", 0),
        "ultima_compra": data.get("ultima_compra", ""),
        "tendencia": data.get("tendencia", "estable"),
        "mejor_proveedor": data.get("mejor_proveedor", ""),
        "historial": data.get("historial", []),
    }

    if precio_actual_clp and data.get("precio_promedio"):
        promedio = data["precio_promedio"]
        diff_pct = ((precio_actual_clp - promedio) / promedio) * 100
        if diff_pct <= -10:
            evaluacion = {"estado": "deal", "emoji": "🟢", "texto": "Precio excelente, muy por debajo del promedio"}
        elif diff_pct <= 5:
            evaluacion = {"estado": "normal", "emoji": "⚪", "texto": "Precio normal, cerca del promedio historico"}
        elif diff_pct <= 25:
            evaluacion = {"estado": "alto", "emoji": "🟡", "texto": "Precio ligeramente alto vs historico"}
        else:
            evaluacion = {"estado": "muy_alto", "emoji": "🔴", "texto": "Precio muy por encima del historico"}

        evaluacion["diferencia_pct"] = round(diff_pct, 1)
        evaluacion["precio_actual_clp"] = precio_actual_clp
        result["evaluacion_precio"] = evaluacion

    return result
