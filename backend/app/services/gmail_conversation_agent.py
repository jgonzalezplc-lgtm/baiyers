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


def redactar_inicio_compra(proveedor_nombre: str | None, items: list[str] | None = None) -> str:
    nombre = proveedor_nombre or "estimados"
    detalle = ""
    if items:
        detalle = "\n\nÍtems seleccionados:\n" + "\n".join(f"- {item}" for item in items)
    return (
        f"Estimados {nombre},\n\n"
        "Les contamos que su cotización fue seleccionada y ya está autorizada internamente "
        f"para continuar con la compra.{detalle}\n\nPara avanzar, ¿podrían confirmarnos:\n\n"
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
    return iniciar_proceso_compra_resultados(user_id, [resultado_id]) > 0


def iniciar_proceso_compra_resultados(user_id: str, resultado_ids: list[str]) -> int:
    """Inicia compra una sola vez por conversación. Para RFQs multiítem
    incluye únicamente los resultados definitivos de ese proveedor, evitando
    confirmar accidentalmente otros ítems del mismo correo agrupado."""
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service

    sb = get_supabase()
    por_conversacion: dict[str, dict] = {}
    for resultado_id in dict.fromkeys(resultado_ids):
        convs = sb.table("gmail_conversations").select("*").eq("resultado_id", resultado_id).eq("user_id", user_id).order("last_message_at", desc=True).limit(1).execute().data or []
        conv = convs[0] if convs else None
        batch_item = None
        if not conv:
            try:
                batch_item = sb.table("rfq_batch_items").select("id,rfq_batch_id,cotizacion_id,resultado_id,cantidad,unidad").eq("resultado_id", resultado_id).maybe_single().execute().data
                if batch_item:
                    batch = sb.table("rfq_batches").select("conversation_id,user_id").eq("id", batch_item["rfq_batch_id"]).eq("user_id", user_id).maybe_single().execute().data
                    if batch and batch.get("conversation_id"):
                        conv = sb.table("gmail_conversations").select("*").eq("id", batch["conversation_id"]).eq("user_id", user_id).maybe_single().execute().data
            except Exception:
                conv = None
        if not conv:
            continue
        entrada = por_conversacion.setdefault(conv["id"], {"conv": conv, "items": [], "batch_items": []})
        if batch_item:
            nombre = "Ítem"
            try:
                cot = sb.table("cotizaciones").select("nombre_identificado").eq("id", batch_item["cotizacion_id"]).maybe_single().execute().data or {}
                nombre = cot.get("nombre_identificado") or nombre
            except Exception:
                pass
            entrada["items"].append(f"{batch_item.get('cantidad') or 1:g} {batch_item.get('unidad') or 'un'} · {nombre}")
            entrada["batch_items"].append(batch_item["id"])

    integ = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").maybe_single().execute().data
    if not integ:
        return 0

    try:
        service, _ = get_gmail_service(integ["access_token"], integ["refresh_token"])
    except Exception as e:
        print(f"[Gmail agent] no se pudo autenticar para iniciar compra: {e}")
        return 0

    enviados = 0
    for entrada in por_conversacion.values():
        conv = entrada["conv"]
        if conv.get("estado") == "compra_iniciada":
            continue
        cuerpo = redactar_inicio_compra(conv.get("proveedor_nombre"), entrada["items"])
        if _enviar_y_registrar(sb, service, conv, integ["email"], cuerpo, "compra_iniciada", nuevo_tipo="compra"):
            enviados += 1
            if entrada["batch_items"]:
                try:
                    sb.table("rfq_batch_items").update({
                        "estado": "closed", "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).in_("id", entrada["batch_items"]).execute()
                except Exception:
                    pass
    return enviados
