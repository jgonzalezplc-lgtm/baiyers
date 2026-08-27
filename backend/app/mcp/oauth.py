"""OAuth 2.1 + PKCE server for MCP authentication."""
import secrets
import hashlib
import base64
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlencode, urlparse
from fastapi import APIRouter, HTTPException, Request, Form, Query, Body, Header
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
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
AUTH_REQUEST_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class SessionConsentRequest(BaseModel):
    request_id: str
    action: Literal["allow", "deny"] = "allow"

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


def _url_resultado(redirect_uri: str, parametros: dict[str, str]) -> str:
    """Agrega el resultado OAuth sin romper redirect_uri con query previa."""
    separador = "&" if "?" in redirect_uri else "?"
    return redirect_uri + separador + urlencode(parametros)


def _validar_request_id(request_id: str) -> None:
    if not AUTH_REQUEST_RE.fullmatch(request_id):
        raise HTTPException(400, "Solicitud de autorización inválida o expirada")


def _emitir_codigo(pending: dict, user_id: str) -> str:
    """Emite el código MCP de un solo uso después de verificar al usuario."""
    code = secrets.token_urlsafe(32)
    try:
        _guardar_estado(code, {**pending, "user_id": user_id}, ttl_minutos=10)
    except Exception as e:
        print(f"[MCP OAuth] error guardando código emitido: {e}")
        raise HTTPException(500, "No se pudo completar la autorización, intenta de nuevo")
    return code


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


@router.get("/authorize")
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
    """Valida OAuth 2.1 y deriva el consentimiento a la app de Baiyer.

    La sesión de Supabase vive en el dominio del frontend, por lo que el
    backend no puede reutilizarla desde una página HTML propia. Guardamos la
    solicitud completa bajo un identificador interno de alta entropía y
    enviamos al navegador sólo ese identificador. Así Google, Microsoft y
    email/contraseña terminan en el mismo consentimiento sin exponer
    credenciales al servidor MCP.
    """
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

    # No usamos el `state` que eligió el cliente como clave interna: dos
    # clientes podrían reutilizarlo y pisarse. El request_id es opaco, propio
    # de Baiyer y suficientemente impredecible para viajar por el navegador.
    request_id = secrets.token_urlsafe(32)
    _guardar_estado(f"pending_{request_id}", {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "resource": settings.mcp_resource_url,
    })
    destino = settings.frontend_url.rstrip("/") + "/mcp/autorizar?" + urlencode({"request": request_id})
    return RedirectResponse(destino, status_code=302)


@router.get("/request/{request_id}")
async def authorization_request(request_id: str):
    """Metadata mínima para renderizar el consentimiento en el frontend."""
    _validar_request_id(request_id)
    pending = _leer_estado_vigente(f"pending_{request_id}")
    if not pending:
        raise HTTPException(404, "Solicitud de autorización inválida o expirada")
    client = _cliente(pending["client_id"])
    if not client:
        raise HTTPException(404, "Cliente MCP no disponible")
    return {
        "client_name": client.get("client_name") or "Cliente MCP",
        "scopes": pending.get("scope", "").split(),
    }


@router.post("/consent/session")
async def consent_session(
    body: SessionConsentRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Autoriza usando la sesión Supabase que ya tiene el navegador.

    El token se verifica contra Supabase y nunca se transforma en un token MCP:
    sólo identifica al usuario que recibirá el código OAuth de un solo uso.
    """
    _validar_request_id(body.request_id)
    pending_key = f"pending_{body.request_id}"
    pending = _leer_estado_vigente(pending_key)
    if not pending:
        raise HTTPException(400, "Solicitud de autorización inválida o expirada")

    if body.action == "deny":
        consumed = _leer_y_consumir_estado(pending_key)
        if not consumed:
            raise HTTPException(400, "Solicitud de autorización inválida o ya utilizada")
        return {
            "redirect_url": _url_resultado(
                consumed["redirect_uri"],
                {"error": "access_denied", "state": consumed["state"]},
            )
        }

    from app.services.auth_context import verificar_token

    user_id = verificar_token(authorization)
    # Consumir sólo después de autenticar: un token vencido no invalida el
    # request y el usuario todavía puede volver a iniciar sesión.
    pending = _leer_y_consumir_estado(pending_key)
    if not pending:
        raise HTTPException(400, "Solicitud de autorización inválida o ya utilizada")
    code = _emitir_codigo(pending, user_id)
    return {
        "redirect_url": _url_resultado(
            pending["redirect_uri"],
            {"code": code, "state": pending["state"]},
        )
    }


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
        consumed = _leer_y_consumir_estado(pending_key)
        if not consumed:
            raise HTTPException(400, "Estado de autorización inválido o ya utilizado")
        return RedirectResponse(
            _url_resultado(
                consumed["redirect_uri"],
                {"error": "access_denied", "state": consumed["state"]},
            ),
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

    code = _emitir_codigo(pending, user_id)

    return RedirectResponse(
        _url_resultado(pending["redirect_uri"], {"code": code, "state": pending["state"]}),
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

    # Persist connection summary without storing raw credentials. El verifier
    # también lo hace al usar un token preexistente (backfill automático).
    try:
        from app.mcp.token_service import registrar_conexion
        registrar_conexion(user_id, client_id, scopes, response["access_token"])
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
