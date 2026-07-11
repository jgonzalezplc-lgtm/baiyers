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
