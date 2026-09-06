"""Bienvenida común para clientes MCP de Baiyer."""
from __future__ import annotations

from app.services.mcp_context import ApplicationActorContext


BANNER = r"""
██████╗  █████╗ ██╗██╗   ██╗███████╗██████╗
██╔══██╗██╔══██╗██║╚██╗ ██╔╝██╔════╝██╔══██╗
██████╔╝███████║██║ ╚████╔╝ █████╗  ██████╔╝
██╔══██╗██╔══██║██║  ╚██╔╝  ██╔══╝  ██╔══██╗
██████╔╝██║  ██║██║   ██║   ███████╗██║  ██║
╚═════╝ ╚═╝  ╚═╝╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═════╝
""".strip()


def bienvenida(actor: ApplicationActorContext) -> dict[str, object]:
    return {
        "banner": BANNER,
        "saludo": "Empleado digital de compras",
        "organizacion": actor.organization_name,
        "capacidades": [
            "Cotizar necesidades y comparar alternativas",
            "Consultar proveedores, listas, aprobaciones y órdenes de compra",
            "Preparar acciones que requieren aprobación humana",
        ],
        "siguiente_paso": "Cuéntame qué necesitas comprar o consulta una lista existente.",
    }
