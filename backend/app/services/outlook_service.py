"""
Capa de transporte del agente de Outlook, equivalente a `gmail_service.py`
pero contra Microsoft Graph REST vía httpx (no hay SDK oficial instalado).
Deliberadamente NO comparte código con `gmail_service.py` — es una copia
paralela para no arriesgar el flujo de Gmail que ya está en producción.

Notas de Graph que no son obvias:
- `POST /me/sendMail` responde 202 Accepted SIN cuerpo — no devuelve el
  mensaje creado. Para poder trackear el hilo (equivalente a `threadId` de
  Gmail, acá `conversationId`) hay que ir a buscarlo después a la carpeta
  "Sent Items".
- `POST /me/messages/{id}/reply` también responde 202/204 sin cuerpo —
  mismo problema, mismo remedio.
- No existe un concepto de headers RFC crudos expuestos fácilmente vía
  Graph; el JSON de cada mensaje ya trae `from`/`toRecipients` estructurados.
"""
import html as _html
import re
from typing import Optional

import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


# ─── Tokens ─────────────────────────────────────────────────────────────────

def refrescar_tokens(refresh_token: str) -> dict:
    """Renueva el access_token contra Microsoft. Devuelve el dict crudo de
    la respuesta de token (con al menos `access_token`, y `refresh_token`
    sólo si Microsoft decidió rotarlo)."""
    from app.config import settings

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"No se pudo refrescar el token de Microsoft: {resp.text}")
    return resp.json()


def get_valid_access_token(access_token: str, refresh_token: str, user_id: str, sb) -> str:
    """Prueba el access_token actual con una llamada barata (`/me`); si Graph
    devuelve 401 (vencido), lo refresca y persiste el nuevo valor en
    `user_integrations` antes de devolverlo. `sb` es el cliente de Supabase
    ya inicializado (se recibe en vez de importarlo acá para evitar import
    circular con `app.services.supabase`)."""
    probe = httpx.get(
        f"{GRAPH_BASE}/me",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"$select": "id"},
        timeout=15.0,
    )
    if probe.status_code != 401:
        return access_token

    nuevos = refrescar_tokens(refresh_token)
    nuevo_access = nuevos.get("access_token")
    if not nuevo_access:
        raise RuntimeError("Microsoft no devolvió access_token al refrescar")

    cambios = {"access_token": nuevo_access}
    if nuevos.get("refresh_token"):
        cambios["refresh_token"] = nuevos["refresh_token"]
    sb.table("user_integrations").update(cambios).eq("user_id", user_id).eq("provider", "outlook").execute()
    return nuevo_access


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


# ─── Envío ──────────────────────────────────────────────────────────────────

def _ultimo_enviado(access_token: str) -> Optional[dict]:
    """Busca el mensaje más reciente en "Sent Items" — usado tras `sendMail`/
    `reply` (ambos responden sin cuerpo) para recuperar `id`/`conversationId`
    del mensaje que se acaba de enviar."""
    resp = httpx.get(
        f"{GRAPH_BASE}/me/mailFolders/sentitems/messages",
        headers=_headers(access_token),
        params={
            "$top": "1",
            "$orderby": "sentDateTime desc",
            "$select": "id,conversationId,subject,sentDateTime",
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        return None
    valores = resp.json().get("value", [])
    return valores[0] if valores else None


def send_email(access_token: str, to: str, subject: str, body: str, from_email: str = None) -> dict:
    """Envía un correo nuevo (`POST /me/sendMail`, 202 sin cuerpo) y luego
    recupera `id`/`conversationId` desde "Sent Items" para poder trackear el
    hilo. `from_email` no se usa para nada en Graph (siempre envía desde la
    cuenta autenticada) — se mantiene el parámetro por paridad de firma con
    `gmail_service.send_email`."""
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    resp = httpx.post(f"{GRAPH_BASE}/me/sendMail", headers=_headers(access_token), json=payload, timeout=30.0)
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"Error enviando correo por Outlook: {resp.status_code} {resp.text}")

    enviado = _ultimo_enviado(access_token)
    return {
        "id": (enviado or {}).get("id"),
        "conversationId": (enviado or {}).get("conversationId"),
    }


def send_email_threaded(
    access_token: str, to: str, subject: str, body: str, from_email: str,
    conversation_id: str, in_reply_to_message_id: str | None = None,
) -> dict:
    """Responde dentro de un hilo existente. Camino confiable con Graph:
    `POST /me/messages/{message_id}/reply` si se tiene el id del último
    mensaje del hilo. Si no se tiene, cae a `send_email` normal con el
    subject prefijado "RE:" (mismo patrón de fallback que
    `gmail_service.send_email_threaded` usa con `threadId`)."""
    if not in_reply_to_message_id:
        asunto = subject if subject.lower().startswith("re:") else f"RE: {subject}"
        return send_email(access_token, to, asunto, body, from_email)

    resp = httpx.post(
        f"{GRAPH_BASE}/me/messages/{in_reply_to_message_id}/reply",
        headers=_headers(access_token),
        json={"comment": body},
        timeout=30.0,
    )
    if resp.status_code not in (200, 202, 204):
        # El mensaje al que se intentaba responder puede haber sido movido o
        # el id venía vencido — mismo fallback que si nunca hubiéramos tenido
        # in_reply_to_message_id: no perder el envío por eso.
        asunto = subject if subject.lower().startswith("re:") else f"RE: {subject}"
        return send_email(access_token, to, asunto, body, from_email)

    # `reply` tampoco devuelve el cuerpo del mensaje creado (202/204) — se
    # recupera igual que en send_email, buscando en Sent Items.
    enviado = _ultimo_enviado(access_token)
    return {
        "id": (enviado or {}).get("id"),
        "conversationId": (enviado or {}).get("conversationId") or conversation_id,
    }


# ─── Lectura de hilos ───────────────────────────────────────────────────────

def listar_mensajes_thread(access_token: str, conversation_id: str) -> list[dict]:
    """Todos los mensajes de un hilo (conversationId de Graph), en orden
    cronológico, con adjuntos ya expandidos."""
    resp = httpx.get(
        f"{GRAPH_BASE}/me/messages",
        headers=_headers(access_token),
        params={
            "$filter": f"conversationId eq '{conversation_id}'",
            "$orderby": "receivedDateTime asc",
            "$select": "id,conversationId,subject,from,toRecipients,body,bodyPreview,receivedDateTime,sentDateTime,hasAttachments",
            "$expand": "attachments($select=id,name,contentType,size)",
        },
        timeout=30.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Error listando mensajes del hilo de Outlook: {resp.status_code} {resp.text}")
    return resp.json().get("value", [])


# ─── Extracción de contenido ────────────────────────────────────────────────

def extraer_texto_plano(mensaje_graph: dict) -> str:
    """`body.contentType` es 'text' o 'html'. Si es html, se despoja a texto
    plano con una limpieza simple de regex (no hace falta un parser HTML
    pesado sólo para esto) + unescape de entities."""
    body = mensaje_graph.get("body") or {}
    contenido = body.get("content") or ""
    tipo = (body.get("contentType") or "text").lower()
    if tipo != "html":
        return contenido.strip()

    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(contenido, "html.parser").get_text(separator="\n").strip()
    except Exception:
        texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", contenido, flags=re.IGNORECASE | re.DOTALL)
        texto = re.sub(r"<[^>]+>", " ", texto)
        texto = _html.unescape(texto)
        return re.sub(r"[ \t]+", " ", texto).strip()


def extraer_adjuntos_meta(mensaje_graph: dict) -> list[dict]:
    adjuntos = []
    for a in mensaje_graph.get("attachments", []) or []:
        adjuntos.append({
            "filename": a.get("name"),
            "mime_type": a.get("contentType"),
            "attachment_id": a.get("id"),
            "size": a.get("size"),
        })
    return adjuntos


def headers_de(mensaje_graph: dict) -> dict:
    """No hay headers RFC crudos expuestos por Graph de forma simple — se
    arma un dict compatible con lo que el resto del agente espera
    (`From`/`To`/`Subject`), a partir del JSON estructurado de Graph."""
    remitente = ((mensaje_graph.get("from") or {}).get("emailAddress") or {})
    destinatarios = mensaje_graph.get("toRecipients") or []
    to_emails = ", ".join(
        (d.get("emailAddress") or {}).get("address", "") for d in destinatarios
    )
    return {
        "From": remitente.get("address", ""),
        "To": to_emails,
        "Subject": mensaje_graph.get("subject", "") or "",
    }


def es_enviado_por_mi(mensaje_graph: dict, mi_email: str) -> bool:
    """Graph no tiene un label 'SENT' como Gmail — se usa la dirección del
    remitente como criterio (mismo fallback que ya usa gmail.py cuando no
    hay labels)."""
    remitente = ((mensaje_graph.get("from") or {}).get("emailAddress") or {}).get("address", "")
    return bool(mi_email) and mi_email.lower() == (remitente or "").lower()
