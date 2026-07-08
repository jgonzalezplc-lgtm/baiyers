"""Parser de facturas desde Gmail usando Gemini."""
import asyncio
import base64
import json


PALABRAS_FACTURA = ["factura", "invoice", "boleta", "dte", "cobro", "vencimiento", "pagar", "billing"]


async def procesar_email_entrante(message_id: str, user_id: str):
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service
    from app.config import settings
    import google.generativeai as genai

    sb = get_supabase()

    gmail_res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").single().execute()
    if not gmail_res.data:
        return None

    integration = gmail_res.data

    # Verificar no duplicada antes de procesar
    dup = sb.table("facturas").select("id").eq("email_message_id", message_id).execute()
    if dup.data:
        return None

    try:
        service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    except Exception as e:
        print(f"[Facturas] Error descargando email {message_id}: {e}")
        return None

    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("Subject", "")
    from_email = headers.get("From", "")

    # Extraer cuerpo
    body_text = _extract_body(msg["payload"])

    # Filtrar rápido antes de llamar a Gemini
    contenido = (subject + " " + body_text).lower()
    if not any(p in contenido for p in PALABRAS_FACTURA):
        return None

    # Analizar con Gemini
    if not settings.gemini_api_key:
        return None

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""Analiza este email y extrae datos de factura en JSON (SOLO JSON sin markdown):
{{
  "es_factura": true,
  "proveedor_nombre": "string",
  "numero_factura": "string o null",
  "fecha_factura": "YYYY-MM-DD o null",
  "fecha_vencimiento": "YYYY-MM-DD o null",
  "monto_neto": number o null,
  "iva": number o null,
  "monto_total": number o null,
  "moneda": "CLP"
}}

Si el email NO es una factura o cobro, responde: {{"es_factura": false}}

Asunto: {subject}
De: {from_email}
Cuerpo: {body_text[:3000]}"""

    try:
        response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=20.0)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
    except Exception as e:
        print(f"[Facturas] Error Gemini: {e}")
        return None

    if not data.get("es_factura"):
        return None

    # Buscar proveedor_id por nombre
    proveedor_id = None
    nombre_proveedor = data.get("proveedor_nombre") or from_email.split("<")[0].strip()
    if nombre_proveedor:
        prov_res = sb.table("proveedores").select("id").eq("user_id", user_id).ilike("nombre", f"%{nombre_proveedor[:50]}%").limit(1).execute()
        if prov_res.data:
            proveedor_id = prov_res.data[0]["id"]

    # Guardar factura
    factura_row = {
        "user_id": user_id,
        "proveedor_id": proveedor_id,
        "proveedor_nombre": nombre_proveedor[:200],
        "numero_factura": data.get("numero_factura"),
        "fecha_factura": data.get("fecha_factura"),
        "fecha_vencimiento": data.get("fecha_vencimiento"),
        "monto_neto": data.get("monto_neto"),
        "iva": data.get("iva"),
        "monto_total": data.get("monto_total") or 0,
        "moneda": data.get("moneda", "CLP"),
        "estado": "pendiente",
        "email_message_id": message_id,
    }

    try:
        sb.table("facturas").insert(factura_row).execute()
    except Exception as e:
        print(f"[Facturas] Error guardando factura: {e}")
        return None

    # Notificar al usuario
    try:
        from app.services.gmail_service import send_email
        monto = data.get("monto_total", 0) or 0
        monto_fmt = f"${int(monto):,}".replace(",", ".")
        send_email(
            service=service,
            to=integration["email"],
            subject=f"Nueva factura de {nombre_proveedor} — {monto_fmt} {data.get('moneda','CLP')}",
            body=(
                f"Se detectó una nueva factura en tu inbox:\n\n"
                f"Proveedor: {nombre_proveedor}\n"
                f"N° Factura: {data.get('numero_factura', 'N/A')}\n"
                f"Monto total: {monto_fmt} {data.get('moneda','CLP')}\n"
                f"Vencimiento: {data.get('fecha_vencimiento', 'No especificado')}\n\n"
                f"Ver en: {settings.frontend_url}/facturas"
            ),
            from_email=integration["email"],
        )
    except Exception as e:
        print(f"[Facturas] Error notificando: {e}")

    print(f"[Facturas] Nueva factura de {nombre_proveedor} — ${monto_fmt}")
    return data


def _extract_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        try:
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        except Exception:
            pass
    for part in payload.get("parts", []):
        if part.get("mimeType") in ("text/plain", "text/html"):
            if part.get("body", {}).get("data"):
                try:
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                except Exception:
                    pass
        # Recursión para partes anidadas
        nested = _extract_body(part)
        if nested:
            return nested
    return ""


async def scan_inbox(user_id: str, max_emails: int = 20) -> int:
    """Escanea inbox buscando facturas no procesadas. Retorna cantidad encontrada."""
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service

    sb = get_supabase()
    gmail_res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").single().execute()
    if not gmail_res.data:
        return 0

    integration = gmail_res.data
    try:
        service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
        results = service.users().messages().list(
            userId="me",
            q="subject:(factura OR invoice OR boleta OR cobro OR DTE) newer_than:30d",
            maxResults=max_emails,
        ).execute()
        messages = results.get("messages", [])
    except Exception as e:
        print(f"[Facturas] Error listando inbox: {e}")
        return 0

    encontradas = 0
    for msg_ref in messages:
        result = await procesar_email_entrante(msg_ref["id"], user_id)
        if result:
            encontradas += 1

    return encontradas
