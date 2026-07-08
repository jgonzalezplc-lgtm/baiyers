"""MCP tool: buscar_proveedores — lista proveedores con scores."""
import httpx

API_BASE = "http://localhost:8000"


async def buscar_proveedores(
    rubro: str = "",
    ciudad: str = "",
    min_score: float = 0.0,
    user_id: str = "",
) -> dict:
    """
    Lista los proveedores registrados en Claria con sus scores y datos de contacto.

    Args:
        rubro: Filtrar por rubro o categoria (ej: 'electronica', 'ferreteria')
        ciudad: Filtrar por ciudad (ej: 'Santiago', 'Valparaiso')
        min_score: Score minimo del proveedor (0-5)
        user_id: ID del usuario Claria

    Returns:
        Lista de proveedores con nombre, rubro, score, email y telefono
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = {"user_id": user_id}
            if rubro:
                params["rubro"] = rubro
            if ciudad:
                params["ciudad"] = ciudad

            resp = await client.get(f"{API_BASE}/api/suppliers", params=params)
            data = resp.json() if resp.status_code == 200 else []
        except Exception:
            data = []

    proveedores = data if isinstance(data, list) else data.get("proveedores", [])

    if min_score > 0:
        proveedores = [p for p in proveedores if (p.get("score") or 0) >= min_score]

    return {
        "total": len(proveedores),
        "filtros": {"rubro": rubro, "ciudad": ciudad, "min_score": min_score},
        "proveedores": [
            {
                "id": p.get("id", ""),
                "nombre": p.get("nombre", ""),
                "rubro": p.get("rubro", ""),
                "ciudad": p.get("ciudad", ""),
                "email": p.get("email", ""),
                "telefono": p.get("telefono", ""),
                "score": p.get("score", 0),
                "total_cotizaciones": p.get("total_cotizaciones", 0),
                "tiempo_respuesta_horas": p.get("tiempo_respuesta_horas"),
            }
            for p in proveedores[:50]
        ],
    }
