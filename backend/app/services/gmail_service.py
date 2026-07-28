import base64
import json
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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


def load_client_secrets() -> dict:
    """Credenciales OAuth de Google: primero variables de entorno
    (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, ideal para producción), y si no
    están, el archivo credentials.json (cómodo en local). Único punto de carga
    usado por el router de Gmail y por este servicio."""
    from app.config import settings

    if settings.google_client_id and settings.google_client_secret:
        return {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
        }
    if os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH) as f:
            data = json.load(f)
        return data.get("web") or data.get("installed") or {}
    raise RuntimeError(
        "Credenciales de Google no configuradas: define GOOGLE_CLIENT_ID y "
        "GOOGLE_CLIENT_SECRET, o coloca credentials.json en backend/app/."
    )


# Alias interno para retrocompatibilidad
_load_client_secrets = load_client_secrets


def get_gmail_service(access_token: str, refresh_token: str):
    secrets = _load_client_secrets()
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=secrets["client_id"],
        client_secret=secrets["client_secret"],
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds), creds


def send_email_with_attachment(
    service, to: str, subject: str, body: str, from_email: str,
    pdf_bytes: bytes, pdf_filename: str
) -> dict:
    from email.mime.application import MIMEApplication
    msg = MIMEMultipart("mixed")
    msg["to"] = to
    msg["from"] = from_email
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    msg.attach(pdf_part)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_email(service, to: str, subject: str, body: str, from_email: str) -> dict:
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["from"] = from_email
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_email_threaded(
    service, to: str, subject: str, body: str, from_email: str,
    thread_id: str, in_reply_to_msgid: str | None = None,
) -> dict:
    """Envía dentro de un hilo existente (usado por el agente para
    agradecimientos/seguimientos automáticos). `in_reply_to_msgid` es el
    header Message-ID (RFC) del mensaje al que se responde, no el id interno
    de Gmail — mantiene el threading también en el cliente del proveedor."""
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["from"] = from_email
    msg["subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to_msgid:
        msg["In-Reply-To"] = in_reply_to_msgid
        msg["References"] = in_reply_to_msgid
    msg.attach(MIMEText(body, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw, "threadId": thread_id}).execute()


def extraer_texto_plano(payload: dict) -> str:
    """Extrae el body de texto plano de un mensaje de Gmail (formato 'full'),
    recorriendo las partes MIME si es multipart."""
    def _decode(data: str) -> str:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    if payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])

    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode(part["body"]["data"])
    # Sin texto plano directo: intenta bajar por sub-partes, y como último
    # recurso el html (sin limpiar tags — mejor que perder el contenido).
    for part in payload.get("parts", []) or []:
        if part.get("parts"):
            texto = extraer_texto_plano(part)
            if texto:
                return texto
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return _decode(part["body"]["data"])
    return ""


def extraer_adjuntos_meta(payload: dict) -> list[dict]:
    """Lista los adjuntos de un mensaje (sin descargar el contenido todavía):
    filename, mimeType y attachmentId para pedirlos después con
    `descargar_adjunto`."""
    adjuntos: list[dict] = []

    def _recorrer(parte: dict):
        filename = parte.get("filename")
        body = parte.get("body", {})
        if filename and body.get("attachmentId"):
            adjuntos.append({
                "filename": filename,
                "mime_type": parte.get("mimeType"),
                "attachment_id": body["attachmentId"],
                "size": body.get("size"),
            })
        for sub in parte.get("parts", []) or []:
            _recorrer(sub)

    _recorrer(payload)
    return adjuntos


def descargar_adjunto(service, message_id: str, attachment_id: str) -> bytes:
    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    return base64.urlsafe_b64decode(att["data"])


def listar_mensajes_thread(service, thread_id: str) -> list[dict]:
    """Todos los mensajes (formato 'full') de un hilo de Gmail, en orden cronológico."""
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    return thread.get("messages", [])


def headers_de(msg: dict) -> dict:
    return {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}


def get_refreshed_tokens(access_token: str, refresh_token: str) -> dict:
    """Renueva tokens y retorna los nuevos valores."""
    secrets = _load_client_secrets()
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=secrets["client_id"],
        client_secret=secrets["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return {
        "access_token": creds.token,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
