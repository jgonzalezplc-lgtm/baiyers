"""
Metadata de descubrimiento OAuth para clientes MCP reales (RFC 8414 +
RFC 9728). Sin esto, un cliente MCP estándar (Claude, etc.) no encuentra
los endpoints de autorización/token/registro y cae a flujos manuales
improvisados — eso fue justo lo que rompió la conexión antes de agregar
esto: sin `registration_endpoint` publicado, no hay forma de que el
cliente sepa que existe `/api/mcp/oauth/register`.

Vive en la raíz del dominio (`/.well-known/...`), fuera del prefijo
`/api/mcp` — así lo exige el estándar, los clientes lo piden ahí directo.
"""
from fastapi import APIRouter, Request

router = APIRouter(tags=["mcp-discovery"])


def _base(request: Request) -> str:
    """URL base real de la request (protocolo + host), nunca hardcodeada —
    el manifest.json legado tenía `localhost:8000` fijo y por eso apuntaba
    mal en producción."""
    return str(request.base_url).rstrip("/")


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata(request: Request):
    base = _base(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/api/mcp/oauth/authorize",
        "token_endpoint": f"{base}/api/mcp/oauth/token",
        "registration_endpoint": f"{base}/api/mcp/oauth/register",
        "userinfo_endpoint": f"{base}/api/mcp/oauth/userinfo",
        "revocation_endpoint": f"{base}/api/mcp/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["read", "write", "admin"],
    }


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata(request: Request):
    base = _base(request)
    return {
        "resource": f"{base}/api/mcp/sse",
        "authorization_servers": [base],
    }
