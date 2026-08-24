"""MCP tool: cotizar_item — busca precios en múltiples fuentes.

Pertenece al transporte MCP legado (`/api/mcp/sse` + `/api/mcp/rpc`). Los
clientes nuevos usan Streamable HTTP en `/api/mcp`, cuyo equivalente es
`start_web_quote`. Se mantiene funcionando mientras el legado siga expuesto.

Antes le pegaba por HTTP a la propia API (`http://localhost:8000/api/identificar`
y `/api/buscar`) con un cuerpo que no correspondía a `BuscarRequest`, así que
devolvía siempre "No se pudo identificar el item". Ahora usa el pipeline en
proceso, que es además lo que permitió cerrar esos dos endpoints con sesión.
"""
from app.services.cotizacion_pipeline import cotizar_descripcion


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
        user_id: ID del usuario Baiyer

    Returns:
        dict con resultados de cotizacion, precio minimo, maximo y promedio
    """
    try:
        salida = await cotizar_descripcion(
            user_id=user_id, descripcion=descripcion, cantidad=cantidad,
        )
    except ValueError as exc:
        return {"error": str(exc), "descripcion": descripcion}

    resultados = salida["resultados"]
    if not resultados:
        return {
            "item_id": salida["cotizacion_id"],
            "descripcion": descripcion,
            "resultados": [],
            "mensaje": "No se encontraron precios disponibles",
        }

    # Sólo se agregan precios en CLP: las fuentes internacionales devuelven USD
    # o EUR y sumarlos como si fueran pesos daba un "precio mínimo" de $0,49.
    precios = [
        r["precio"] for r in resultados
        if r.get("precio") and (r.get("moneda") or "CLP").upper() == "CLP"
    ]
    return {
        "item_id": salida["cotizacion_id"],
        "descripcion": descripcion,
        "nombre_identificado": salida["nombre"],
        "cantidad": cantidad,
        "resultados": [
            {
                "proveedor": r.get("proveedor", ""),
                "precio_clp": r.get("precio", 0),
                "moneda_original": r.get("moneda", "CLP"),
                "fuente": r.get("fuente", ""),
                "url": r.get("url", ""),
                "disponibilidad": r.get("disponibilidad", ""),
            }
            for r in resultados[:10]
        ],
        "resumen": {
            "total_fuentes": len(resultados),
            "con_precio_clp": len(precios),
            "precio_minimo_clp": min(precios) if precios else 0,
            "precio_maximo_clp": max(precios) if precios else 0,
            "precio_promedio_clp": round(sum(precios) / len(precios)) if precios else 0,
            "mejor_proveedor": resultados[0].get("proveedor", "") if resultados else "",
        },
    }
