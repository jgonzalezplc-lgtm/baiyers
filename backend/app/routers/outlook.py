import base64
import hashlib
import json
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/outlook", tags=["outlook"])

# Permisos delegados de Graph configurados en el registro de la app (Azure AD).
SCOPES = [
    "openid",
    "offline_access",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
]

AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def _make_code_verifier() -> str:
    return secrets.token_urlsafe(48)


def _make_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _next_seguro(next_path: Optional[str]) -> str:
    """Sólo permite redirigir a una ruta relativa propia — nunca a otro host."""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
        return "/dashboard"
    return next_path


def _encode_state(user_id: str, verifier: str, next_path: str = "/dashboard") -> str:
    payload = json.dumps({"u": user_id, "v": verifier, "n": _next_seguro(next_path)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_state(state: str) -> tuple[str, str, str]:
    payload = json.loads(base64.urlsafe_b64decode(state + "==").decode())
    return payload["u"], payload["v"], _next_seguro(payload.get("n"))


@router.get("/auth")
async def outlook_auth(user_id: str, next: str = "/dashboard"):
    """Redirige al usuario a Microsoft OAuth (Graph) con PKCE. `next` es a dónde
    volver en el frontend una vez conectado (ej. /onboarding cuando viene
    encadenado desde el login con Outlook)."""
    from app.config import settings

    if not settings.microsoft_client_id:
        raise HTTPException(status_code=500, detail="MICROSOFT_CLIENT_ID no configurado")

    verifier = _make_code_verifier()
    challenge = _make_code_challenge(verifier)
    state = _encode_state(user_id, verifier, next)

    params = {
        "response_type": "code",
        "client_id": settings.microsoft_client_id,
        "redirect_uri": settings.microsoft_redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    from urllib.parse import urlencode
    return RedirectResponse(url=f"{AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
async def outlook_callback(code: str, state: str):
    """Recibe código OAuth con PKCE, guarda tokens en Supabase."""
    import httpx
    from app.config import settings
    from app.services.supabase import get_supabase

    try:
        user_id, verifier, next_path = _decode_state(state)
    except Exception:
        raise HTTPException(status_code=400, detail="State inválido")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "redirect_uri": settings.microsoft_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
                "scope": " ".join(SCOPES),
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error Microsoft token: {resp.text}")

    tokens = resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token:
        raise HTTPException(status_code=500, detail="No se recibió access_token de Microsoft")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    outlook_email = "hola@claria.cc"
    if userinfo_resp.status_code == 200:
        info = userinfo_resp.json()
        outlook_email = info.get("mail") or info.get("userPrincipalName") or outlook_email

    sb = get_supabase()
    integration = {
        "user_id": user_id,
        "provider": "outlook",
        "access_token": access_token,
        "email": outlook_email,
    }
    # Microsoft puede omitir refresh_token en autorizaciones posteriores. No
    # pisar con null el token persistente que mantiene la integración activa.
    if refresh_token:
        integration["refresh_token"] = refresh_token
    sb.table("user_integrations").upsert(
        integration,
        on_conflict="user_id,provider",
    ).execute()

    separador = "&" if "?" in next_path else "?"
    return RedirectResponse(url=f"{settings.frontend_url}{next_path}{separador}outlook=conectado")


@router.get("/status")
async def outlook_status(ctx: AuthContext = Depends(get_auth_context)):
    """Estado persistente de la integración para la UI del frontend. Mismos 3
    valores de `estado` que `/api/gmail/status`."""
    from app.services.supabase import get_supabase

    sb = get_supabase()
    user_id = ctx.actor_user_id
    result = sb.table("user_integrations").select("refresh_token, email").eq(
        "user_id", user_id
    ).eq("provider", "outlook").limit(1).execute()
    integration = (result.data or [{}])[0]
    conectado = bool(integration.get("refresh_token"))

    if not conectado:
        return {"connected": False, "estado": "desconectado"}

    return {
        "connected": True,
        "estado": "ok",
        "email": integration.get("email"),
    }
