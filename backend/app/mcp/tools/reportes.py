"""MCP tool: generar_reporte — genera reporte PDF de cotizaciones."""
import httpx

API_BASE = "http://localhost:8000"


async def generar_reporte(
    tipo: str,
    cotizacion_id: str = "",
    proyecto_id: str = "",
    periodo: str = "mes",
    formato: str = "pdf",
    user_id: str = "",
) -> dict:
    """
    Genera un reporte descargable de cotizaciones, OCs o gastos.

    Args:
        tipo: 'cotizacion', 'oc', 'gastos', 'proyecto', 'comparativo'
        cotizacion_id: ID de cotizacion especifica (para tipo='cotizacion')
        proyecto_id: ID de proyecto (para tipo='proyecto')
        periodo: 'mes', 'trimestre', 'anio' (para tipo='gastos')
        formato: 'pdf' o 'excel'
        user_id: ID del usuario Claria

    Returns:
        URL de descarga del reporte generado
    """
    tipos_validos = {"cotizacion", "oc", "gastos", "proyecto", "comparativo"}
    if tipo not in tipos_validos:
        return {"error": f"Tipo invalido. Use: {', '.join(tipos_validos)}"}

    formatos_validos = {"pdf", "excel"}
    if formato not in formatos_validos:
        return {"error": "Formato debe ser 'pdf' o 'excel'"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            body = {
                "tipo": tipo,
                "formato": formato,
                "periodo": periodo,
                "user_id": user_id,
            }
            if cotizacion_id:
                body["cotizacion_id"] = cotizacion_id
            if proyecto_id:
                body["proyecto_id"] = proyecto_id

            resp = await client.post(f"{API_BASE}/api/reportes/generar", json=body)
            data = resp.json() if resp.status_code in (200, 201) else {}
        except Exception:
            data = {}

    if not data or data.get("error"):
        return {"error": data.get("error", "Error al generar el reporte")}

    return {
        "tipo": tipo,
        "formato": formato,
        "url_descarga": data.get("url", ""),
        "nombre_archivo": data.get("nombre", f"reporte_{tipo}.{formato}"),
        "tamaño_bytes": data.get("size", 0),
        "generado_en": data.get("created_at", ""),
        "expira_en": data.get("expires_at", ""),
        "mensaje": f"Reporte {tipo} en {formato.upper()} listo para descargar",
    }
