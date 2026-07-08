"""MCP tool: emitir_oc — emite una orden de compra."""
import httpx

API_BASE = "http://localhost:8000"


async def emitir_oc(
    proveedor_id: str,
    items: list[dict],
    notas: str = "",
    user_id: str = "",
) -> dict:
    """
    Emite una Orden de Compra (OC) a un proveedor especificado.

    Args:
        proveedor_id: ID del proveedor en Claria
        items: Lista de items [{nombre, cantidad, precio_unitario_clp}]
        notas: Notas adicionales para el proveedor
        user_id: ID del usuario Claria

    Returns:
        OC creada con numero, monto total y estado
    """
    if not items:
        return {"error": "Debe especificar al menos un item"}

    total_clp = sum(
        item.get("cantidad", 1) * item.get("precio_unitario_clp", 0)
        for item in items
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{API_BASE}/api/oc/crear", json={
                "proveedor_id": proveedor_id,
                "items": items,
                "notas": notas,
                "user_id": user_id,
            })
            data = resp.json() if resp.status_code in (200, 201) else {}
        except Exception:
            data = {}

    if not data or data.get("error"):
        return {
            "error": data.get("error", "Error al emitir la OC"),
            "detalle": "Verifica que el proveedor_id sea valido y que el plan sea Pro o superior",
        }

    return {
        "oc_id": data.get("id", ""),
        "numero_oc": data.get("numero_oc", ""),
        "proveedor_id": proveedor_id,
        "estado": data.get("estado", "pendiente"),
        "items": items,
        "total_clp": total_clp,
        "notas": notas,
        "creada_en": data.get("created_at", ""),
        "mensaje": f"OC emitida exitosamente por ${total_clp:,.0f} CLP",
    }
