"""MCP tool: crear_recurrencia — configura compras recurrentes."""
import httpx

API_BASE = "http://localhost:8000"


async def crear_recurrencia(
    item_nombre: str,
    cantidad: int,
    frecuencia: str,
    proveedor_id: str = "",
    precio_maximo_clp: int = 0,
    user_id: str = "",
) -> dict:
    """
    Configura una compra recurrente para un item.

    Args:
        item_nombre: Nombre del item a comprar periodicamente
        cantidad: Cantidad por compra
        frecuencia: 'semanal', 'quincenal', 'mensual', 'bimestral', 'trimestral'
        proveedor_id: ID del proveedor preferido (opcional)
        precio_maximo_clp: Precio maximo por unidad en CLP (0 = sin limite)
        user_id: ID del usuario Claria

    Returns:
        Recurrencia creada con proxima fecha de compra
    """
    frecuencias_validas = {"semanal", "quincenal", "mensual", "bimestral", "trimestral"}
    if frecuencia not in frecuencias_validas:
        return {
            "error": f"Frecuencia invalida. Use: {', '.join(frecuencias_validas)}"
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = {
                "item_nombre": item_nombre,
                "cantidad": cantidad,
                "frecuencia": frecuencia,
                "user_id": user_id,
            }
            if proveedor_id:
                body["proveedor_id"] = proveedor_id
            if precio_maximo_clp:
                body["precio_maximo_clp"] = precio_maximo_clp

            resp = await client.post(f"{API_BASE}/api/recurrencias", json=body)
            data = resp.json() if resp.status_code in (200, 201) else {}
        except Exception:
            data = {}

    if not data or data.get("error"):
        return {"error": data.get("error", "Error al crear la recurrencia")}

    return {
        "id": data.get("id", ""),
        "item_nombre": item_nombre,
        "cantidad": cantidad,
        "frecuencia": frecuencia,
        "proveedor_id": proveedor_id or None,
        "precio_maximo_clp": precio_maximo_clp or None,
        "proxima_compra": data.get("proxima_compra", ""),
        "estado": data.get("estado", "activo"),
        "mensaje": f"Recurrencia creada: {item_nombre} x{cantidad} cada {frecuencia}",
    }
