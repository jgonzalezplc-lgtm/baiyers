import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context
from app.services.item_field_updates import registrar_actualizacion_campo
from app.services.supabase import ejecutar_maybe_single

router = APIRouter(prefix="/api/gmail", tags=["gmail"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ─── OAuth ────────────────────────────────────────────────────────────────────

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

@router.post("/conectar")
async def gmail_conectar(next: str = "/dashboard", ctx: AuthContext = Depends(get_auth_context)):
    """Devuelve la URL de consentimiento de Google para el usuario autenticado.

    Reemplaza al viejo `GET /api/gmail/auth?user_id=...`, que iniciaba el flujo
    sin sesión: con el UUID de otra persona se completaba el consentimiento con
    la cuenta de Google propia y el callback dejaba los tokens del atacante en
    la fila de la víctima (ver `services/oauth_state.py`). El `user_id` sale de
    la sesión verificada, y devolvemos JSON en vez de un redirect porque un
    endpoint autenticado no puede ser el destino de una navegación del browser.
    """
    from app.config import settings
    from app.services.gmail_service import load_client_secrets
    from app.services.oauth_state import firmar_state

    try:
        client_info = load_client_secrets()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    client_id = client_info["client_id"]

    verifier = _make_code_verifier()
    challenge = _make_code_challenge(verifier)
    state = firmar_state(ctx.actor_user_id, verifier, _next_seguro(next))

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
    return {"url": "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)}


@router.get("/callback")
async def gmail_callback(code: str, state: str):
    """Recibe código OAuth con PKCE, guarda tokens en Supabase."""
    import httpx
    from app.config import settings
    from app.services.supabase import get_supabase

    from app.services.oauth_state import verificar_state

    # Este endpoint es público de verdad (lo invoca Google, no el navegador con
    # sesión Baiyer), así que la firma del `state` es lo único que ata este
    # consentimiento al usuario que realmente lo inició.
    datos = verificar_state(state)
    if not datos:
        raise HTTPException(status_code=400, detail="State inválido o expirado")
    user_id, verifier, next_path = datos["u"], datos["v"], _next_seguro(datos.get("n"))

    from app.services.gmail_service import load_client_secrets
    client_info = load_client_secrets()
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
    integration = {
        "user_id": user_id,
        "provider": "gmail",
        "access_token": access_token,
        "email": gmail_email,
    }
    # Google puede omitir refresh_token en autorizaciones posteriores. No
    # pisar con null el token persistente que mantiene Gmail funcionando tras
    # reinicios y deploys.
    if refresh_token:
        integration["refresh_token"] = refresh_token
    sb.table("user_integrations").upsert(
        integration,
        on_conflict="user_id,provider",
    ).execute()
    # Sin esto el dashboard seguiría diciendo "reconexión requerida" hasta 10
    # minutos después de que el usuario ya reconectó.
    from app.services.gmail_service import invalidar_cache_validez
    invalidar_cache_validez(user_id)

    separador = "&" if "?" in next_path else "?"
    return RedirectResponse(url=f"{settings.frontend_url}{next_path}{separador}gmail=conectado")


@router.get("/status")
async def gmail_status(ctx: AuthContext = Depends(get_auth_context)):
    """Estado persistente de la integración para la UI del dashboard. Nunca
    desde `?gmail=conectado` (query param temporal del callback OAuth) — este
    endpoint es la única fuente de verdad.

    `estado` de 3 valores para el indicador del dashboard:
    - "desconectado": no hay refresh_token (no autorizado, o revocado).
    - "atencion": conectado, pero hay conversaciones que requieren revisión
      humana o fallaron — la integración funciona pero algo necesita ojo.
    - "ok": conectado y sin conversaciones pendientes de atención.
    No se expone ningún token."""
    from app.services.supabase import get_supabase

    sb = get_supabase()
    user_id = ctx.actor_user_id
    result = sb.table("user_integrations").select("access_token, refresh_token, email").eq(
        "user_id", user_id
    ).eq("provider", "gmail").limit(1).execute()
    integration = (result.data or [{}])[0]

    if not integration.get("refresh_token"):
        return {"connected": False, "estado": "desconectado", "conversaciones_atencion": 0}

    # Que exista el refresh_token no significa que Google lo acepte. Sin esta
    # verificación una autorización revocada seguía figurando "ok" y el dashboard
    # ni siquiera ofrecía el botón para reconectar (sólo se muestra si `connected`
    # es falso), así que el usuario quedaba encerrado afuera.
    from app.services.gmail_service import verificar_credencial_cacheada

    sirve, motivo = verificar_credencial_cacheada(
        user_id, integration.get("access_token") or "", integration["refresh_token"]
    )
    if not sirve:
        return {
            "connected": False,
            # Distinto de "desconectado": el buzón está configurado y su historial
            # sigue ahí; lo único que caducó es la autorización.
            "estado": "reconexion_requerida",
            "motivo": motivo,
            "conversaciones_atencion": 0,
            "email": integration.get("email"),
        }

    atencion = sb.table("gmail_conversations").select("id", count="exact").eq(
        "user_id", user_id
    ).in_("estado", ["human_review_required", "failed"]).execute()
    n_atencion = atencion.count or 0

    return {
        "connected": True,
        "estado": "atencion" if n_atencion > 0 else "ok",
        "conversaciones_atencion": n_atencion,
        "email": integration.get("email"),
    }


# ─── Generar correo ────────────────────────────────────────────────────────────

class GenerarCorreoRequest(BaseModel):
    nombre_item: str
    specs: Optional[str] = None
    proveedor_nombre: str
    cantidad: str = "1"
    plazo: Optional[str] = None


def _quitar_markdown(texto: str) -> str:
    """Gemini a veces devuelve viñetas/negritas en markdown pese a que se le
    pide texto plano — un correo con asteriscos se nota "hecho por IA". Se
    limpia como red de seguridad además de pedírselo en el prompt."""
    if not texto:
        return texto
    texto = re.sub(r"\*\*(.+?)\*\*", r"\1", texto)
    texto = re.sub(r"__(.+?)__", r"\1", texto)
    texto = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", texto)
    texto = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", texto)
    texto = re.sub(r"^[ \t]*[\*\-•][ \t]+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^#{1,6}[ \t]+", "", texto, flags=re.MULTILINE)
    return texto


@router.post("/generar-correo")
async def generar_correo(req: GenerarCorreoRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.config import settings
    import google.generativeai as genai

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no configurada")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""Genera una PLANTILLA de email profesional en español para solicitar cotización de un ítem.
Datos:
- Item: {req.nombre_item}
- Especificaciones: {req.specs or "según descripción"}
- Cantidad: {req.cantidad} unidades
- Plazo requerido: {req.plazo or "a convenir"}

Instrucciones IMPORTANTES:
- El saludo DEBE usar el marcador literal {{proveedor_nombre}} (ej: "Estimados {{proveedor_nombre}},"). NO inventes ni uses un nombre de proveedor real: se reemplaza automáticamente por cada destinatario.
- NO firmes con un nombre de empresa específico ni pongas un correo remitente: el correo se envía desde la cuenta del propio usuario. Cierra con una despedida neutra (ej: "Quedamos atentos. Saludos cordiales.") sin firma inventada.
- Máximo 150 palabras, tono profesional. Solicita precio unitario, disponibilidad, plazo de entrega y condiciones de pago.
- Si hay especificaciones, menciónalas de forma concreta en el cuerpo (no las resumas como "se adjuntan" o "se compartirán por separado" — inclúyelas tal cual). Si NO hay especificaciones, simplemente no menciones el tema; no inventes que se adjuntan o se enviarán aparte.
- El cuerpo va en texto plano, como lo escribiría una persona a mano: párrafos corridos, sin viñetas ni listas. NO uses markdown de ningún tipo (nada de **negrita**, *cursiva*, guiones ni asteriscos de lista, ni títulos con #). Los datos del ítem (descripción, cantidad) se integran en la redacción, no como lista.

Responde SOLO en JSON válido sin markdown:
{{"subject": "string", "body": "string"}}"""

    try:
        response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=20.0)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()
        datos = json.loads(text)
        datos["subject"] = _quitar_markdown(datos.get("subject", ""))
        datos["body"] = _quitar_markdown(datos.get("body", ""))
        return datos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error Gemini: {str(e)}")


# ─── Enviar correo ─────────────────────────────────────────────────────────────

class EnviarRequest(BaseModel):
    cotizacion_id: str
    resultado_id: Optional[str] = None
    to_email: str
    subject: str
    body: str
    proveedor_nombre: str = ""


@router.post("/enviar")
async def enviar_correo(req: EnviarRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.config import settings
    from app.services.gmail_service import get_gmail_service, send_email, get_refreshed_tokens
    from app.services.supabase import get_supabase

    sb = get_supabase()

    # Obtener tokens
    res = sb.table("user_integrations").select("*").eq("user_id", ctx.actor_user_id).eq("provider", "gmail").single().execute()
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
            }).eq("user_id", ctx.actor_user_id).eq("provider", "gmail").execute()

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
        registrar_solicitud(ctx.actor_user_id, req.proveedor_nombre, req.to_email)
    except Exception as e:
        print(f"[Gmail] SI error: {e}")

    # Agente de Gmail: registra la conversación y el mensaje saliente para
    # poder trackear el hilo y leer las respuestas más adelante. Se engancha
    # al directorio real de proveedores (no crea un registro paralelo) — la
    # ausencia de RUT no bloquea el envío, se completa después si aparece.
    thread_id = msg.get("threadId")
    try:
        from app.services.proveedores_matching import resolver_o_crear_proveedor, resolver_o_crear_contacto
        proveedor_id = resolver_o_crear_proveedor(sb, ctx.actor_user_id, req.proveedor_nombre or req.to_email, req.to_email)
        contacto_id = resolver_o_crear_contacto(sb, ctx.actor_user_id, proveedor_id, req.to_email, origen="gmail_agent")

        conv = sb.table("gmail_conversations").upsert({
            "user_id": ctx.actor_user_id,
            "gmail_thread_id": thread_id,
            "proveedor_id": proveedor_id,
            "contacto_id": contacto_id,
            "proveedor_nombre": req.proveedor_nombre or None,
            "proveedor_email": req.to_email,
            "cotizacion_id": req.cotizacion_id if req.cotizacion_id != "demo" else None,
            "resultado_id": req.resultado_id,
            "subject": subject_final,
            "estado": "sent",
            "last_message_at": now_iso,
        }, on_conflict="user_id,gmail_thread_id").execute()
        conversation_id = conv.data[0]["id"]
        sb.table("gmail_messages").upsert({
            "conversation_id": conversation_id,
            "gmail_message_id": msg.get("id"),
            "gmail_thread_id": thread_id,
            "direction": "outbound",
            "from_email": integration["email"],
            "to_email": req.to_email,
            "subject": subject_final,
            "body_text": body_final,
            "received_at": now_iso,
            "procesado": True,
        }, on_conflict="gmail_message_id").execute()
    except Exception as e:
        # No bloquea el envío si el esquema del agente aún no está migrado.
        print(f"[Gmail] No se pudo registrar la conversación: {e}")

    return {"success": True, "message_id": msg.get("id"), "thread_id": thread_id}


# ─── Sync email (fix para cuentas con email hardcodeado) ──────────────────────

@router.post("/sync-email")
async def sync_gmail_email(ctx: AuthContext = Depends(get_auth_context)):
    """Actualiza el email real de la cuenta Gmail conectada."""
    import httpx
    from app.services.supabase import get_supabase

    user_id = ctx.actor_user_id
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


# ─── Agente de Gmail: sincronizar respuestas ──────────────────────────────────
# Fase 1: sólo lee y PROPONE actualizaciones (item_field_updates.estado='propuesta').
# No envía correos automáticos ni escribe en `resultados` sin que un humano
# apruebe la propuesta vía /propuestas/{id}/aplicar.

_AUTO_REPLY_HINTS = (
    "out of office", "fuera de la oficina", "fuera de oficina", "respuesta automática",
    "automatic reply", "no-reply", "noreply", "vacaciones", "delivery status notification",
    "undelivered mail", "mailer-daemon",
)


def _parece_automatico(subject: str, from_email: str, cuerpo: str) -> bool:
    blob = f"{subject} {from_email} {cuerpo[:300]}".lower()
    return any(h in blob for h in _AUTO_REPLY_HINTS)


def _extraer_email(header_from: str) -> str:
    """'Nombre Apellido <correo@dominio.cl>' → 'correo@dominio.cl' (lower)."""
    m = re.search(r"<([^<>]+)>", header_from)
    email = (m.group(1) if m else header_from).strip().lower()
    return email if "@" in email else ""


def _nombre_cotizacion(sb, cotizacion_id: str) -> str:
    try:
        cot = ejecutar_maybe_single(sb.table("cotizaciones").select("nombre_identificado,descripcion").eq("id", cotizacion_id).maybe_single())
        if cot.data:
            return cot.data.get("nombre_identificado") or cot.data.get("descripcion") or "ítem cotizado"
    except Exception:
        pass
    return "ítem cotizado"


def _nombre_lista(sb, lista_proyecto_id: str | None) -> str | None:
    if not lista_proyecto_id:
        return None
    try:
        proy = ejecutar_maybe_single(sb.table("proyectos").select("nombre").eq("id", lista_proyecto_id).maybe_single())
        return (proy.data or {}).get("nombre")
    except Exception:
        return None


async def _procesar_respuesta_oc(sb, service, conv: dict, mi_email: str, cuerpo: str,
                                 recibido_iso: str, gmail_message_id: str = "") -> str:
    """Respuesta a una OC (conv['oc_id'] presente): a diferencia de una
    cotización, acá no se extraen campos — sólo interesa si el proveedor
    acusó recibo o avisó el despacho. Devuelve el nuevo estado de la
    conversación; el estado de negocio real queda en ordenes_compra."""
    from app.services.email_understanding import clasificar_respuesta_oc
    from app.services import gmail_conversation_agent

    oc = ejecutar_maybe_single(sb.table("ordenes_compra").select("id, estado").eq("id", conv["oc_id"]).maybe_single()).data
    if not oc:
        return "human_review_required"

    clasificacion = await clasificar_respuesta_oc(cuerpo)
    tipo = clasificacion["tipo"]

    if tipo == "acuse_recibo" and oc["estado"] in ("enviada", "borrador"):
        sb.table("ordenes_compra").update({
            "estado": "recibido_conforme", "recibido_conforme_at": recibido_iso,
        }).eq("id", oc["id"]).execute()
        try:
            from app.services.supplier_intelligence import registrar_oc_confirmada, programar_rating
            registrar_oc_confirmada(oc["id"])
            programar_rating(oc["id"])
        except Exception as e:
            print(f"[OC] SI error (acuse por correo): {e}")
        try:
            from app.services.workflow_purchase_order import registrar_acuse_oc
            registrar_acuse_oc(oc["id"], gmail_message_id or recibido_iso)
        except Exception as e:
            print(f"[OC] evento workflow de acuse falló: {e}")
        cuerpo_resp = (
            f"Estimados,\n\nGracias por confirmar la recepción de la orden. "
            f"Quedamos atentos al despacho.\n\nSaludos cordiales."
        )
        gmail_conversation_agent._enviar_y_registrar(sb, service, conv, mi_email, cuerpo_resp, "waiting_for_supplier")
        return "waiting_for_supplier"

    if tipo == "despacho":
        sb.table("ordenes_compra").update({
            "estado": "despachada", "despacho_at": recibido_iso,
            "despacho_detalle": clasificacion.get("detalle"),
        }).eq("id", oc["id"]).execute()
        try:
            from app.services.workflow_purchase_order import registrar_despacho_oc
            registrar_despacho_oc(
                oc["id"], gmail_message_id or recibido_iso, clasificacion.get("detalle") or "",
            )
        except Exception as e:
            print(f"[OC] evento workflow de despacho falló: {e}")
        cuerpo_resp = (
            f"Estimados,\n\nGracias por avisarnos. Quedamos atentos a la llegada del pedido.\n\nSaludos cordiales."
        )
        gmail_conversation_agent._enviar_y_registrar(sb, service, conv, mi_email, cuerpo_resp, "closed")
        return "closed"

    return "human_review_required"


def _items_contexto(sb, conv: dict) -> list[dict]:
    """Ítem(s) sobre los que trata esta conversación, para dárselos como
    contexto al Email Understanding Agent."""
    items = []
    # RFQ agrupada: una conversación representa varios resultados/ítems.
    # Se intenta primero y se tolera que la migración 026 aún no exista.
    try:
        batch = ejecutar_maybe_single(sb.table("rfq_batches").select("id").eq("conversation_id", conv["id"]).maybe_single()).data
        if batch:
            batch_items = sb.table("rfq_batch_items").select("resultado_id,cotizacion_id").eq("rfq_batch_id", batch["id"]).execute().data or []
            for item in batch_items:
                items.append({
                    "entity_id": item["resultado_id"],
                    "nombre": _nombre_cotizacion(sb, item["cotizacion_id"]),
                    "proveedor": conv.get("proveedor_nombre"),
                })
            if items:
                return items
    except Exception:
        pass
    if conv.get("resultado_id"):
        r = ejecutar_maybe_single(sb.table("resultados").select("id,proveedor_nombre,cotizacion_id").eq("id", conv["resultado_id"]).maybe_single())
        if r.data:
            nombre_item = _nombre_cotizacion(sb, r.data["cotizacion_id"])
            items.append({"entity_id": r.data["id"], "nombre": nombre_item, "proveedor": r.data.get("proveedor_nombre")})
    elif conv.get("cotizacion_id"):
        nombre_item = _nombre_cotizacion(sb, conv["cotizacion_id"])
        rs = sb.table("resultados").select("id,proveedor_nombre").eq("cotizacion_id", conv["cotizacion_id"]).eq("proveedor_nombre", conv.get("proveedor_nombre") or "").execute()
        for r in (rs.data or []):
            items.append({"entity_id": r["id"], "nombre": nombre_item, "proveedor": r.get("proveedor_nombre")})
    return items


# Mapea campos extraídos a columnas reales de `resultados`. Lo que no está acá
# se guarda igual como propuesta (audit log), pero al aplicarla cae en
# notas_respuesta como texto libre en vez de una columna dedicada.
_FIELD_MAP_RESULTADOS = {
    "precio_unitario": "precio_cotizado",
    "moneda": "moneda_cotizada",
    "plazo_entrega": "plazo_entrega",
    "condiciones_pago": "condiciones_pago",
}


def _aplicar_campo_resultado(sb, entity_id: str, field: str, valor, cuando_iso: str) -> None:
    """Escribe un valor extraído en `resultados`: a su columna dedicada si
    existe, o acumulado en notas_respuesta si no (ej: disponibilidad, que no
    tiene columna propia). Usado tanto por la auto-aplicación en
    /sincronizar-respuestas como por /propuestas/{id}/aplicar."""
    columna = _FIELD_MAP_RESULTADOS.get(field)
    cambios = {"estado": "respondido", "respuesta_recibida_at": cuando_iso}
    if columna:
        cambios[columna] = valor
    else:
        actual = ejecutar_maybe_single(sb.table("resultados").select("notas_respuesta").eq("id", entity_id).maybe_single())
        previa = (actual.data or {}).get("notas_respuesta") or ""
        cambios["notas_respuesta"] = (previa + f"\n{field}: {valor}").strip()
    sb.table("resultados").update(cambios).eq("id", entity_id).execute()


@router.post("/sincronizar-respuestas")
async def sincronizar_respuestas(ctx: AuthContext = Depends(get_auth_context)):
    """Trigger manual (botón en /conversaciones) — delega en la misma función
    que corre sola cada pocos minutos vía cron (ver sincronizar_todos_los_usuarios)."""
    return await _sincronizar_usuario(ctx.actor_user_id)


@router.post("/mensajes/{message_id}/reprocesar")
async def reprocesar_mensaje(message_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Vuelve a correr el Email Understanding Agent sobre un mensaje inbound
    ya guardado. Existe para el caso en que una extracción anterior no
    generó ninguna propuesta (ambigüedad, item_ctx vacío en ese momento,
    error transitorio de Gemini) y el mensaje quedó marcado 'procesado' sin
    dejar rastro para reintentar solo — no reinventa el parseo, solo destraba
    el mismo camino que corre `_sincronizar_usuario`."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    msg = ejecutar_maybe_single(
        sb.table("gmail_messages").select("id,conversation_id,direction").eq("id", message_id).maybe_single()
    ).data
    if not msg or msg.get("direction") != "inbound":
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    conv = ejecutar_maybe_single(
        sb.table("gmail_conversations").select("id,user_id,estado").eq("id", msg["conversation_id"])
        .in_("user_id", ctx.user_ids_organizacion).maybe_single()
    ).data
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    sb.table("gmail_messages").update({"procesado": False}).eq("id", message_id).execute()
    if conv["estado"] not in ("sent", "waiting_for_supplier", "supplier_replied", "partially_answered", "clarification_required"):
        sb.table("gmail_conversations").update({"estado": "supplier_replied"}).eq("id", conv["id"]).execute()

    return await _sincronizar_usuario(conv["user_id"])


async def _sincronizar_usuario(user_id: str) -> dict:
    """Recorre las conversaciones activas del usuario, trae mensajes nuevos del
    hilo de Gmail, los persiste (idempotente por gmail_message_id) y para los
    inbound corre el Email Understanding Agent, guardando sus propuestas."""
    from app.services.gmail_service import get_gmail_service, listar_mensajes_thread, headers_de, extraer_texto_plano, extraer_adjuntos_meta
    from app.services.email_understanding import extraer_actualizaciones
    from app.services.supabase import get_supabase
    from app.services import gmail_conversation_agent
    from app.services.gmail_conversation_agent import CAMPOS_SEGUIMIENTO
    from app.services.notificaciones import crear_notificacion

    UMBRAL_AUTO_APLICAR = 0.85

    sb = get_supabase()
    res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Gmail no conectado")
    integration = res.data
    service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
    mi_email = (integration["email"] or "").lower()

    from app.services.organizacion import ids_organizacion
    # "clarification_required" queda acá a propósito: significa que una
    # extracción anterior fue ambigua, no que la conversación terminó — si se
    # excluye, el hilo deja de revisarse para siempre aunque el proveedor
    # responda de nuevo con datos claros.
    activas = sb.table("gmail_conversations").select("*").in_("user_id", ids_organizacion(user_id)).in_(
        "estado", ["sent", "waiting_for_supplier", "supplier_replied", "partially_answered", "clarification_required"]
    ).execute().data or []

    resumen = {"conversaciones_revisadas": len(activas), "mensajes_nuevos": 0, "propuestas_generadas": 0}

    for conv in activas:
        try:
            existentes = {
                m["gmail_message_id"]: m
                for m in sb.table("gmail_messages").select("id,gmail_message_id,procesado").eq("conversation_id", conv["id"]).execute().data or []
            }
            mensajes = listar_mensajes_thread(service, conv["gmail_thread_id"])
        except Exception as e:
            print(f"[Gmail sync] thread {conv.get('gmail_thread_id')}: {e}")
            continue

        for msg in mensajes:
            ya_guardado = existentes.get(msg["id"])
            # Idempotente por procesado, no sólo por existencia: si un intento
            # anterior guardó el mensaje pero se cayó antes de terminar de
            # procesarlo (ej: error extrayendo datos), acá se reintenta en vez
            # de saltarlo para siempre.
            if ya_guardado and ya_guardado.get("procesado"):
                continue
            h = headers_de(msg)
            from_email = h.get("From", "")
            # La etiqueta SENT de Gmail es más confiable que comparar el
            # remitente por texto (evita falsos "outbound"/"inbound" con
            # alias o nombres de display). Nota: si te respondes a ti mismo
            # dentro del mismo hilo para probar, Gmail igual lo marca SENT
            # (porque lo enviaste tú) — no hay forma de distinguirlo de un
            # envío real; para simular una respuesta de proveedor hay que
            # responder desde OTRA cuenta de correo.
            labels = msg.get("labelIds", []) or []
            if labels:
                direction = "outbound" if "SENT" in labels else "inbound"
            else:
                direction = "outbound" if mi_email and mi_email in from_email.lower() else "inbound"
            cuerpo = extraer_texto_plano(msg.get("payload", {}))
            adjuntos_meta = extraer_adjuntos_meta(msg.get("payload", {}))
            recibido_iso = datetime.now(timezone.utc).isoformat()

            if ya_guardado:
                # Reintento de un mensaje que se guardó pero no se terminó de
                # procesar — reusa la fila en vez de reinsertar (gmail_message_id
                # es único).
                row = {"id": ya_guardado["id"]}
            else:
                row = sb.table("gmail_messages").insert({
                    "conversation_id": conv["id"],
                    "gmail_message_id": msg["id"],
                    "gmail_thread_id": conv["gmail_thread_id"],
                    "direction": direction,
                    "from_email": from_email,
                    "to_email": h.get("To", ""),
                    "subject": h.get("Subject", ""),
                    "body_text": cuerpo,
                    "received_at": recibido_iso,
                    "procesado": direction == "outbound",
                }).execute().data[0]
                resumen["mensajes_nuevos"] += 1

                for a in adjuntos_meta:
                    sb.table("gmail_attachments").insert({
                        "message_id": row["id"],
                        "filename": a["filename"],
                        "mime_type": a["mime_type"],
                        "gmail_attachment_id": a["attachment_id"],
                    }).execute()

            if direction != "inbound":
                if not ya_guardado:
                    sb.table("gmail_messages").update({"procesado": True}).eq("id", row["id"]).execute()
                continue

            nuevo_estado = "supplier_replied"
            es_respuesta_rfq = False
            rfq_completa = False
            try:
                # El proveedor respondió desde un correo distinto al contacto
                # registrado: NO se crea otro proveedor ni se agrega el contacto
                # solo — la respuesta ya quedó asociada al hilo (prioridad #1 de
                # asociación), y se propone el contacto nuevo para confirmación.
                remitente = _extraer_email(from_email)
                if conv.get("proveedor_id") and remitente and remitente != (conv.get("proveedor_email") or "").lower():
                    ya_conocido = sb.table("proveedor_contactos").select("id").eq("proveedor_id", conv["proveedor_id"]).eq("email", remitente).execute().data
                    ya_propuesto = sb.table("item_field_updates").select("id").eq("entity_type", "proveedor_contacto").eq("entity_id", conv["proveedor_id"]).eq("new_value", json.dumps(remitente)).eq("estado", "propuesta").execute().data
                    if not ya_conocido and not ya_propuesto:
                        sb.table("item_field_updates").insert({
                            "user_id": user_id,
                            "entity_type": "proveedor_contacto",
                            "entity_id": conv["proveedor_id"],
                            "field": "email",
                            "previous_value": None,
                            "new_value": json.dumps(remitente),
                            "source_type": "gmail_message",
                            "source_id": row["id"],
                            "supplier_nombre": conv.get("proveedor_nombre"),
                            "supplier_email": conv.get("proveedor_email"),
                            "confidence": 0.9,
                        }).execute()
                        resumen["propuestas_generadas"] += 1

                if _parece_automatico(h.get("Subject", ""), from_email, cuerpo):
                    nuevo_estado = "human_review_required"
                elif conv.get("tipo") == "homologacion":
                    from app.services.workflow_homologation import registrar_recepcion_antecedentes
                    registrar_recepcion_antecedentes(
                        conv["id"], msg["id"],
                        [a.get("filename") for a in adjuntos_meta if a.get("filename")],
                        cuerpo,
                    )
                    nuevo_estado = "human_review_required"
                elif conv.get("oc_id"):
                    nuevo_estado = await _procesar_respuesta_oc(
                        sb, service, conv, mi_email, cuerpo, recibido_iso, msg["id"],
                    )
                else:
                    es_respuesta_rfq = True
                    items_ctx = _items_contexto(sb, conv)
                    extraccion = await extraer_actualizaciones(cuerpo, items_ctx)
                    entity_unico = items_ctx[0]["entity_id"] if len(items_ctx) == 1 else None

                    # Campos "core" (precio/disponibilidad/plazo/condiciones) con
                    # confianza alta se aplican solos — son los datos operativos
                    # de la cotización, no datos maestros del proveedor. Todo lo
                    # demás (u otra confianza) queda como propuesta para revisar.
                    campos_recibidos: set[str] = set()
                    for p in extraccion["propuestas"]:
                        entity_id = p["entity_id"] or entity_unico
                        if not entity_id:
                            continue  # ambiguo y no hay un único ítem al que asociarlo por defecto
                        # "disponibilidad" y "stock_disponible" cuentan como el mismo
                        # dato de seguimiento (la tabla no tiene columna dedicada,
                        # ambas caen en notas_respuesta vía _aplicar_campo_resultado).
                        campo_seguimiento = "disponibilidad" if p["field"] in ("disponibilidad", "stock_disponible") else p["field"]
                        columna = _FIELD_MAP_RESULTADOS.get(p["field"])
                        previo = None
                        if columna:
                            r = ejecutar_maybe_single(sb.table("resultados").select(columna).eq("id", entity_id).maybe_single())
                            previo = r.data.get(columna) if r.data else None

                        auto_aplicar = campo_seguimiento in CAMPOS_SEGUIMIENTO and p["confidence"] >= UMBRAL_AUTO_APLICAR
                        fila_propuesta = {
                            "user_id": user_id,
                            "entity_type": "resultado",
                            "entity_id": entity_id,
                            "field": p["field"],
                            "previous_value": json.dumps(previo, default=str),
                            "new_value": json.dumps(p["new_value"], default=str),
                            "currency": p.get("currency"),
                            "source_type": "gmail_message",
                            "source_id": row["id"],
                            "supplier_nombre": conv.get("proveedor_nombre"),
                            "supplier_email": conv.get("proveedor_email"),
                            "confidence": p["confidence"],
                        }
                        # El orden (propuesta → aplicar → marcar aplicado) es
                        # deliberado y está explicado en el servicio.
                        registrar_actualizacion_campo(
                            sb, fila_propuesta,
                            auto_aplicar=auto_aplicar,
                            agente="gmail_agent",
                            cuando_iso=recibido_iso,
                            aplicar=lambda: _aplicar_campo_resultado(
                                sb, entity_id, p["field"], p["new_value"], recibido_iso
                            ),
                        )
                        resumen["propuestas_generadas"] += 1

                        if auto_aplicar:
                            try:
                                sb.table("rfq_batch_items").update({
                                    "estado": "responded", "updated_at": recibido_iso,
                                }).eq("resultado_id", entity_id).execute()
                            except Exception:
                                pass
                            try:
                                from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
                                registrar_evento_para_resultado(
                                    user_id, entity_id, "supplier_replied_can_supply",
                                    {"conversation_id": conv["id"], "gmail_message_id": msg["id"]},
                                )
                                if p["field"] == "precio_unitario":
                                    registrar_evento_para_resultado(
                                        user_id, entity_id, "valid_quote_received",
                                        {"conversation_id": conv["id"], "gmail_message_id": msg["id"]},
                                    )
                            except Exception as e:
                                print(f"[Gmail sync] evidencia de capacidad: {e}")
                            campos_recibidos.add(campo_seguimiento)

                    if campos_recibidos:
                        item_nombre = items_ctx[0]["nombre"] if items_ctx else _nombre_cotizacion(sb, conv.get("cotizacion_id") or "")
                        lista_nombre = _nombre_lista(sb, conv.get("lista_proyecto_id"))
                        proveedor_nombre = conv.get("proveedor_nombre") or "un proveedor"
                        detalle = f"{proveedor_nombre} respondió sobre '{item_nombre}'"
                        if lista_nombre:
                            detalle += f" (lista '{lista_nombre}')"
                        crear_notificacion(
                            sb, user_id, "email_cotizacion",
                            "Nueva respuesta de proveedor",
                            detalle + ".",
                            {
                                "conversation_id": conv["id"],
                                "lista_id": conv.get("lista_proyecto_id"),
                                "lista_nombre": lista_nombre,
                                "proveedor_nombre": proveedor_nombre,
                                "item_nombre": item_nombre,
                            },
                        )

                    pendientes = CAMPOS_SEGUIMIENTO - campos_recibidos
                    if extraccion["requiere_aclaracion"] and not campos_recibidos:
                        nuevo_estado = "clarification_required"
                    elif campos_recibidos:
                        # Hubo al menos un dato core con confianza suficiente para
                        # aplicarse solo → el agente sigue la conversación sin
                        # esperar aprobación humana para ESTE paso puntual.
                        try:
                            gmail_conversation_agent.seguimiento_automatico(sb, service, conv, mi_email, pendientes)
                            nuevo_estado = "closed" if not pendientes else "partially_answered"
                        except Exception as e:
                            print(f"[Gmail sync] seguimiento automático falló: {e}")
                            nuevo_estado = "complete" if not pendientes else "partially_answered"
                    elif extraccion["propuestas"]:
                        nuevo_estado = "partially_answered"
                    rfq_completa = nuevo_estado in ("closed", "complete") or (
                        bool(campos_recibidos) and not pendientes
                    )
            except Exception as e:
                # Un mensaje problemático no debe dejar la conversación
                # colgada: se marca para revisión humana y sigue con el resto.
                print(f"[Gmail sync] error procesando mensaje {msg['id']}: {e}")
                nuevo_estado = "human_review_required"

            sb.table("gmail_messages").update({"procesado": True}).eq("id", row["id"]).execute()
            # seguimiento_automatico ya actualiza estado+last_message_at cuando
            # envía; si no se llamó (o falló el envío), lo hacemos acá.
            conv_actual = ejecutar_maybe_single(sb.table("gmail_conversations").select("estado").eq("id", conv["id"]).maybe_single()).data
            if not conv_actual or conv_actual.get("estado") not in ("closed", "compra_iniciada"):
                sb.table("gmail_conversations").update({
                    "estado": nuevo_estado, "last_message_at": recibido_iso,
                }).eq("id", conv["id"]).execute()
            if es_respuesta_rfq:
                try:
                    from app.services.workflow_rfq import registrar_respuesta_rfq
                    registrar_respuesta_rfq(conv["id"], msg["id"], completa=rfq_completa)
                except Exception as e:
                    # El mensaje ya quedó guardado y procesado por el agente;
                    # un fallo del adaptador se hace visible sin reejecutar
                    # extracción ni duplicar respuestas automáticas.
                    print(f"[Gmail sync] evento workflow RFQ falló: {e}")

    return resumen


async def sincronizar_todos_los_usuarios() -> dict:
    """Corre _sincronizar_usuario para cada usuario con al menos una
    conversación activa. La llama el cron cada pocos minutos (ver
    services/cron.py) — así el usuario no tiene que acordarse de apretar
    'Sincronizar respuestas': el agente revisa Gmail solo."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    activas = sb.table("gmail_conversations").select("user_id").in_(
        "estado", ["sent", "waiting_for_supplier", "supplier_replied", "partially_answered", "clarification_required"]
    ).execute().data or []
    usuarios = {c["user_id"] for c in activas}

    resumen = {"usuarios_revisados": len(usuarios), "errores": 0}
    for uid in usuarios:
        try:
            await _sincronizar_usuario(uid)
        except Exception as e:
            resumen["errores"] += 1
            print(f"[Gmail cron] error sincronizando user_id={uid}: {e}")
    return resumen


@router.get("/conversaciones")
async def listar_conversaciones(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    ids = ctx.user_ids_organizacion
    convs = sb.table("gmail_conversations").select("*").in_("user_id", ids).order("last_message_at", desc=True).execute().data or []

    propuestas = sb.table("item_field_updates").select("source_id").in_("user_id", ids).eq("estado", "propuesta").execute().data or []
    ids_mensajes_con_propuesta = [p["source_id"] for p in propuestas if p.get("source_id")]
    conv_por_mensaje: dict[str, str] = {}
    if ids_mensajes_con_propuesta:
        msgs = sb.table("gmail_messages").select("id,conversation_id").in_("id", ids_mensajes_con_propuesta).execute().data or []
        conv_por_mensaje = {m["id"]: m["conversation_id"] for m in msgs}
    pendientes_por_conv: dict[str, int] = {}
    for p in propuestas:
        conv_id = conv_por_mensaje.get(p.get("source_id"))
        if conv_id:
            pendientes_por_conv[conv_id] = pendientes_por_conv.get(conv_id, 0) + 1

    for c in convs:
        c["gmail_url"] = f"https://mail.google.com/mail/u/0/#all/{c['gmail_thread_id']}"
        c["propuestas_pendientes"] = pendientes_por_conv.get(c["id"], 0)
    return convs


@router.get("/conversaciones/{conversation_id}")
async def detalle_conversacion(conversation_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    conv = ejecutar_maybe_single(sb.table("gmail_conversations").select("*").eq("id", conversation_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv["gmail_url"] = f"https://mail.google.com/mail/u/0/#all/{conv['gmail_thread_id']}"

    mensajes = sb.table("gmail_messages").select("*").eq("conversation_id", conversation_id).order("received_at").execute().data or []
    ids_mensajes = [m["id"] for m in mensajes]
    adjuntos = []
    propuestas = []
    if ids_mensajes:
        adjuntos = sb.table("gmail_attachments").select("*").in_("message_id", ids_mensajes).execute().data or []
        propuestas = sb.table("item_field_updates").select("*").in_("source_id", ids_mensajes).order("created_at", desc=True).execute().data or []

    return {"conversacion": conv, "mensajes": mensajes, "adjuntos": adjuntos, "propuestas": propuestas}


class RevisarPropuestaRequest(BaseModel):
    pass


@router.post("/propuestas/{propuesta_id}/aplicar")
async def aplicar_propuesta(propuesta_id: str, req: RevisarPropuestaRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Aprueba una propuesta: la marca aplicada y, si el campo mapea a una
    columna real de `resultados`, la escribe. Acción explícita de un humano —
    el agente nunca llega a este estado por sí solo."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    p = ejecutar_maybe_single(sb.table("item_field_updates").select("*").eq("id", propuesta_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    if not p:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    if p["estado"] != "propuesta":
        raise HTTPException(status_code=400, detail=f"Ya estaba '{p['estado']}'")

    nuevo_valor = json.loads(p["new_value"]) if isinstance(p["new_value"], str) else p["new_value"]

    if p["entity_type"] == "resultado":
        aplicado_at = datetime.now(timezone.utc).isoformat()
        _aplicar_campo_resultado(sb, p["entity_id"], p["field"], nuevo_valor, aplicado_at)
        try:
            sb.table("rfq_batch_items").update({"estado": "responded", "updated_at": aplicado_at}).eq("resultado_id", p["entity_id"]).execute()
            from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
            registrar_evento_para_resultado(ctx.actor_user_id, p["entity_id"], "supplier_replied_can_supply", {"propuesta_id": propuesta_id, "revision": "manual"})
            if p["field"] == "precio_unitario":
                registrar_evento_para_resultado(ctx.actor_user_id, p["entity_id"], "valid_quote_received", {"propuesta_id": propuesta_id, "revision": "manual"})
        except Exception as e:
            print(f"[Gmail propuesta] evidencia de capacidad: {e}")
    elif p["entity_type"] == "proveedor_contacto" and p["field"] == "email":
        from app.services.proveedores_matching import resolver_o_crear_contacto
        resolver_o_crear_contacto(sb, ctx.actor_user_id, p["entity_id"], nuevo_valor, origen="gmail_agent")

    sb.table("item_field_updates").update({
        "estado": "aplicado", "reviewed_at": datetime.now(timezone.utc).isoformat(), "reviewed_by": ctx.actor_user_id,
    }).eq("id", propuesta_id).execute()

    return {"success": True}


@router.post("/propuestas/{propuesta_id}/rechazar")
async def rechazar_propuesta(propuesta_id: str, req: RevisarPropuestaRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    p = ejecutar_maybe_single(sb.table("item_field_updates").select("id,estado").eq("id", propuesta_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    if not p:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    if p["estado"] != "propuesta":
        raise HTTPException(status_code=400, detail=f"Ya estaba '{p['estado']}'")
    sb.table("item_field_updates").update({
        "estado": "descartado", "reviewed_at": datetime.now(timezone.utc).isoformat(), "reviewed_by": ctx.actor_user_id,
    }).eq("id", propuesta_id).execute()
    return {"success": True}
