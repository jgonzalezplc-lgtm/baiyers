"""Middleware ASGI de auditoría MCP sin registrar argumentos ni respuestas."""
import asyncio
import hashlib
import json
import time
from typing import Any


def _entity(arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    for key, kind in (
        ("list_id", "list"), ("cotizacion_id", "quote"), ("supplier_id", "supplier"),
        ("proveedor_id", "supplier"), ("po_id", "purchase_order"),
        ("invoice_id", "invoice"), ("request_id", "approval"),
        ("conversation_id", "conversation"), ("job_id", "job"), ("draft_id", "draft"),
    ):
        if arguments.get(key): return kind, str(arguments[key])[:200]
    return None, None


def _nivel_de_confirmacion(arguments: dict[str, Any]) -> str:
    """Qué respaldo tuvo la acción, sin inventarle autoridad al modelo.

    Antes acá se escribía `"explicit"` cuando el modelo mandaba `confirmed=true`.
    El problema es que `confirmed` es un argumento que el propio modelo elige:
    la auditoría terminaba certificando "un humano confirmó" sobre la base de un
    booleano que nadie verificó. Con el empleado digital —donde no hay una
    persona leyendo el cliente— eso sería directamente falso, y la regla dura 6
    del PRD pide registrar *qué autorización habilitó* cada acción.

    `asserted_by_model` dice lo único que se sabe de verdad: que el llamador
    afirmó tener confirmación. Cuando F1 traiga la barrera real (elicitation del
    cliente o fila de aprobación persistida), ese caso pasará a `"explicit"` y
    esta función va a poder distinguirlos, que es justo lo que hoy no se puede.
    """
    return "asserted_by_model" if arguments.get("confirmed") is True else "none"


def _record(raw_token: str, payload: dict, status: int, duration_ms: int, rpc_error: bool = False) -> None:
    from app.mcp.token_service import load_token
    from app.services.supabase import get_supabase
    token = load_token(raw_token, "access")
    params = payload.get("params") or {}
    if not token or payload.get("method") != "tools/call": return
    arguments = params.get("arguments") or {}
    entity_type, entity_id = _entity(arguments)
    idem = arguments.get("idempotency_key")
    get_supabase().table("mcp_tool_audit_log").insert({
        "organization_id": token["organization_id"], "actor_user_id": token["user_id"],
        "client_id": token.get("client_id"), "request_id": str(payload.get("id") or "")[:200],
        "tool_name": str(params.get("name") or "unknown")[:200], "scopes": token.get("scopes") or [],
        "entity_type": entity_type, "entity_id": entity_id,
        "idempotency_key_hash": hashlib.sha256(str(idem).encode()).hexdigest() if idem else None,
        "outcome": "success" if status < 400 and not rpc_error else "error", "http_status": status,
        "duration_ms": duration_ms,
        "confirmation_level": _nivel_de_confirmacion(arguments),
    }).execute()


class McpAuditMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST" or scope.get("path") != "/api/mcp":
            return await self.app(scope, receive, send)
        chunks = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body"): break
        body = b"".join(chunks)
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered: return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        status = 500
        response_chunks = []
        async def capture(message):
            nonlocal status
            if message.get("type") == "http.response.start": status = message.get("status", 500)
            if message.get("type") == "http.response.body": response_chunks.append(message.get("body", b""))
            await send(message)
        started = time.perf_counter()
        await self.app(scope, replay, capture)
        try:
            payload = json.loads(body)
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            auth = headers.get("authorization", "")
            raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if raw:
                try: rpc_error = bool(json.loads(b"".join(response_chunks)).get("error"))
                except Exception: rpc_error = False
                await asyncio.to_thread(_record, raw, payload, status, int((time.perf_counter() - started) * 1000), rpc_error)
        except Exception:
            pass
