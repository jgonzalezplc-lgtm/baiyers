"""
Claria MCP Server — Model Context Protocol para Cotizador Inteligente.
Compatible con Claude Desktop, Claude.ai, ChatGPT (via plugin), Gemini y cualquier cliente MCP.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    CallToolRequestParams,
    ListToolsResult,
)

from app.mcp.tools.cotizar import cotizar_item
from app.mcp.tools.proveedores import buscar_proveedores
from app.mcp.tools.oc import emitir_oc
from app.mcp.tools.estadisticas import consultar_gastos
from app.mcp.tools.recurrencias import crear_recurrencia
from app.mcp.tools.historico import historico_precios
from app.mcp.tools.proyectos import crear_proyecto
from app.mcp.tools.reportes import generar_reporte

logger = logging.getLogger(__name__)

# MCP tools schema definitions
TOOLS: list[Tool] = [
    Tool(
        name="cotizar_item",
        description=(
            "Busca precios para un item o producto en multiples proveedores chilenos e internacionales. "
            "Retorna lista de proveedores con precios en CLP, precio minimo, maximo y promedio. "
            "Ideal para comparar precios antes de comprar."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "descripcion": {
                    "type": "string",
                    "description": "Descripcion del item o producto a cotizar (ej: 'tornillos acero inoxidable M8', 'cable UTP Cat6 100m')"
                },
                "cantidad": {
                    "type": "integer",
                    "description": "Cantidad requerida",
                    "default": 1,
                    "minimum": 1,
                },
                "user_id": {
                    "type": "string",
                    "description": "ID del usuario Claria (proporcionado automaticamente)"
                }
            },
            "required": ["descripcion"],
        },
    ),
    Tool(
        name="buscar_proveedores",
        description=(
            "Lista los proveedores registrados en Claria con sus scores, datos de contacto y estadisticas. "
            "Permite filtrar por rubro, ciudad y score minimo."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "rubro": {
                    "type": "string",
                    "description": "Filtrar por rubro o categoria (ej: 'electronica', 'ferreteria', 'materiales construccion')"
                },
                "ciudad": {
                    "type": "string",
                    "description": "Filtrar por ciudad (ej: 'Santiago', 'Valparaiso', 'Concepcion')"
                },
                "min_score": {
                    "type": "number",
                    "description": "Score minimo del proveedor (0-5)",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0,
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": [],
        },
    ),
    Tool(
        name="emitir_oc",
        description=(
            "Emite una Orden de Compra (OC) oficial a un proveedor. "
            "Requiere plan Pro o superior. La OC queda registrada en el sistema y puede enviarse por email automaticamente."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "proveedor_id": {
                    "type": "string",
                    "description": "ID del proveedor en Claria (usar buscar_proveedores para obtener el ID)"
                },
                "items": {
                    "type": "array",
                    "description": "Lista de items de la OC",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {"type": "string", "description": "Nombre del item"},
                            "cantidad": {"type": "integer", "description": "Cantidad"},
                            "precio_unitario_clp": {"type": "integer", "description": "Precio unitario en CLP"},
                        },
                        "required": ["nombre", "cantidad", "precio_unitario_clp"]
                    }
                },
                "notas": {
                    "type": "string",
                    "description": "Notas adicionales para el proveedor",
                    "default": ""
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": ["proveedor_id", "items"],
        },
    ),
    Tool(
        name="consultar_gastos",
        description=(
            "Retorna estadisticas detalladas de gasto en compras: total, top proveedores, top items, "
            "tendencias mensuales y ahorro estimado. Filtrable por periodo de tiempo."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "periodo": {
                    "type": "string",
                    "enum": ["mes", "trimestre", "anio", "todo"],
                    "description": "Periodo de tiempo a consultar",
                    "default": "mes"
                },
                "año": {
                    "type": "integer",
                    "description": "Año especifico (0 = actual)",
                    "default": 0
                },
                "mes": {
                    "type": "integer",
                    "description": "Mes especifico 1-12 (0 = actual)",
                    "minimum": 0,
                    "maximum": 12,
                    "default": 0
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": [],
        },
    ),
    Tool(
        name="crear_recurrencia",
        description=(
            "Configura una compra recurrente automatica para un item. "
            "El sistema cotizara y generara OCs automaticamente segun la frecuencia definida. "
            "Ideal para insumos que se compran regularmente."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "item_nombre": {
                    "type": "string",
                    "description": "Nombre del item a comprar periodicamente"
                },
                "cantidad": {
                    "type": "integer",
                    "description": "Cantidad por compra",
                    "minimum": 1
                },
                "frecuencia": {
                    "type": "string",
                    "enum": ["semanal", "quincenal", "mensual", "bimestral", "trimestral"],
                    "description": "Frecuencia de compra"
                },
                "proveedor_id": {
                    "type": "string",
                    "description": "ID del proveedor preferido (opcional, si se omite el sistema elige el mejor precio)"
                },
                "precio_maximo_clp": {
                    "type": "integer",
                    "description": "Precio maximo aceptable por unidad en CLP (0 = sin limite)",
                    "default": 0
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": ["item_nombre", "cantidad", "frecuencia"],
        },
    ),
    Tool(
        name="historico_precios",
        description=(
            "Consulta el historial de precios de un item comprado anteriormente. "
            "Retorna estadisticas (min/max/promedio), tendencia de precios y evaluacion del precio actual vs historico. "
            "Util para negociar con proveedores."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "item_nombre": {
                    "type": "string",
                    "description": "Nombre del item a consultar"
                },
                "precio_actual_clp": {
                    "type": "integer",
                    "description": "Precio actual cotizado para comparar con el historico (0 = no comparar)",
                    "default": 0
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": ["item_nombre"],
        },
    ),
    Tool(
        name="crear_proyecto",
        description=(
            "Crea un proyecto de compras con su lista de materiales y cubicacion. "
            "Permite organizar multiples items bajo un mismo proyecto (ej: obra, evento, mantenimiento). "
            "El sistema puede cotizar todos los items del proyecto en paralelo."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre del proyecto"
                },
                "descripcion": {
                    "type": "string",
                    "description": "Descripcion del proyecto"
                },
                "items": {
                    "type": "array",
                    "description": "Lista de materiales del proyecto",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {"type": "string"},
                            "cantidad": {"type": "integer"},
                            "unidad": {"type": "string", "description": "ej: unidad, metro, kg, litro"},
                            "descripcion_opcional": {"type": "string"},
                        },
                        "required": ["nombre", "cantidad"]
                    }
                },
                "fecha_inicio": {
                    "type": "string",
                    "description": "Fecha de inicio ISO (YYYY-MM-DD)"
                },
                "fecha_fin": {
                    "type": "string",
                    "description": "Fecha de termino ISO (YYYY-MM-DD)"
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": ["nombre", "items"],
        },
    ),
    Tool(
        name="generar_reporte",
        description=(
            "Genera un reporte descargable en PDF o Excel de cotizaciones, OCs o analisis de gastos. "
            "Retorna URL de descarga temporal valida por 24 horas."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["cotizacion", "oc", "gastos", "proyecto", "comparativo"],
                    "description": "Tipo de reporte a generar"
                },
                "cotizacion_id": {
                    "type": "string",
                    "description": "ID de cotizacion especifica (para tipo='cotizacion')"
                },
                "proyecto_id": {
                    "type": "string",
                    "description": "ID de proyecto (para tipo='proyecto')"
                },
                "periodo": {
                    "type": "string",
                    "enum": ["mes", "trimestre", "anio"],
                    "description": "Periodo para reporte de gastos",
                    "default": "mes"
                },
                "formato": {
                    "type": "string",
                    "enum": ["pdf", "excel"],
                    "description": "Formato del reporte",
                    "default": "pdf"
                },
                "user_id": {"type": "string", "description": "ID del usuario Claria"}
            },
            "required": ["tipo"],
        },
    ),
]

# Tool dispatcher
TOOL_HANDLERS = {
    "cotizar_item": cotizar_item,
    "buscar_proveedores": buscar_proveedores,
    "emitir_oc": emitir_oc,
    "consultar_gastos": consultar_gastos,
    "crear_recurrencia": crear_recurrencia,
    "historico_precios": historico_precios,
    "crear_proyecto": crear_proyecto,
    "generar_reporte": generar_reporte,
}


def create_mcp_server() -> Server:
    """Create and configure the Claria MCP server instance."""
    server = Server("claria-cotizador")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        try:
            result = await handler(**arguments)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except TypeError as e:
            error = {"error": f"Parametros invalidos: {str(e)}"}
            return [TextContent(type="text", text=json.dumps(error, ensure_ascii=False))]
        except Exception as e:
            logger.error(f"MCP tool {name} error: {e}")
            error = {"error": f"Error ejecutando {name}: {str(e)}"}
            return [TextContent(type="text", text=json.dumps(error, ensure_ascii=False))]

    return server


async def run_stdio_server():
    """Run MCP server in stdio mode (for Claude Desktop)."""
    from mcp.server.stdio import stdio_server

    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="claria-cotizador",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run_stdio_server())
