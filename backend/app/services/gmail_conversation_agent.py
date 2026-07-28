"""
Continuación automática de conversaciones del agente de Gmail: agradecer
cuando la respuesta viene completa, pedir sólo lo que falta cuando viene
parcial, y arrancar la etapa de compra cuando un proveedor queda
seleccionado y autorizado. Usa textos fijos (no LLM) para estos envíos
automáticos — es intencional: un correo que sale solo, sin revisión humana,
no debe depender de que un modelo no alucine.
"""
from datetime import datetime, timezone

# Los 4 datos que se le pide a todo proveedor al cotizar (ver PROMPT en
# gmail.py /generar-correo). Si llegan los 4, la conversación se cierra sola.
CAMPOS_SEGUIMIENTO = {"precio_unitario", "disponibilidad", "plazo_entrega", "condiciones_pago"}

_LABEL = {
    "precio_unitario": "el precio unitario",
    "disponibilidad": "la disponibilidad",
    "plazo_entrega": "el plazo de entrega",
    "condiciones_pago": "las condiciones de pago",
}


def _listar_campos(campos: set[str]) -> str:
    labels = [_LABEL.get(c, c) for c in campos]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " y " + labels[-1]


def redactar_agradecimiento(proveedor_nombre: str | None) -> str:
    nombre = proveedor_nombre or "estimados"
    return (
        f"Estimados {nombre},\n\n"
        "Muchas gracias por la información enviada, ya quedó registrada de nuestro lado. "
        "Quedamos en contacto para los siguientes pasos.\n\n"
        "Saludos cordiales."
    )


def redactar_pedir_faltantes(proveedor_nombre: str | None, pendientes: set[str]) -> str:
    nombre = proveedor_nombre or "estimados"
    return (
        f"Estimados {nombre},\n\n"
        "Gracias por su respuesta, ya registramos lo que nos enviaron. "
        f"Para completar la evaluación nos falta {_listar_campos(pendientes)}.\n\n"
        "¿Podrían confirmarnos ese dato? Quedamos atentos.\n\n"
        "Saludos cordiales."
    )


def redactar_inicio_compra(proveedor_nombre: str | None) -> str:
    nombre = proveedor_nombre or "estimados"
    return (
        f"Estimados {nombre},\n\n"
        "Les contamos que su cotización fue seleccionada y ya está autorizada internamente "
        "para continuar con la compra. Para avanzar, ¿podrían confirmarnos:\n\n"
        "- ¿Cuál es su proceso habitual de venta? ¿Necesitan que emitamos una Orden de Compra formal?\n"
        "- Sus datos para homologarlos como proveedor (razón social, RUT, dirección y, si aplica, datos bancarios).\n"
        "- Sus condiciones de pago vigentes.\n\n"
        "Quedamos atentos para coordinar los siguientes pasos hasta la emisión de la factura.\n\n"
        "Saludos cordiales."
    )


def _enviar_y_registrar(sb, service, conv: dict, mi_email: str, cuerpo: str, nuevo_estado: str, nuevo_tipo: str | None = None) -> bool:
    from app.services.gmail_service import send_email_threaded, headers_de

    ultimo_inbound = (
        sb.table("gmail_messages").select("*")
        .eq("conversation_id", conv["id"]).eq("direction", "inbound")
        .order("received_at", desc=True).limit(1).execute().data
    )
    ultimo_inbound = ultimo_inbound[0] if ultimo_inbound else None
    destino = (ultimo_inbound.get("from_email") if ultimo_inbound else None) or conv.get("proveedor_email")
    if not destino:
        return False

    try:
        msg = send_email_threaded(
            service, destino, conv.get("subject") or "Cotización", cuerpo, mi_email,
            conv["gmail_thread_id"], in_reply_to_msgid=None,
        )
    except Exception as e:
        print(f"[Gmail agent] no se pudo enviar seguimiento automático: {e}")
        return False

    ahora = datetime.now(timezone.utc).isoformat()
    sb.table("gmail_messages").insert({
        "conversation_id": conv["id"], "gmail_message_id": msg["id"], "gmail_thread_id": conv["gmail_thread_id"],
        "direction": "outbound", "from_email": mi_email, "to_email": destino,
        "subject": conv.get("subject") or "Cotización", "body_text": cuerpo,
        "received_at": ahora, "procesado": True,
    }).execute()
    cambios = {"estado": nuevo_estado, "last_message_at": ahora}
    if nuevo_tipo:
        cambios["tipo"] = nuevo_tipo
    sb.table("gmail_conversations").update(cambios).eq("id", conv["id"]).execute()
    return True


def seguimiento_automatico(sb, service, conv: dict, mi_email: str, pendientes: set[str]) -> bool:
    """Envía agradecimiento (si no falta nada) o pide sólo lo pendiente."""
    if pendientes:
        cuerpo = redactar_pedir_faltantes(conv.get("proveedor_nombre"), pendientes)
        return _enviar_y_registrar(sb, service, conv, mi_email, cuerpo, "partially_answered")
    cuerpo = redactar_agradecimiento(conv.get("proveedor_nombre"))
    return _enviar_y_registrar(sb, service, conv, mi_email, cuerpo, "closed")


def iniciar_proceso_compra(user_id: str, resultado_id: str) -> bool:
    """Se llama cuando un resultado queda definitivo Y su lista queda
    autorizada (aprobaciones.py). Idempotente: si la conversación ya está en
    'compra_iniciada' (o más adelante), no reenvía nada."""
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service

    sb = get_supabase()
    convs = (
        sb.table("gmail_conversations").select("*")
        .eq("resultado_id", resultado_id).eq("user_id", user_id)
        .order("last_message_at", desc=True).limit(1).execute().data
    )
    conv = convs[0] if convs else None
    if not conv or conv.get("estado") == "compra_iniciada":
        return False

    integ = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").maybe_single().execute().data
    if not integ:
        return False

    try:
        service, _ = get_gmail_service(integ["access_token"], integ["refresh_token"])
    except Exception as e:
        print(f"[Gmail agent] no se pudo autenticar para iniciar compra: {e}")
        return False

    cuerpo = redactar_inicio_compra(conv.get("proveedor_nombre"))
    return _enviar_y_registrar(sb, service, conv, integ["email"], cuerpo, "compra_iniciada", nuevo_tipo="compra")
