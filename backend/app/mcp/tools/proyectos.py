"""MCP tool: crear_proyecto — crea un proyecto con cubicacion."""
import httpx

API_BASE = "http://localhost:8000"


async def crear_proyecto(
    nombre: str,
    descripcion: str,
    items: list[dict],
    fecha_inicio: str = "",
    fecha_fin: str = "",
    user_id: str = "",
) -> dict:
    """
    Crea un proyecto de compras con su lista de materiales y cubicacion.

    Args:
        nombre: Nombre del proyecto
        descripcion: Descripcion del proyecto
        items: Lista de items [{nombre, cantidad, unidad, descripcion_opcional}]
        fecha_inicio: Fecha de inicio ISO (YYYY-MM-DD)
        fecha_fin: Fecha de termino ISO (YYYY-MM-DD)
        user_id: ID del usuario Claria

    Returns:
        Proyecto creado con ID y lista de items registrada
    """
    if not items:
        return {"error": "Debe especificar al menos un item en el proyecto"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = {
                "nombre": nombre,
                "descripcion": descripcion,
                "items": items,
                "user_id": user_id,
            }
            if fecha_inicio:
                body["fecha_inicio"] = fecha_inicio
            if fecha_fin:
                body["fecha_fin"] = fecha_fin

            resp = await client.post(f"{API_BASE}/api/proyectos", json=body)
            data = resp.json() if resp.status_code in (200, 201) else {}
        except Exception:
            data = {}

    if not data or data.get("error"):
        return {"error": data.get("error", "Error al crear el proyecto")}

    return {
        "id": data.get("id", ""),
        "nombre": nombre,
        "descripcion": descripcion,
        "total_items": len(items),
        "items": items,
        "fecha_inicio": fecha_inicio or None,
        "fecha_fin": fecha_fin or None,
        "estado": data.get("estado", "activo"),
        "creado_en": data.get("created_at", ""),
        "mensaje": f"Proyecto '{nombre}' creado con {len(items)} items",
    }
