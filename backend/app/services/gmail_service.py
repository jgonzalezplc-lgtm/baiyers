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


def _load_client_secrets() -> dict:
    with open(CREDENTIALS_PATH) as f:
        data = json.load(f)
    return data.get("web") or data.get("installed") or {}


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
