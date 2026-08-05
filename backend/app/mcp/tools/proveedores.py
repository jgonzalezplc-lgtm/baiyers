"""MCP tool: buscar_proveedores — lista proveedores con scores.

No llama al backend por HTTP a sí mismo (localhost hardcodeado) — llama
directo a la capa de datos en el mismo proceso, igual patrón que
`routers/suppliers.py`. Evita el antipatrón que señala
PLAN_DATA_FOUNTATION.md y evita que este tool dependa de que
`/api/suppliers` acepte auth por query param (ya no lo hace, requiere
AuthContext verificado — un MCP tool no tiene ese contexto HTTP).

Pendiente real (Fase 4 del plan, no resuelto acá): `user_id` sigue siendo
un parámetro libre que cualquier cliente MCP puede mandar — falta que las
tools MCP se autentiquen con su propio token y resuelvan el usuario desde
ahí, en vez de confiar en lo que declara el propio tool call."""


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
    try:
        from app.services.supabase import get_supabase
        from app.services.organizacion import ids_organizacion

        sb = get_supabase()
        data = sb.table("proveedores").select("*").in_(
            "user_id", ids_organizacion(user_id)
        ).order("score", desc=True).execute().data or []
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
