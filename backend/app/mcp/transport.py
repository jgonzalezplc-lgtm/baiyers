"""
MCP SSE transport — expone el servidor MCP via HTTP/SSE para clientes remotos.
Compatible con Claude.ai, ChatGPT plugin, y cualquier cliente MCP via HTTP.
"""
import json
import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request, HTTPException, Depends, Body
from fastapi.responses import StreamingResponse, JSONResponse
from mcp.types import (
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
)

from app.mcp.server import TOOLS, TOOL_HANDLERS
from app.mcp.oauth import verify_mcp_token
from supabase import create_client
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp", tags=["mcp"])

SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)


def _get_token_payload(request: Request) -> dict:
    """Extract and verify MCP Bearer token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, detail={"error": "unauthorized", "error_description": "Missing Bearer token"})
    payload = verify_mcp_token(auth[7:])
    if not payload:
        raise HTTPException(401, detail={"error": "invalid_token"})
    return payload


def _audit_log(user_id: str, tool_name: str, params: dict, result: Any):
    """Fire-and-forget audit log to Supabase."""
    try:
        SUPABASE.table("mcp_audit_log").insert({
            "user_id": user_id,
            "tool_name": tool_name,
            "params": json.dumps(params),
            "result_preview": json.dumps(result)[:500] if result else None,
            "called_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass


# ─── Manifest / Discovery ────────────────────────────────────────────────────

@router.get("/manifest.json")
async def manifest():
    """MCP manifest for client discovery."""
    return {
        "schema_version": "v1",
        "name_for_human": "Claria — Cotizador Inteligente",
        "name_for_model": "claria_cotizador",
        "description_for_human": "Cotiza productos, busca proveedores, emite OCs y analiza gastos de procurement en Chile.",
        "description_for_model": (
            "Claria es un sistema de procurement inteligente para empresas chilenas. "
            "Puedes cotizar cualquier item en multiples proveedores, ver historial de precios, "
            "emitir ordenes de compra, crear recurrencias y analizar gastos. "
            "Todos los precios son en CLP (pesos chilenos)."
        ),
        "auth": {
            "type": "oauth",
            "client_url": f"{settings.frontend_url}/mcp/autorizar",
            "scope": "read write",
            "authorization_url": "http://localhost:8000/api/mcp/oauth/authorize",
            "token_url": "http://localhost:8000/api/mcp/oauth/token",
        },
        "api": {
            "type": "openapi",
            "url": "http://localhost:8000/openapi.json",
        },
        "logo_url": f"{settings.frontend_url}/logo.png",
        "contact_email": "hola@claria.cc",
        "legal_info_url": f"{settings.frontend_url}/terminos",
    }


# ─── SSE Endpoint (streaming) ─────────────────────────────────────────────────

@router.get("/sse")
async def mcp_sse(request: Request):
    """
    SSE endpoint for MCP streaming.
    Sends server capabilities and keeps connection alive for tool calls.
    """
    payload = _get_token_payload(request)

    async def event_stream() -> AsyncGenerator[str, None]:
        # Send server info
        server_info = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {
                "serverInfo": {"name": "claria-cotizador", "version": "1.0.0"},
                "capabilities": {"tools": {}},
                "protocolVersion": "2024-11-05",
            }
        }
        yield f"data: {json.dumps(server_info)}\n\n"

        # Send tools list
        tools_msg = {
            "jsonrpc": "2.0",
            "id": "init-tools",
            "result": {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema,
                    }
                    for t in TOOLS
                ]
            }
        }
        yield f"data: {json.dumps(tools_msg)}\n\n"

        # Keep-alive
        while True:
            if await request.is_disconnected():
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── JSON-RPC Endpoint ────────────────────────────────────────────────────────

@router.post("/rpc")
async def mcp_rpc(request: Request, body: dict = Body(...)):
    """
    JSON-RPC 2.0 endpoint for MCP tool calls.
    Clients POST method + params here and get a synchronous response.
    """
    payload = _get_token_payload(request)
    user_id = payload["sub"]
    scopes = payload.get("scopes", [])

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    def ok(result: Any) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def err(code: int, message: str) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}})

    # ── Method routing ──────────────────────────────────────────────────────
    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "claria-cotizador", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        })

    elif method == "tools/list":
        return ok({
            "tools": [
                {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                for t in TOOLS
            ]
        })

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return err(-32602, "Missing tool name")

        # Scope check
        write_tools = {"emitir_oc", "crear_recurrencia", "crear_proyecto"}
        if tool_name in write_tools and "write" not in scopes and "admin" not in scopes:
            return err(-32603, f"Tool '{tool_name}' requires 'write' scope")

        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return err(-32601, f"Tool not found: {tool_name}")

        # Inject user_id
        arguments["user_id"] = user_id

        try:
            result = await handler(**arguments)
            _audit_log(user_id, tool_name, arguments, result)
            return ok({
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            })
        except TypeError as e:
            return err(-32602, f"Invalid parameters: {str(e)}")
        except Exception as e:
            logger.error(f"MCP RPC tool {tool_name} error: {e}")
            return err(-32603, f"Tool execution error: {str(e)}")

    elif method == "notifications/initialized":
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": None})

    elif method == "ping":
        return ok("pong")

    else:
        return err(-32601, f"Method not found: {method}")


# ─── Connections list (UI) ────────────────────────────────────────────────────

@router.get("/connections")
async def list_connections(request: Request):
    """List active MCP connections for the authenticated user."""
    payload = _get_token_payload(request)
    user_id = payload["sub"]

    try:
        resp = SUPABASE.table("mcp_connections").select("*").eq("user_id", user_id).execute()
        connections = resp.data or []
    except Exception:
        connections = []

    return {"connections": connections}


@router.get("/audit")
async def audit_log(request: Request, limit: int = 50):
    """Get recent MCP tool call audit log."""
    payload = _get_token_payload(request)
    user_id = payload["sub"]

    try:
        resp = (
            SUPABASE.table("mcp_audit_log")
            .select("*")
            .eq("user_id", user_id)
            .order("called_at", desc=True)
            .limit(limit)
            .execute()
        )
        logs = resp.data or []
    except Exception:
        logs = []

    return {"logs": logs}
