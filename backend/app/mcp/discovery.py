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
from app.config import settings
from app.mcp.oauth import VALID_SCOPES

router = APIRouter(tags=["mcp-discovery"])


def _base(request: Request) -> str:
    """URL base real de la request (protocolo + host), nunca hardcodeada —
    el manifest.json legado tenía `localhost:8000` fijo y por eso apuntaba
    mal en producción.

    Railway termina TLS en un proxy delante de la app: la conexión que
    llega a uvicorn es HTTP plano, así que `request.base_url` por sí solo
    siempre da `http://`, incluso en producción detrás de HTTPS real. Eso
    hacía que el discovery publicara endpoints `http://` — un cliente MCP
    real (Claude) los rechaza por inseguros y el registro dinámico fallaba
    en silencio ("no se pudo registrar"). El proxy sí manda
    `X-Forwarded-Proto: https`, que es la señal correcta a confiar acá.
    """
    base = str(request.base_url).rstrip("/")
    proto_real = request.headers.get("x-forwarded-proto")
    if proto_real and base.startswith("http://"):
        base = proto_real + base[len("http"):]
    return base


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata(request: Request):
    issuer = settings.mcp_issuer_url.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/api/mcp/oauth/authorize",
        "token_endpoint": f"{issuer}/api/mcp/oauth/token",
        "registration_endpoint": f"{issuer}/api/mcp/oauth/register",
        "userinfo_endpoint": f"{issuer}/api/mcp/oauth/userinfo",
        "revocation_endpoint": f"{issuer}/api/mcp/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": sorted(VALID_SCOPES),
        "resource_indicators_supported": True,
    }


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata(request: Request):
    return {
        "resource": settings.mcp_resource_url.rstrip("/"),
        "authorization_servers": [settings.mcp_issuer_url.rstrip("/")],
        "scopes_supported": sorted(VALID_SCOPES),
        "resource_name": "Baiyer Procurement MCP",
    }
