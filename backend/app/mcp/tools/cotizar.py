"""MCP tool: cotizar_item — busca precios en multiples fuentes."""
import asyncio
import httpx
from app.config import settings

API_BASE = f"http://localhost:8000"


async def cotizar_item(
    descripcion: str,
    cantidad: int = 1,
    user_id: str = "",
) -> dict:
    """
    Busca precios para un item en multiples proveedores chilenos e internacionales.

    Args:
        descripcion: Descripcion del item o producto a cotizar
        cantidad: Cantidad requerida (default: 1)
        user_id: ID del usuario Claria

    Returns:
        dict con resultados de cotizacion, precio minimo, maximo y promedio
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Identify item
        try:
            id_resp = await client.post(f"{API_BASE}/api/identificar", json={
                "descripcion": descripcion,
                "user_id": user_id,
            })
            id_data = id_resp.json() if id_resp.status_code == 200 else {}
        except Exception:
            id_data = {}

        item_id = id_data.get("id") or id_data.get("item_id")

        if not item_id:
            return {
                "error": "No se pudo identificar el item",
                "descripcion": descripcion,
            }

        # Step 2: Search prices
        try:
            buscar_resp = await client.post(f"{API_BASE}/api/buscar", json={
                "item_id": item_id,
                "cantidad": cantidad,
                "user_id": user_id,
            })
            resultados = buscar_resp.json() if buscar_resp.status_code == 200 else []
        except Exception:
            resultados = []

    if not resultados:
        return {
            "item_id": item_id,
            "descripcion": descripcion,
            "resultados": [],
            "mensaje": "No se encontraron precios disponibles",
        }

    precios = [r.get("precio_clp", 0) for r in resultados if r.get("precio_clp")]
    return {
        "item_id": item_id,
        "descripcion": descripcion,
        "cantidad": cantidad,
        "resultados": [
            {
                "proveedor": r.get("proveedor", ""),
                "precio_clp": r.get("precio_clp", 0),
                "moneda_original": r.get("moneda", "CLP"),
                "precio_original": r.get("precio", 0),
                "fuente": r.get("fuente", ""),
                "url": r.get("url", ""),
                "disponibilidad": r.get("disponibilidad", ""),
            }
            for r in resultados[:10]
        ],
        "resumen": {
            "total_fuentes": len(resultados),
            "precio_minimo_clp": min(precios) if precios else 0,
            "precio_maximo_clp": max(precios) if precios else 0,
            "precio_promedio_clp": round(sum(precios) / len(precios)) if precios else 0,
            "mejor_proveedor": resultados[0].get("proveedor", "") if resultados else "",
        },
    }
