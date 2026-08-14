"""OAuth 2.1 + PKCE server for MCP authentication."""
import secrets
import hashlib
import base64
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlparse
from fastapi import APIRouter, HTTPException, Request, Form, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from supabase import create_client
from app.config import settings
from app.services.supabase import ejecutar_maybe_single

router = APIRouter(prefix="/api/mcp/oauth", tags=["mcp-oauth"])

SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)
VALID_SCOPES = {
    "jobs:read", "jobs:write", "projects:write", "documents:write",
    "lists:read", "lists:write", "quotes:read", "quotes:write",
    "suppliers:read", "suppliers:write", "suppliers:block", "suppliers:merge",
    "rfq:read", "rfq:write", "rfq:send", "mail:read", "mail:sync", "mail:send",
    "approvals:read", "approvals:request", "approvals:decide",
    "po:read", "po:write", "po:send", "invoices:read", "invoices:write",
    "invoices:pay", "reports:read", "reports:write", "analytics:read", "data:read",
}
DEFAULT_SCOPES = ["lists:read", "quotes:read", "suppliers:read", "jobs:read", "data:read"]
PKCE_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")

# El estado del flujo OAuth vive en Supabase (migración 032), NO en un dict
# en memoria del proceso — Railway corre el backend con más de un
# worker/instancia, así que un GET /authorize (guarda el estado pendiente) y
# el POST /consent que lo confirma pueden caer en procesos sin memoria
# compartida. Bug real encontrado conectando Claude Desktop en producción:
# "Estado de autorización inválido o expirado" pese a que el usuario hizo
# todo bien. Mismo motivo para mcp_registered_clients (RFC 7591).

def _guardar_estado(key: str, data: dict, ttl_minutos: int = 15) -> None:
    expira = (datetime.utcnow() + timedelta(minutes=ttl_minutos)).isoformat()
    SUPABASE.table("mcp_auth_codes").upsert({
        "key": key, "data": data, "expires_at": expira,
    }).execute()


def _leer_y_consumir_estado(key: str) -> Optional[dict]:
    """Lee y borra en el mismo paso (equivalente a dict.pop) — un código de
    autorización de un solo uso no debe poder reutilizarse.

    Esta versión del SDK de Supabase devuelve `None` directamente (no un
    objeto con `.data = None`) cuando `maybe_single()` no encuentra filas —
    acceder a `.data` sobre eso tira AttributeError en vez de dar un
    resultado vacío. Mismo comportamiento ya documentado en rfq.py."""
    respuesta = SUPABASE.rpc("mcp_consume_auth_code", {"p_key": key}).execute()
    return respuesta.data or None


def _leer_estado_vigente(key: str) -> Optional[dict]:
    """Previsualiza un estado sin consumirlo.

    El consentimiento lo consume sólo después de autenticar al usuario, para
    que una contraseña mal escrita no invalide todo el flujo OAuth.
    """
    response = ejecutar_maybe_single(
        SUPABASE.table("mcp_auth_codes").select("data")
        .eq("key", key).is_("consumed_at", "null")
        .gt("expires_at", datetime.now(timezone.utc).isoformat()).maybe_single()
    )
    return (response.data or {}).get("data") if response.data else None


def _redirect_uri_valida(uri: str) -> bool:
    try:
        parsed = urlparse(uri)
    except Exception:
        return False
    if parsed.fragment or parsed.username or parsed.password:
        return False
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _cliente(client_id: str) -> Optional[dict]:
    response = ejecutar_maybe_single(
        SUPABASE.table("mcp_registered_clients").select("*").eq("client_id", client_id).maybe_single()
    )
    return response.data


def _validar_scopes(scope: str) -> list[str]:
    scopes = list(dict.fromkeys(scope.split())) if scope.strip() else list(DEFAULT_SCOPES)
    if any(item not in VALID_SCOPES for item in scopes):
        raise HTTPException(400, detail={"error": "invalid_scope"})
    return scopes


@router.post("/register")
async def registrar_cliente(body: dict = Body(...)):
    """Dynamic Client Registration (RFC 7591). Cliente público (PKCE, sin
    secret) — cualquier MCP client que implemente el flujo estándar puede
    registrarse solo, sin que el usuario tenga que inventar un client_id
    a mano."""
    redirect_uris = body.get("redirect_uris") or []
    if not redirect_uris or len(redirect_uris) > 10 or not all(isinstance(uri, str) and _redirect_uri_valida(uri) for uri in redirect_uris):
        raise HTTPException(400, detail={"error": "invalid_client_metadata", "error_description": "redirect_uris es requerido"})

    client_id = secrets.token_urlsafe(16)
    client_name = body.get("client_name", "MCP Client")
    if not isinstance(client_name, str) or not 1 <= len(client_name) <= 120:
        raise HTTPException(400, detail={"error": "invalid_client_metadata"})
    grant_types = body.get("grant_types", ["authorization_code", "refresh_token"])
    response_types = body.get("response_types", ["code"])
    if not set(grant_types).issubset({"authorization_code", "refresh_token"}) or response_types != ["code"]:
        raise HTTPException(400, detail={"error": "invalid_client_metadata"})

    SUPABASE.table("mcp_registered_clients").insert({
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "grant_types": grant_types,
        "response_types": response_types,
        "token_endpoint_auth_method": "none",  # cliente público, PKCE obligatorio
    }).execute()

    return JSONResponse({
        "client_id": client_id,
        "client_id_issued_at": int(datetime.utcnow().timestamp()),
        "redirect_uris": redirect_uris,
        "grant_types": grant_types,
        "response_types": response_types,
        "token_endpoint_auth_method": "none",
        "client_name": client_name,
    }, status_code=201)


def verify_mcp_token(token: str) -> Optional[dict]:
    from app.mcp.token_service import load_token
    row = load_token(token, "access")
    if not row or row.get("resource") != settings.mcp_resource_url:
        return None
    return {"sub": row["user_id"], "client_id": row["client_id"], "scopes": row.get("scopes") or [], "resource": row["resource"]}


@router.get("/authorize", response_class=HTMLResponse)
async def authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query(...),
    scope: str = Query(""),
    state: str = Query(""),
    code_challenge: str = Query(""),
    code_challenge_method: str = Query("S256"),
    resource: str = Query(""),
):
    """OAuth 2.1 authorization endpoint — renders consent page."""
    if response_type != "code":
        raise HTTPException(400, "Only code flow supported")
    if not 8 <= len(state) <= 512 or not PKCE_RE.fullmatch(code_challenge) or code_challenge_method != "S256":
        raise HTTPException(400, detail={"error": "invalid_request", "error_description": "state y PKCE S256 son obligatorios"})
    client = _cliente(client_id)
    if not client or redirect_uri not in (client.get("redirect_uris") or []):
        raise HTTPException(400, detail={"error": "invalid_client"})
    if not resource or resource.rstrip("/") != settings.mcp_resource_url.rstrip("/"):
        raise HTTPException(400, detail={"error": "invalid_target"})
    scopes = _validar_scopes(scope)

    # Estado pendiente, compartido entre procesos vía Supabase (ver nota
    # arriba de _guardar_estado).
    _guardar_estado(f"pending_{state}", {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "resource": settings.mcp_resource_url,
    })

    scopes_display = {
        "read": "Leer cotizaciones, proveedores y estadisticas",
        "write": "Crear cotizaciones, OCs y recurrencias",
        "admin": "Acceso completo incluyendo configuracion",
    }
    scope_desc = ", ".join(scopes)
    safe_client_id = html.escape(client.get("client_name") or client_id)
    safe_scope = html.escape(" ".join(scopes))
    safe_scope_desc = html.escape(scope_desc)
    safe_state = html.escape(state, quote=True)
    cancel_url = html.escape(redirect_uri + "?" + urlencode({"error": "access_denied", "state": state}), quote=True)

    consent_page = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Baiyer — Autorizar acceso MCP</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #060610; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
    .card {{ background: #0a0a18; border: 1px solid #1a1a2e; border-radius: 12px; padding: 32px; max-width: 440px; width: 100%; margin: 20px; }}
    .logo {{ font-size: 22px; font-weight: 800; color: #6366f1; margin-bottom: 4px; }}
    .subtitle {{ font-size: 11px; color: #475569; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 24px; }}
    h2 {{ font-size: 16px; color: #f1f5f9; margin-bottom: 8px; }}
    .client {{ font-size: 13px; color: #94a3b8; margin-bottom: 20px; }}
    .scope-box {{ background: #060610; border: 1px solid #1a1a2e; border-radius: 8px; padding: 12px 16px; margin-bottom: 24px; }}
    .scope-label {{ font-size: 9px; color: #475569; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }}
    .scope-desc {{ font-size: 12px; color: #94a3b8; }}
    .scope-badge {{ display: inline-block; background: #6366f122; color: #6366f1; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 700; margin-bottom: 8px; }}
    form {{ display: flex; flex-direction: column; gap: 10px; }}
    input[type=text], input[type=password] {{ background: #060610; border: 1px solid #1a1a2e; border-radius: 6px; padding: 10px 12px; color: #f1f5f9; font-size: 12px; font-family: inherit; outline: none; }}
    input::placeholder {{ color: #334155; }}
    input:focus {{ border-color: #6366f1; }}
    .btn-allow {{ background: #6366f1; color: #fff; border: none; border-radius: 6px; padding: 12px; font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; }}
    .btn-deny {{ background: none; color: #475569; border: 1px solid #1a1a2e; border-radius: 6px; padding: 12px; font-size: 12px; cursor: pointer; font-family: inherit; text-decoration: none; display: block; text-align: center; }}
    .warning {{ font-size: 10px; color: #475569; text-align: center; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">Baiyer</div>
    <div class="subtitle">Cotizador Inteligente</div>
    <h2>Autorizar acceso MCP</h2>
    <p class="client">La aplicación <strong style="color:#f1f5f9">{safe_client_id}</strong> solicita acceso a tu cuenta Baiyer.</p>
    <div class="scope-box">
      <div class="scope-label">Permisos solicitados</div>
      <div class="scope-badge">{safe_scope}</div>
      <div class="scope-desc">{safe_scope_desc}</div>
    </div>
    <form method="post" action="/api/mcp/oauth/consent">
      <input type="hidden" name="state" value="{safe_state}">
      <input type="email" name="email" placeholder="Email de tu cuenta Baiyer" autocomplete="email" required>
      <input type="password" name="password" placeholder="Contrasena" autocomplete="current-password" required>
      <button type="submit" name="action" value="allow" class="btn-allow">Autorizar acceso</button>
      <a href="{cancel_url}" class="btn-deny">Cancelar</a>
    </form>
    <p class="warning">Solo autoriza aplicaciones de confianza. Puedes revocar el acceso en Integraciones.</p>
  </div>
</body>
</html>"""
    return HTMLResponse(consent_page)


@router.post("/consent")
async def consent(
    state: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    action: str = Form("allow"),
):
    """Process user consent and issue auth code."""
    pending_key = f"pending_{state}"
    pending = _leer_estado_vigente(pending_key)
    if not pending:
        raise HTTPException(400, "Estado de autorización inválido o expirado")

    if action != "allow":
        return RedirectResponse(
            pending["redirect_uri"] + "?" + urlencode({"error": "access_denied", "state": state}),
            status_code=302,
        )

    # Authenticate user with Supabase — con un cliente propio, descartable,
    # NO con el `SUPABASE` global de módulo. `sign_in_with_password` muta la
    # sesión interna del cliente que lo llama; si se hace con el cliente
    # compartido, las escrituras posteriores a mcp_auth_codes (más abajo)
    # dejan de correr como service role y quedan bloqueadas por RLS (la
    # tabla no tiene policies para un usuario autenticado normal) — eso
    # tiraba 500 Internal Server Error de forma silenciosa, encontrado
    # probando la conexión real de Claude Desktop en producción.
    try:
        cliente_login = create_client(settings.supabase_url, settings.supabase_service_key)
        auth = cliente_login.auth.sign_in_with_password({"email": email, "password": password})
        user_id = auth.user.id
    except Exception:
        raise HTTPException(401, "Credenciales invalidas")

    # Consumir sólo después de autenticar. La RPC conserva atomicidad y evita
    # que dos submits simultáneos emitan dos códigos para el mismo state.
    pending = _leer_y_consumir_estado(pending_key)
    if not pending:
        raise HTTPException(400, "Estado de autorización inválido o ya utilizado")

    # Generate auth code
    code = secrets.token_urlsafe(32)
    try:
        _guardar_estado(code, {**pending, "user_id": user_id}, ttl_minutos=10)
    except Exception as e:
        print(f"[MCP OAuth] error guardando código emitido: {e}")
        raise HTTPException(500, "No se pudo completar la autorización, intenta de nuevo")

    return RedirectResponse(
        pending["redirect_uri"] + "?" + urlencode({"code": code, "state": state}),
        status_code=302,
    )


@router.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    client_id: str = Form(None),
    code_verifier: str = Form(None),
    refresh_token: str = Form(None),
    resource: str = Form(None),
):
    """Exchange auth code for access token (OAuth 2.1 PKCE)."""
    if grant_type == "authorization_code":
        entry = _leer_y_consumir_estado(code or "")
        if not entry:
            raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Code expired or already used"})

        if client_id != entry.get("client_id") or redirect_uri != entry.get("redirect_uri"):
            raise HTTPException(400, detail={"error": "invalid_grant"})
        if resource != entry.get("resource"):
            raise HTTPException(400, detail={"error": "invalid_target"})
        if not code_verifier:
            raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "code_verifier requerido"})
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if challenge != entry["code_challenge"]:
            raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "PKCE verification failed"})

        user_id = entry["user_id"]
        scopes = entry["scope"].split()
        from app.services.organizacion import obtener_organizacion
        organization_id = obtener_organizacion(user_id)["organizacion_id"]
        from app.mcp.token_service import issue_token_pair
        response = issue_token_pair(user_id, organization_id, client_id, scopes, entry["resource"])

    elif grant_type == "refresh_token":
        from app.mcp.token_service import load_token, rotate_refresh_token
        old = load_token(refresh_token or "", "refresh")
        if not old or (client_id and client_id != old["client_id"]) or (resource and resource != old["resource"]):
            raise HTTPException(400, detail={"error": "invalid_grant"})
        user_id, client_id, scopes = old["user_id"], old["client_id"], old.get("scopes") or []
        response = rotate_refresh_token(refresh_token or "")
        if not response:
            raise HTTPException(400, detail={"error": "invalid_grant"})
    else:
        raise HTTPException(400, detail={"error": "unsupported_grant_type"})

    # Persist connection summary without storing raw credentials.
    try:
        access_token = response["access_token"]
        SUPABASE.table("mcp_connections").upsert({
            "user_id": user_id,
            "client_id": client_id,
            "scopes": scopes,
            "token_hash": hashlib.sha256(access_token.encode()).hexdigest()[:16],
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,client_id").execute()
    except Exception:
        pass  # Don't fail token exchange if DB write fails

    return JSONResponse(response)


@router.get("/userinfo")
async def userinfo(request: Request):
    """Return user info for the authenticated MCP token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing token")

    payload = verify_mcp_token(auth_header[7:])
    if not payload:
        raise HTTPException(401, "Invalid token")

    try:
        user = SUPABASE.auth.admin.get_user_by_id(payload["sub"])
        return {
            "sub": payload["sub"],
            "email": user.user.email,
            "empresa": user.user.user_metadata.get("empresa", user.user.email),
            "plan": user.user.user_metadata.get("plan", "free"),
            "scopes": payload.get("scopes", []),
        }
    except Exception:
        return {"sub": payload["sub"], "scopes": payload.get("scopes", [])}


@router.post("/revoke")
async def revoke(token: str = Form(...), client_id: str = Form(None)):
    """RFC 7009: revoca la familia completa sin revelar si existía."""
    from app.mcp.token_service import load_token, revoke_token
    row = load_token(token, "access") or load_token(token, "refresh")
    if row and (not client_id or client_id == row["client_id"]):
        revoke_token(token)
        try:
            SUPABASE.table("mcp_connections").delete().eq("user_id", row["user_id"]).eq("client_id", row["client_id"]).execute()
        except Exception:
            pass
    return JSONResponse({}, status_code=200)
