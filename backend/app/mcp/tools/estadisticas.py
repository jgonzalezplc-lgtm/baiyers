"""MCP tool: consultar_gastos — estadisticas de gasto del usuario."""
import httpx

API_BASE = "http://localhost:8000"


async def consultar_gastos(
    periodo: str = "mes",
    año: int = 0,
    mes: int = 0,
    user_id: str = "",
) -> dict:
    """
    Retorna estadisticas de gasto y cotizaciones del usuario.

    Args:
        periodo: 'mes', 'trimestre', 'anio', 'todo' (default: 'mes')
        año: Ano especifico (0 = actual)
        mes: Mes especifico 1-12 (0 = actual, solo con periodo='mes')
        user_id: ID del usuario Claria

    Returns:
        Gasto total, top proveedores, top items, tendencias
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = {"user_id": user_id, "periodo": periodo}
            if año:
                params["anio"] = str(año)
            if mes:
                params["mes"] = str(mes)

            resp = await client.get(f"{API_BASE}/api/estadisticas/resumen", params=params)
            data = resp.json() if resp.status_code == 200 else {}
        except Exception:
            data = {}

    if not data:
        return {
            "periodo": periodo,
            "mensaje": "No hay datos de gasto disponibles para el periodo seleccionado",
            "gasto_total_clp": 0,
        }

    return {
        "periodo": periodo,
        "gasto_total_clp": data.get("gasto_total", 0),
        "cotizaciones_realizadas": data.get("total_cotizaciones", 0),
        "ocs_emitidas": data.get("total_ocs", 0),
        "proveedores_activos": data.get("proveedores_activos", 0),
        "top_proveedores": data.get("top_proveedores", []),
        "top_items": data.get("top_items", []),
        "gasto_por_mes": data.get("gasto_por_mes", []),
        "ahorro_estimado_clp": data.get("ahorro_estimado", 0),
        "categoria_mayor_gasto": data.get("categoria_mayor_gasto", ""),
    }
