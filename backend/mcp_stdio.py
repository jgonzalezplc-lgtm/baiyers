#!/usr/bin/env python3
"""
Claria MCP stdio server — para Claude Desktop.

Configuracion en claude_desktop_config.json:
{
  "mcpServers": {
    "claria-cotizador": {
      "command": "python",
      "args": ["/ruta/a/backend/mcp_stdio.py"],
      "env": {
        "CLARIA_TOKEN": "<tu-token-mcp>",
        "CLARIA_USER_ID": "<tu-user-id>",
        "CLARIA_API_URL": "http://localhost:8000"
      }
    }
  }
}
"""
import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
os.environ.setdefault("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_SERVICE_KEY", ""))
os.environ.setdefault("GEMINI_API_KEY", "")

# Override API_BASE with env var if provided
API_URL = os.getenv("CLARIA_API_URL", "http://localhost:8000")
CLARIA_TOKEN = os.getenv("CLARIA_TOKEN", "")
CLARIA_USER_ID = os.getenv("CLARIA_USER_ID", "")

import httpx
import json
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


TOOLS = [
    Tool(
        name="cotizar_item",
        description="Busca precios para un item en multiples proveedores chilenos. Retorna lista de precios en CLP.",
        inputSchema={
            "type": "object",
            "properties": {
                "descripcion": {"type": "string", "description": "Item a cotizar"},
                "cantidad": {"type": "integer", "description": "Cantidad requerida", "default": 1},
            },
            "required": ["descripcion"],
        },
    ),
    Tool(
        name="buscar_proveedores",
        description="Lista proveedores registrados con scores y datos de contacto.",
        inputSchema={
            "type": "object",
            "properties": {
                "rubro": {"type": "string", "description": "Filtrar por rubro"},
                "min_score": {"type": "number", "description": "Score minimo 0-5", "default": 0},
            },
        },
    ),
    Tool(
        name="consultar_gastos",
        description="Estadisticas de gasto: total, top proveedores, top items.",
        inputSchema={
            "type": "object",
            "properties": {
                "periodo": {"type": "string", "enum": ["mes", "trimestre", "anio", "todo"], "default": "mes"},
            },
        },
    ),
    Tool(
        name="historico_precios",
        description="Historial de precios de un item con estadisticas y tendencia.",
        inputSchema={
            "type": "object",
            "properties": {
                "item_nombre": {"type": "string", "description": "Item a consultar"},
                "precio_actual_clp": {"type": "integer", "description": "Precio actual para comparar", "default": 0},
            },
            "required": ["item_nombre"],
        },
    ),
]


async def call_rpc(tool_name: str, arguments: dict) -> dict:
    """Call Claria MCP RPC endpoint."""
    arguments["user_id"] = CLARIA_USER_ID
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{API_URL}/api/mcp/rpc",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}},
            headers={"Authorization": f"Bearer {CLARIA_TOKEN}"},
        )
        data = resp.json()
        if "error" in data:
            return {"error": data["error"]["message"]}
        content = data.get("result", {}).get("content", [{}])
        text = content[0].get("text", "{}") if content else "{}"
        return json.loads(text)


async def run():
    server = Server("claria-cotizador")

    @server.list_tools()
    async def list_tools():
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result = await call_rpc(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="claria-cotizador",
                server_version="1.0.0",
                capabilities=server.get_capabilities(notification_options=None, experimental_capabilities={}),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run())
