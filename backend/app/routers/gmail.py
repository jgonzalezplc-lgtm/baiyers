import asyncio
import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/gmail", tags=["gmail"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "credentials.json",
)


# ─── OAuth ────────────────────────────────────────────────────────────────────

def _make_code_verifier() -> str:
    return secrets.token_urlsafe(48)

def _make_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

def _encode_state(user_id: str, verifier: str) -> str:
    payload = f"{user_id}:{verifier}"
    return base64.urlsafe_b64encode(payload.encode()).decode()

def _decode_state(state: str) -> tuple[str, str]:
    payload = base64.urlsafe_b64decode(state + "==").decode()
    user_id, verifier = payload.split(":", 1)
    return user_id, verifier


@router.get("/auth")
async def gmail_auth(user_id: str):
    """Redirige al usuario a Google OAuth con PKCE."""
    from app.config import settings

    if not os.path.exists(CREDENTIALS_PATH):
        raise HTTPException(status_code=500, detail="credentials.json no encontrado en backend/app/")

    with open(CREDENTIALS_PATH) as f:
        creds_data = json.load(f)
    client_info = creds_data.get("web") or creds_data.get("installed") or {}
    client_id = client_info["client_id"]

    verifier = _make_code_verifier()
    challenge = _make_code_challenge(verifier)
    state = _encode_state(user_id, verifier)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": settings.google_redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    from urllib.parse import urlencode
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def gmail_callback(code: str, state: str):
    """Recibe código OAuth con PKCE, guarda tokens en Supabase."""
    import httpx
    from app.config import settings
    from app.services.supabase import get_supabase

    try:
        user_id, verifier = _decode_state(state)
    except Exception:
        raise HTTPException(status_code=400, detail="State inválido")

    with open(CREDENTIALS_PATH) as f:
        creds_data = json.load(f)
    client_info = creds_data.get("web") or creds_data.get("installed") or {}
    client_id = client_info["client_id"]
    client_secret = client_info["client_secret"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error Google token: {resp.text}")

    tokens = resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token:
        raise HTTPException(status_code=500, detail="No se recibio access_token de Google")

    # Obtener el email real de la cuenta conectada
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    gmail_email = "hola@claria.cc"
    if userinfo_resp.status_code == 200:
        gmail_email = userinfo_resp.json().get("email", "hola@claria.cc")

    sb = get_supabase()
    sb.table("user_integrations").upsert(
        {
            "user_id": user_id,
            "provider": "gmail",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email": gmail_email,
        },
        on_conflict="user_id,provider",
    ).execute()

    return RedirectResponse(url=f"{settings.frontend_url}/dashboard?gmail=conectado")


# ─── Generar correo ────────────────────────────────────────────────────────────

class GenerarCorreoRequest(BaseModel):
    nombre_item: str
    specs: Optional[str] = None
    proveedor_nombre: str
    cantidad: str = "1"
    plazo: Optional[str] = None


@router.post("/generar-correo")
async def generar_correo(req: GenerarCorreoRequest):
    from app.config import settings
    import google.generativeai as genai

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no configurada")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""Genera un email profesional en español para solicitar cotizacion de un item industrial.
Datos:
- Item: {req.nombre_item}
- Especificaciones: {req.specs or "segun descripcion"}
- Cantidad: {req.cantidad} unidades
- Plazo requerido: {req.plazo or "a convenir"}
- Proveedor: {req.proveedor_nombre}
- Remitente: hola@claria.cc (empresa de procurement)

Instrucciones: maximo 150 palabras, tono profesional. Solicita precio unitario, disponibilidad, plazo de entrega y condiciones de pago.

Responde SOLO en JSON valido sin markdown:
{{"subject": "string", "body": "string"}}"""

    try:
        response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=20.0)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error Gemini: {str(e)}")


# ─── Enviar correo ─────────────────────────────────────────────────────────────

class EnviarRequest(BaseModel):
    cotizacion_id: str
    resultado_id: Optional[str] = None
    to_email: str
    subject: str
    body: str
    user_id: str
    proveedor_nombre: str = ""


@router.post("/enviar")
async def enviar_correo(req: EnviarRequest):
    from app.config import settings
    from app.services.gmail_service import get_gmail_service, send_email, get_refreshed_tokens
    from app.services.supabase import get_supabase

    sb = get_supabase()

    # Obtener tokens
    res = sb.table("user_integrations").select("*").eq("user_id", req.user_id).eq("provider", "gmail").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Gmail no conectado. Ve al dashboard para conectar tu cuenta.")

    integration = res.data

    try:
        service, creds = get_gmail_service(
            access_token=integration["access_token"],
            refresh_token=integration["refresh_token"],
        )

        # Si el token fue renovado, actualizar en Supabase
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            }).eq("user_id", req.user_id).eq("provider", "gmail").execute()

        # Personalizar cuerpo con nombre del proveedor
        body_final = req.body.replace("{proveedor_nombre}", req.proveedor_nombre)
        subject_final = req.subject.replace("{proveedor_nombre}", req.proveedor_nombre)

        msg = send_email(service, req.to_email, subject_final, body_final, integration["email"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enviando email: {str(e)}")

    # Actualizar resultado en Supabase
    now_iso = datetime.now(timezone.utc).isoformat()
    if req.resultado_id:
        sb.table("resultados").update({
            "solicitud_enviada_at": now_iso,
            "estado": "contactado",
            "proveedor_email": req.to_email,
        }).eq("id", req.resultado_id).execute()
    elif req.cotizacion_id != "demo":
        # Actualizar por cotizacion_id + nombre si no hay resultado_id
        sb.table("resultados").update({
            "solicitud_enviada_at": now_iso,
            "estado": "contactado",
            "proveedor_email": req.to_email,
        }).eq("cotizacion_id", req.cotizacion_id).eq("proveedor_nombre", req.proveedor_nombre[:100]).execute()

    # Supplier Intelligence — registrar solicitud enviada
    try:
        from app.services.supplier_intelligence import registrar_solicitud
        registrar_solicitud(req.user_id, req.proveedor_nombre, req.to_email)
    except Exception as e:
        print(f"[Gmail] SI error: {e}")

    return {"success": True, "message_id": msg.get("id")}


# ─── Sync email (fix para cuentas con email hardcodeado) ──────────────────────

@router.post("/sync-email")
async def sync_gmail_email(user_id: str):
    """Actualiza el email real de la cuenta Gmail conectada."""
    import httpx
    from app.services.supabase import get_supabase

    sb = get_supabase()
    res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Gmail no conectado")

    access_token = res.data["access_token"]
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudo obtener el email de Google. Reconecta Gmail.")

    gmail_email = resp.json().get("email")
    if gmail_email:
        sb.table("user_integrations").update({"email": gmail_email}).eq("user_id", user_id).eq("provider", "gmail").execute()

    return {"email": gmail_email}


# ─── Webhook Pub/Sub ───────────────────────────────────────────────────────────

@router.post("/webhook")
async def gmail_webhook(request: Request):
    """Recibe notificaciones de Gmail vía Pub/Sub (requiere URL pública)."""
    import base64
    from app.services.supabase import get_supabase
    import google.generativeai as genai
    from app.config import settings

    body = await request.json()
    message = body.get("message", {})
    data_b64 = message.get("data", "")

    try:
        decoded = json.loads(base64.b64decode(data_b64).decode())
    except Exception:
        return {"status": "ignored"}

    email_address = decoded.get("emailAddress")
    history_id = decoded.get("historyId")
    print(f"[Gmail webhook] Nueva actividad en {email_address}, historyId: {history_id}")

    return {"status": "received"}


# ─── Check replies (polling para desarrollo) ───────────────────────────────────

@router.get("/check-replies/{cotizacion_id}")
async def check_replies(cotizacion_id: str, user_id: str):
    """Busca manualmente respuestas en Gmail para una cotizacion."""
    from app.services.gmail_service import get_gmail_service
    from app.services.supabase import get_supabase
    import google.generativeai as genai
    from app.config import settings

    sb = get_supabase()
    res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Gmail no conectado")

    integration = res.data
    service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])

    # Buscar emails recientes en inbox con asunto "RE:" o "Cotizacion"
    results = service.users().messages().list(
        userId="me",
        q="subject:(RE: cotizacion OR RE: quotation) newer_than:7d",
        maxResults=10,
    ).execute()

    messages = results.get("messages", [])
    parsed_replies = []

    for msg_ref in messages[:5]:
        try:
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            subject = headers.get("Subject", "")
            from_email = headers.get("From", "")

            # Extraer body del mensaje
            body_text = ""
            payload = msg.get("payload", {})
            if payload.get("body", {}).get("data"):
                body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
            elif payload.get("parts"):
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                        break

            if not body_text:
                continue

            # Parsear con Gemini
            if settings.gemini_api_key:
                genai.configure(api_key=settings.gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                parse_prompt = f"""Del siguiente email de proveedor, extrae en JSON (SOLO JSON sin markdown):
{{"precio_unitario": number|null, "moneda": "CLP|USD|EUR", "disponibilidad": "string", "plazo_entrega": "string", "condiciones_pago": "string"}}

Email:
{body_text[:2000]}"""
                try:
                    response = await asyncio.wait_for(model.generate_content_async(parse_prompt), timeout=20.0)
                    text = response.text.strip()
                    if "```" in text:
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:].strip()
                    data = json.loads(text)
                    data["from"] = from_email
                    data["subject"] = subject
                    data["message_id"] = msg_ref["id"]
                    parsed_replies.append(data)
                except Exception:
                    pass
        except Exception:
            pass

    return {"replies": parsed_replies, "total": len(parsed_replies)}
