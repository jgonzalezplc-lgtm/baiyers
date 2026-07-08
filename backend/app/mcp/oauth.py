"""OAuth 2.1 + PKCE server for MCP authentication."""
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import jwt
from supabase import create_client
from app.config import settings

router = APIRouter(prefix="/api/mcp/oauth", tags=["mcp-oauth"])

SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)
JWT_SECRET = settings.mcp_jwt_secret
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 30  # 30 days

# In-memory code store (use Redis in production)
_auth_codes: dict[str, dict] = {}


def _generate_token(user_id: str, client_id: str, scopes: list[str]) -> str:
    payload = {
        "sub": user_id,
        "client_id": client_id,
        "scopes": scopes,
        "iat": datetime.utcnow().isoformat(),
        "exp": (datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)).timestamp(),
        "type": "mcp_access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_mcp_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "mcp_access":
            return None
        return payload
    except Exception:
        return None


@router.get("/authorize", response_class=HTMLResponse)
async def authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query(...),
    scope: str = Query("read"),
    state: str = Query(""),
    code_challenge: str = Query(""),
    code_challenge_method: str = Query("S256"),
):
    """OAuth 2.1 authorization endpoint — renders consent page."""
    if response_type != "code":
        raise HTTPException(400, "Only code flow supported")

    # Store params in session-like dict keyed by state
    _auth_codes[f"pending_{state}"] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }

    scopes_display = {
        "read": "Leer cotizaciones, proveedores y estadisticas",
        "write": "Crear cotizaciones, OCs y recurrencias",
        "admin": "Acceso completo incluyendo configuracion",
    }
    scope_desc = scopes_display.get(scope, scope)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Claria — Autorizar acceso MCP</title>
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
    <div class="logo">Claria</div>
    <div class="subtitle">Cotizador Inteligente</div>
    <h2>Autorizar acceso MCP</h2>
    <p class="client">La aplicacion <strong style="color:#f1f5f9">{client_id}</strong> solicita acceso a tu cuenta Claria.</p>
    <div class="scope-box">
      <div class="scope-label">Permisos solicitados</div>
      <div class="scope-badge">{scope}</div>
      <div class="scope-desc">{scope_desc}</div>
    </div>
    <form method="post" action="/api/mcp/oauth/consent">
      <input type="hidden" name="state" value="{state}">
      <input type="text" name="email" placeholder="Email de tu cuenta Claria" autocomplete="email">
      <input type="password" name="password" placeholder="Contrasena">
      <button type="submit" name="action" value="allow" class="btn-allow">Autorizar acceso</button>
      <a href="{redirect_uri}?error=access_denied&state={state}" class="btn-deny">Cancelar</a>
    </form>
    <p class="warning">Solo autoriza aplicaciones de confianza. Puedes revocar el acceso en Integraciones.</p>
  </div>
</body>
</html>"""
    return HTMLResponse(html)


@router.post("/consent")
async def consent(
    state: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    action: str = Form("allow"),
):
    """Process user consent and issue auth code."""
    pending = _auth_codes.pop(f"pending_{state}", None)
    if not pending:
        raise HTTPException(400, "Estado de autorización inválido o expirado")

    if action != "allow":
        return RedirectResponse(
            f"{pending['redirect_uri']}?error=access_denied&state={state}",
            status_code=302,
        )

    # Authenticate user with Supabase
    try:
        auth = SUPABASE.auth.sign_in_with_password({"email": email, "password": password})
        user_id = auth.user.id
    except Exception:
        raise HTTPException(401, "Credenciales invalidas")

    # Generate auth code
    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        **pending,
        "user_id": user_id,
        "expires_at": (datetime.utcnow() + timedelta(minutes=10)).timestamp(),
    }

    return RedirectResponse(
        f"{pending['redirect_uri']}?code={code}&state={state}",
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
):
    """Exchange auth code for access token (OAuth 2.1 PKCE)."""
    if grant_type == "authorization_code":
        entry = _auth_codes.pop(code, None)
        if not entry:
            raise HTTPException(400, detail={"error": "invalid_grant"})

        if datetime.utcnow().timestamp() > entry["expires_at"]:
            raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "Code expired"})

        # Verify PKCE
        if entry.get("code_challenge") and code_verifier:
            digest = hashlib.sha256(code_verifier.encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            if challenge != entry["code_challenge"]:
                raise HTTPException(400, detail={"error": "invalid_grant", "error_description": "PKCE verification failed"})

        user_id = entry["user_id"]
        scopes = entry["scope"].split()

    elif grant_type == "refresh_token":
        # Verify existing token and reissue
        payload = verify_mcp_token(refresh_token or "")
        if not payload:
            raise HTTPException(400, detail={"error": "invalid_grant"})
        user_id = payload["sub"]
        scopes = payload.get("scopes", ["read"])
        client_id = payload.get("client_id", client_id)
    else:
        raise HTTPException(400, detail={"error": "unsupported_grant_type"})

    access_token = _generate_token(user_id, client_id or "unknown", scopes)

    # Persist connection in Supabase
    try:
        SUPABASE.table("mcp_connections").upsert({
            "user_id": user_id,
            "client_id": client_id,
            "scopes": scopes,
            "token_hash": hashlib.sha256(access_token.encode()).hexdigest()[:16],
            "connected_at": datetime.utcnow().isoformat(),
            "last_used_at": datetime.utcnow().isoformat(),
        }, on_conflict="user_id,client_id").execute()
    except Exception:
        pass  # Don't fail token exchange if DB write fails

    return JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_EXPIRE_HOURS * 3600,
        "refresh_token": access_token,  # Same token used for refresh
        "scope": " ".join(scopes),
    })


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


@router.delete("/revoke")
async def revoke(request: Request, client_id: str = Query(...)):
    """Revoke MCP connection."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing token")

    payload = verify_mcp_token(auth_header[7:])
    if not payload:
        raise HTTPException(401, "Invalid token")

    try:
        SUPABASE.table("mcp_connections").delete().eq("user_id", payload["sub"]).eq("client_id", client_id).execute()
    except Exception:
        pass

    return {"revoked": True}
