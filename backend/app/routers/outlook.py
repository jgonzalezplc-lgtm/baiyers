import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context
from app.services.item_field_updates import registrar_actualizacion_campo
from app.services.supabase import ejecutar_maybe_single

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


# ─── Enviar correo ─────────────────────────────────────────────────────────────
# Duplicado deliberado de `/api/gmail/enviar` — no se reusa el router de Gmail
# para no arriesgar el flujo en producción. `/api/gmail/generar-correo` (la
# plantilla generada por Gemini) NO se duplica: no tiene nada específico de
# Gmail, el frontend la sigue usando para ambos proveedores.

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
    from app.services import outlook_service
    from app.services.supabase import get_supabase

    sb = get_supabase()

    res = sb.table("user_integrations").select("*").eq("user_id", req.user_id).eq("provider", "outlook").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Outlook no conectado. Ve al dashboard para conectar tu cuenta.")

    integration = res.data

    try:
        access_token = outlook_service.get_valid_access_token(
            integration["access_token"], integration["refresh_token"], req.user_id, sb,
        )

        body_final = req.body.replace("{proveedor_nombre}", req.proveedor_nombre)
        subject_final = req.subject.replace("{proveedor_nombre}", req.proveedor_nombre)

        msg = outlook_service.send_email(access_token, req.to_email, subject_final, body_final, integration["email"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enviando email: {str(e)}")

    now_iso = datetime.now(timezone.utc).isoformat()
    if req.resultado_id:
        sb.table("resultados").update({
            "solicitud_enviada_at": now_iso,
            "estado": "contactado",
            "proveedor_email": req.to_email,
        }).eq("id", req.resultado_id).execute()
    elif req.cotizacion_id != "demo":
        sb.table("resultados").update({
            "solicitud_enviada_at": now_iso,
            "estado": "contactado",
            "proveedor_email": req.to_email,
        }).eq("cotizacion_id", req.cotizacion_id).eq("proveedor_nombre", req.proveedor_nombre[:100]).execute()

    try:
        from app.services.supplier_intelligence import registrar_solicitud
        registrar_solicitud(req.user_id, req.proveedor_nombre, req.to_email)
    except Exception as e:
        print(f"[Outlook] SI error: {e}")

    thread_id = msg.get("conversationId")
    try:
        from app.services.proveedores_matching import resolver_o_crear_proveedor, resolver_o_crear_contacto
        proveedor_id = resolver_o_crear_proveedor(sb, req.user_id, req.proveedor_nombre or req.to_email, req.to_email)
        contacto_id = resolver_o_crear_contacto(sb, req.user_id, proveedor_id, req.to_email, origen="outlook_agent")

        conv = sb.table("outlook_conversations").upsert({
            "user_id": req.user_id,
            "graph_thread_id": thread_id,
            "proveedor_id": proveedor_id,
            "contacto_id": contacto_id,
            "proveedor_nombre": req.proveedor_nombre or None,
            "proveedor_email": req.to_email,
            "cotizacion_id": req.cotizacion_id if req.cotizacion_id != "demo" else None,
            "resultado_id": req.resultado_id,
            "subject": subject_final,
            "estado": "sent",
            "last_message_at": now_iso,
        }, on_conflict="user_id,graph_thread_id").execute()
        conversation_id = conv.data[0]["id"]
        if msg.get("id"):
            sb.table("outlook_messages").upsert({
                "conversation_id": conversation_id,
                "graph_message_id": msg.get("id"),
                "graph_thread_id": thread_id,
                "direction": "outbound",
                "from_email": integration["email"],
                "to_email": req.to_email,
                "subject": subject_final,
                "body_text": body_final,
                "received_at": now_iso,
                "procesado": True,
            }, on_conflict="graph_message_id").execute()
    except Exception as e:
        # No bloquea el envío si el esquema del agente aún no está migrado.
        print(f"[Outlook] No se pudo registrar la conversación: {e}")

    return {"success": True, "message_id": msg.get("id"), "thread_id": thread_id}


# ─── Sync email ─────────────────────────────────────────────────────────────

@router.post("/sync-email")
async def sync_outlook_email(ctx: AuthContext = Depends(get_auth_context)):
    """Actualiza el email real de la cuenta Outlook conectada."""
    import httpx
    from app.services.supabase import get_supabase

    user_id = ctx.actor_user_id
    sb = get_supabase()
    res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "outlook").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Outlook no conectado")

    access_token = res.data["access_token"]
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudo obtener el email de Microsoft. Reconecta Outlook.")

    info = resp.json()
    outlook_email = info.get("mail") or info.get("userPrincipalName")
    if outlook_email:
        sb.table("user_integrations").update({"email": outlook_email}).eq("user_id", user_id).eq("provider", "outlook").execute()

    return {"email": outlook_email}


# ─── Agente de Outlook: sincronizar respuestas ──────────────────────────────
# Puerto exacto de la lógica de `_sincronizar_usuario`/`sincronizar_todos_los_usuarios`
# de gmail.py, pero sobre Graph y las tablas outlook_*. Alcance recortado: no
# hay RFQ agrupada (rfq_batches) para Outlook en esta primera versión.

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
    import re as _re
    m = _re.search(r"<([^<>]+)>", header_from)
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


async def _procesar_respuesta_oc(sb, access_token: str, conv: dict, mi_email: str, cuerpo: str, recibido_iso: str) -> str:
    """Respuesta a una OC (conv['oc_id'] presente) — mismo criterio que el
    agente de Gmail: no se extraen campos, sólo interesa si el proveedor
    acusó recibo o avisó despacho."""
    from app.services.email_understanding import clasificar_respuesta_oc
    from app.services import outlook_conversation_agent

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
            print(f"[OC] SI error (acuse por correo, Outlook): {e}")
        cuerpo_resp = (
            f"Estimados,\n\nGracias por confirmar la recepción de la orden. "
            f"Quedamos atentos al despacho.\n\nSaludos cordiales."
        )
        outlook_conversation_agent._enviar_y_registrar(sb, access_token, conv, mi_email, cuerpo_resp, "waiting_for_supplier", evento="supplier_intake_started")
        return "waiting_for_supplier"

    if tipo == "despacho":
        sb.table("ordenes_compra").update({
            "estado": "despachada", "despacho_at": recibido_iso,
            "despacho_detalle": clasificacion.get("detalle"),
        }).eq("id", oc["id"]).execute()
        cuerpo_resp = (
            f"Estimados,\n\nGracias por avisarnos. Quedamos atentos a la llegada del pedido.\n\nSaludos cordiales."
        )
        outlook_conversation_agent._enviar_y_registrar(sb, access_token, conv, mi_email, cuerpo_resp, "closed", evento="supplier_intake_started")
        return "closed"

    return "human_review_required"


def _items_contexto(sb, conv: dict) -> list[dict]:
    """Ítem(s) sobre los que trata esta conversación. A diferencia de la
    versión de Gmail, NO hay bloque de rfq_batches — Outlook no soporta RFQ
    agrupada en esta primera versión."""
    items = []
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


# Mismo mapeo que gmail.py — campo extraído -> columna real de `resultados`.
_FIELD_MAP_RESULTADOS = {
    "precio_unitario": "precio_cotizado",
    "moneda": "moneda_cotizada",
    "plazo_entrega": "plazo_entrega",
    "condiciones_pago": "condiciones_pago",
}


def _aplicar_campo_resultado(sb, entity_id: str, field: str, valor, cuando_iso: str) -> None:
    """Idéntica a `gmail._aplicar_campo_resultado` — genérica, sólo depende de
    `sb` y de la tabla `resultados`. Se duplica acá por consistencia con el
    resto del router (no importa nada de `app.routers.gmail`)."""
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
    que corre sola cada minuto vía cron (ver sincronizar_todos_los_usuarios_outlook)."""
    return await _sincronizar_usuario_outlook(ctx.actor_user_id)


@router.post("/mensajes/{message_id}/reprocesar")
async def reprocesar_mensaje(message_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Puerto exacto de `reprocesar_mensaje` de gmail.py — ver ahí el porqué."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    msg = ejecutar_maybe_single(
        sb.table("outlook_messages").select("id,conversation_id,direction").eq("id", message_id).maybe_single()
    ).data
    if not msg or msg.get("direction") != "inbound":
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    conv = ejecutar_maybe_single(
        sb.table("outlook_conversations").select("id,user_id,estado").eq("id", msg["conversation_id"])
        .in_("user_id", ctx.user_ids_organizacion).maybe_single()
    ).data
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    sb.table("outlook_messages").update({"procesado": False}).eq("id", message_id).execute()
    if conv["estado"] not in ("sent", "waiting_for_supplier", "supplier_replied", "partially_answered", "clarification_required"):
        sb.table("outlook_conversations").update({"estado": "supplier_replied"}).eq("id", conv["id"]).execute()

    return await _sincronizar_usuario_outlook(conv["user_id"])


async def _sincronizar_usuario_outlook(user_id: str) -> dict:
    """Puerto exacto de `_sincronizar_usuario` de gmail.py, sobre Microsoft
    Graph. Recorre conversaciones activas, trae mensajes nuevos del hilo,
    los persiste (idempotente por graph_message_id) y para los inbound corre
    el Email Understanding Agent, guardando sus propuestas."""
    from app.services import outlook_service
    from app.services.email_understanding import extraer_actualizaciones
    from app.services.supabase import get_supabase
    from app.services import outlook_conversation_agent
    from app.services.outlook_conversation_agent import CAMPOS_SEGUIMIENTO
    from app.services.notificaciones import crear_notificacion

    UMBRAL_AUTO_APLICAR = 0.85

    sb = get_supabase()
    res = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "outlook").single().execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Outlook no conectado")
    integration = res.data
    access_token = outlook_service.get_valid_access_token(
        integration["access_token"], integration["refresh_token"], user_id, sb,
    )
    mi_email = (integration["email"] or "").lower()

    from app.services.organizacion import ids_organizacion
    # "clarification_required" queda acá a propósito: significa que una
    # extracción anterior fue ambigua, no que la conversación terminó — si se
    # excluye, el hilo deja de revisarse para siempre aunque el proveedor
    # responda de nuevo con datos claros.
    activas = sb.table("outlook_conversations").select("*").in_("user_id", ids_organizacion(user_id)).in_(
        "estado", ["sent", "waiting_for_supplier", "supplier_replied", "partially_answered", "clarification_required"]
    ).execute().data or []

    resumen = {"conversaciones_revisadas": len(activas), "mensajes_nuevos": 0, "propuestas_generadas": 0}

    for conv in activas:
        try:
            existentes = {
                m["graph_message_id"]: m
                for m in sb.table("outlook_messages").select("id,graph_message_id,procesado").eq("conversation_id", conv["id"]).execute().data or []
            }
            mensajes = outlook_service.listar_mensajes_thread(access_token, conv["graph_thread_id"])
        except Exception as e:
            print(f"[Outlook sync] thread {conv.get('graph_thread_id')}: {e}")
            continue

        for msg in mensajes:
            ya_guardado = existentes.get(msg["id"])
            if ya_guardado and ya_guardado.get("procesado"):
                continue
            h = outlook_service.headers_de(msg)
            from_email = h.get("From", "")
            direction = "outbound" if outlook_service.es_enviado_por_mi(msg, mi_email) else "inbound"
            cuerpo = outlook_service.extraer_texto_plano(msg)
            adjuntos_meta = outlook_service.extraer_adjuntos_meta(msg)
            recibido_iso = datetime.now(timezone.utc).isoformat()

            if ya_guardado:
                row = {"id": ya_guardado["id"]}
            else:
                row = sb.table("outlook_messages").insert({
                    "conversation_id": conv["id"],
                    "graph_message_id": msg["id"],
                    "graph_thread_id": conv["graph_thread_id"],
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
                    sb.table("outlook_attachments").insert({
                        "message_id": row["id"],
                        "filename": a["filename"],
                        "mime_type": a["mime_type"],
                        "graph_attachment_id": a["attachment_id"],
                    }).execute()

            if direction != "inbound":
                if not ya_guardado:
                    sb.table("outlook_messages").update({"procesado": True}).eq("id", row["id"]).execute()
                continue

            nuevo_estado = "supplier_replied"
            try:
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
                            "source_type": "outlook_message",
                            "source_id": row["id"],
                            "supplier_nombre": conv.get("proveedor_nombre"),
                            "supplier_email": conv.get("proveedor_email"),
                            "confidence": 0.9,
                        }).execute()
                        resumen["propuestas_generadas"] += 1

                if _parece_automatico(h.get("Subject", ""), from_email, cuerpo):
                    nuevo_estado = "human_review_required"
                elif conv.get("oc_id"):
                    nuevo_estado = await _procesar_respuesta_oc(sb, access_token, conv, mi_email, cuerpo, recibido_iso)
                else:
                    items_ctx = _items_contexto(sb, conv)
                    extraccion = await extraer_actualizaciones(cuerpo, items_ctx)
                    entity_unico = items_ctx[0]["entity_id"] if len(items_ctx) == 1 else None

                    campos_recibidos: set[str] = set()
                    for p in extraccion["propuestas"]:
                        entity_id = p["entity_id"] or entity_unico
                        if not entity_id:
                            continue
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
                            "source_type": "outlook_message",
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
                            agente="outlook_agent",
                            cuando_iso=recibido_iso,
                            aplicar=lambda: _aplicar_campo_resultado(
                                sb, entity_id, p["field"], p["new_value"], recibido_iso
                            ),
                        )
                        resumen["propuestas_generadas"] += 1

                        if auto_aplicar:
                            try:
                                from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
                                registrar_evento_para_resultado(
                                    user_id, entity_id, "supplier_replied_can_supply",
                                    {"conversation_id": conv["id"], "graph_message_id": msg["id"]},
                                )
                                if p["field"] == "precio_unitario":
                                    registrar_evento_para_resultado(
                                        user_id, entity_id, "valid_quote_received",
                                        {"conversation_id": conv["id"], "graph_message_id": msg["id"]},
                                    )
                            except Exception as e:
                                print(f"[Outlook sync] evidencia de capacidad: {e}")
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
                        try:
                            outlook_conversation_agent.seguimiento_automatico(sb, access_token, conv, mi_email, pendientes)
                            nuevo_estado = "closed" if not pendientes else "partially_answered"
                        except Exception as e:
                            print(f"[Outlook sync] seguimiento automático falló: {e}")
                            nuevo_estado = "complete" if not pendientes else "partially_answered"
                    elif extraccion["propuestas"]:
                        nuevo_estado = "partially_answered"
            except Exception as e:
                print(f"[Outlook sync] error procesando mensaje {msg['id']}: {e}")
                nuevo_estado = "human_review_required"

            sb.table("outlook_messages").update({"procesado": True}).eq("id", row["id"]).execute()
            conv_actual = ejecutar_maybe_single(sb.table("outlook_conversations").select("estado").eq("id", conv["id"]).maybe_single()).data
            if not conv_actual or conv_actual.get("estado") not in ("closed", "compra_iniciada"):
                sb.table("outlook_conversations").update({
                    "estado": nuevo_estado, "last_message_at": recibido_iso,
                }).eq("id", conv["id"]).execute()

    return resumen


async def sincronizar_todos_los_usuarios_outlook() -> dict:
    """Corre `_sincronizar_usuario_outlook` para cada usuario con al menos
    una conversación de Outlook activa. La llama el cron cada minuto (ver
    services/cron.py), igual que Gmail."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    activas = sb.table("outlook_conversations").select("user_id").in_(
        "estado", ["sent", "waiting_for_supplier", "supplier_replied", "partially_answered", "clarification_required"]
    ).execute().data or []
    usuarios = {c["user_id"] for c in activas}

    resumen = {"usuarios_revisados": len(usuarios), "errores": 0}
    for uid in usuarios:
        try:
            await _sincronizar_usuario_outlook(uid)
        except Exception as e:
            resumen["errores"] += 1
            print(f"[Outlook cron] error sincronizando user_id={uid}: {e}")
    return resumen


@router.get("/conversaciones")
async def listar_conversaciones(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    ids = ctx.user_ids_organizacion
    convs = sb.table("outlook_conversations").select("*").in_("user_id", ids).order("last_message_at", desc=True).execute().data or []

    propuestas = sb.table("item_field_updates").select("source_id").in_("user_id", ids).eq("estado", "propuesta").execute().data or []
    ids_mensajes_con_propuesta = [p["source_id"] for p in propuestas if p.get("source_id")]
    conv_por_mensaje: dict[str, str] = {}
    if ids_mensajes_con_propuesta:
        msgs = sb.table("outlook_messages").select("id,conversation_id").in_("id", ids_mensajes_con_propuesta).execute().data or []
        conv_por_mensaje = {m["id"]: m["conversation_id"] for m in msgs}
    pendientes_por_conv: dict[str, int] = {}
    for p in propuestas:
        conv_id = conv_por_mensaje.get(p.get("source_id"))
        if conv_id:
            pendientes_por_conv[conv_id] = pendientes_por_conv.get(conv_id, 0) + 1

    for c in convs:
        # No hay un deep-link confiable a Outlook web para un conversationId
        # de Graph — se deja null en vez de inventar una URL sin confirmar.
        c["outlook_url"] = None
        c["propuestas_pendientes"] = pendientes_por_conv.get(c["id"], 0)
    return convs


@router.get("/conversaciones/{conversation_id}")
async def detalle_conversacion(conversation_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    conv = ejecutar_maybe_single(sb.table("outlook_conversations").select("*").eq("id", conversation_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv["outlook_url"] = None

    mensajes = sb.table("outlook_messages").select("*").eq("conversation_id", conversation_id).order("received_at").execute().data or []
    ids_mensajes = [m["id"] for m in mensajes]
    adjuntos = []
    propuestas = []
    if ids_mensajes:
        adjuntos = sb.table("outlook_attachments").select("*").in_("message_id", ids_mensajes).execute().data or []
        propuestas = sb.table("item_field_updates").select("*").in_("source_id", ids_mensajes).order("created_at", desc=True).execute().data or []

    return {"conversacion": conv, "mensajes": mensajes, "adjuntos": adjuntos, "propuestas": propuestas}


# ─── Propuestas ──────────────────────────────────────────────────────────────
# `item_field_updates` es genérica (no distingue proveedor de correo) — se
# duplican estos dos endpoints acá por consistencia con el resto del router,
# pero el frontend puede llamar indistintamente `/api/gmail/propuestas/...`
# o `/api/outlook/propuestas/...`: ambos operan sobre la misma tabla.

class RevisarPropuestaRequest(BaseModel):
    pass


@router.post("/propuestas/{propuesta_id}/aplicar")
async def aplicar_propuesta(propuesta_id: str, req: RevisarPropuestaRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Aprueba una propuesta: la marca aplicada y, si el campo mapea a una
    columna real de `resultados`, la escribe. Acción explícita de un humano."""
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
            from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
            registrar_evento_para_resultado(ctx.actor_user_id, p["entity_id"], "supplier_replied_can_supply", {"propuesta_id": propuesta_id, "revision": "manual"})
            if p["field"] == "precio_unitario":
                registrar_evento_para_resultado(ctx.actor_user_id, p["entity_id"], "valid_quote_received", {"propuesta_id": propuesta_id, "revision": "manual"})
        except Exception as e:
            print(f"[Outlook propuesta] evidencia de capacidad: {e}")
    elif p["entity_type"] == "proveedor_contacto" and p["field"] == "email":
        from app.services.proveedores_matching import resolver_o_crear_contacto
        resolver_o_crear_contacto(sb, ctx.actor_user_id, p["entity_id"], nuevo_valor, origen="outlook_agent")

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
    sb.table("item_field_updates").update({
        "estado": "descartado", "reviewed_at": datetime.now(timezone.utc).isoformat(), "reviewed_by": ctx.actor_user_id,
    }).eq("id", propuesta_id).execute()
    return {"success": True}
