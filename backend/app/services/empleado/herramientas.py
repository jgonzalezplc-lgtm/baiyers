"""Capacidades inicialmente habilitadas para el empleado digital."""
from __future__ import annotations

from typing import Any, Mapping

from app.services.mcp_context import ApplicationActorContext


async def cotizar_necesidad(actor: ApplicationActorContext, argumentos: Mapping[str, Any]) -> dict[str, Any]:
    """Inicia una cotización sin enviar correos ni seleccionar un proveedor."""
    from app.services.mcp_quote_workflow import quote_new_project
    from app.services.supabase import get_supabase

    return await quote_new_project(
        get_supabase(), actor,
        description=str(argumentos.get("descripcion") or ""),
        name=str(argumentos.get("nombre") or "") or None,
        industry=str(argumentos.get("industria") or "") or None,
        # La clave no viene del modelo: evita dos listas si éste reintenta.
        idempotency_key=str(argumentos["idempotency_key"]),
    )


HERRAMIENTAS_F1 = {"quote_new_project": cotizar_necesidad}
