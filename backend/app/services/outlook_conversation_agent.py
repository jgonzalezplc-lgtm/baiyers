"""
Continuación automática de conversaciones del agente de Outlook — copia
paralela deliberada de `gmail_conversation_agent.py` (mismo rol, mismas
funciones, mismos textos fijos para envíos sin revisión humana), pero sobre
Microsoft Graph (`outlook_service`) y las tablas `outlook_conversations`/
`outlook_messages`. No se reusa el módulo de Gmail: cero riesgo de romper el
flujo de Gmail que ya está en producción generando ingresos.
"""
from datetime import datetime, timezone
from app.services.supabase import ejecutar_maybe_single

# Los 4 datos que se le pide a todo proveedor al cotizar (mismo criterio que
# el agente de Gmail — ver PROMPT en gmail.py /generar-correo, reusado por
# ambos proveedores de correo).
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


def redactar_inicio_compra(proveedor_nombre: str | None, items: list[str] | None = None) -> str:
    """Texto idéntico al de `gmail_conversation_agent.redactar_inicio_compra`
    — es texto puro sin dependencia de transporte, se duplica acá nomás para
    mantener este módulo autocontenido (sin imports cruzados con el agente
    de Gmail)."""
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


def _enviar_y_registrar(sb, access_token: str, conv: dict, mi_email: str, cuerpo: str, nuevo_estado: str, evento: str, nuevo_tipo: str | None = None) -> bool:
    from app.services import outlook_service

    ultimo_inbound = (
        sb.table("outlook_messages").select("*")
        .eq("conversation_id", conv["id"]).eq("direction", "inbound")
        .order("received_at", desc=True).limit(1).execute().data
    )
    ultimo_inbound = ultimo_inbound[0] if ultimo_inbound else None
    destino = (ultimo_inbound.get("from_email") if ultimo_inbound else None) or conv.get("proveedor_email")
    if not destino:
        return False

    in_reply_to = ultimo_inbound.get("graph_message_id") if ultimo_inbound else None

    try:
        msg = outlook_service.send_email_threaded(
            access_token, destino, conv.get("subject") or "Cotización", cuerpo, mi_email,
            conv["graph_thread_id"], in_reply_to_message_id=in_reply_to,
        )
    except Exception as e:
        print(f"[Outlook agent] no se pudo enviar seguimiento automático: {e}")
        return False

    ahora = datetime.now(timezone.utc).isoformat()
    graph_message_id = msg.get("id")
    if graph_message_id:
        sb.table("outlook_messages").insert({
            "conversation_id": conv["id"], "graph_message_id": graph_message_id, "graph_thread_id": conv["graph_thread_id"],
            "direction": "outbound", "from_email": mi_email, "to_email": destino,
            "subject": conv.get("subject") or "Cotización", "body_text": cuerpo,
            "received_at": ahora, "procesado": True,
        }).execute()
    cambios = {"estado": nuevo_estado, "last_message_at": ahora}
    if nuevo_tipo:
        cambios["tipo"] = nuevo_tipo
    sb.table("outlook_conversations").update(cambios).eq("id", conv["id"]).execute()

    if conv.get("user_id"):
        try:
            from app.services.mail_template_service import registrar_envio
            from app.services.organizacion import resolver_organizacion
            ctx_org = resolver_organizacion(conv["user_id"])
            if ctx_org:
                registrar_envio(
                    ctx_org.organizacion_id, evento, destino,
                    f"{evento}:{graph_message_id or conv['id']}", estado="enviado",
                    gmail_message_id=graph_message_id, gmail_thread_id=conv["graph_thread_id"],
                )
        except Exception as e:
            print(f"[Outlook agent] registrar_envio falló (correo ya enviado, solo auditoría): {e}")
    return True


def _renderizar_seguimiento(evento: str, conv: dict, extra: dict) -> str:
    """Wrapper del renderer de plantillas (Fase 6, genérico) — idéntico al de
    `gmail_conversation_agent`. `render()` sólo interpola variables, nunca
    genera contenido nuevo; si algo falla, cae al texto exacto default."""
    from app.services.mail_template_service import render
    from app.services.organizacion import resolver_organizacion

    nombre = conv.get("proveedor_nombre") or "estimados"
    ctx_org = resolver_organizacion(conv["user_id"]) if conv.get("user_id") else None
    try:
        return render(evento, {"proveedor_nombre": nombre, **extra}, organizacion_id=ctx_org.organizacion_id if ctx_org else None)["body"]
    except Exception as e:
        print(f"[Outlook agent] render() falló para {evento}, uso el texto default: {e}")
        from app.services.mail_events import EVENTOS
        texto = EVENTOS[evento].cuerpo_default
        for clave, valor in {"proveedor_nombre": nombre, **extra}.items():
            texto = texto.replace(f"{{{{{clave}}}}}", str(valor))
        return texto


def seguimiento_automatico(sb, access_token: str, conv: dict, mi_email: str, pendientes: set[str]) -> bool:
    """Envía agradecimiento (si no falta nada) o pide sólo lo pendiente."""
    if pendientes:
        cuerpo = _renderizar_seguimiento("rfq_missing_information", conv, {"campos_faltantes": _listar_campos(pendientes)})
        return _enviar_y_registrar(sb, access_token, conv, mi_email, cuerpo, "partially_answered", evento="rfq_missing_information")
    cuerpo = _renderizar_seguimiento("rfq_received_thanks", conv, {})
    return _enviar_y_registrar(sb, access_token, conv, mi_email, cuerpo, "closed", evento="rfq_received_thanks")


def iniciar_proceso_compra(user_id: str, resultado_id: str) -> bool:
    """Se llama cuando un resultado queda definitivo Y su lista queda
    autorizada (aprobaciones.py). Idempotente: si la conversación ya está en
    'compra_iniciada' (o más adelante), no reenvía nada."""
    return iniciar_proceso_compra_resultados(user_id, [resultado_id]) > 0


def iniciar_proceso_compra_resultados(user_id: str, resultado_ids: list[str]) -> int:
    """Inicia compra una sola vez por conversación de Outlook. A diferencia
    del agente de Gmail, no hay RFQ agrupada (rfq_batches) para Outlook en
    esta primera versión — cada resultado mapea a lo sumo a una conversación
    1:1 por resultado_id."""
    from app.services.supabase import get_supabase
    from app.services import outlook_service

    sb = get_supabase()
    por_conversacion: dict[str, dict] = {}
    for resultado_id in dict.fromkeys(resultado_ids):
        convs = sb.table("outlook_conversations").select("*").eq("resultado_id", resultado_id).eq("user_id", user_id).order("last_message_at", desc=True).limit(1).execute().data or []
        conv = convs[0] if convs else None
        if not conv:
            continue
        entrada = por_conversacion.setdefault(conv["id"], {"conv": conv, "items": []})
        try:
            r = ejecutar_maybe_single(sb.table("resultados").select("cotizacion_id").eq("id", resultado_id).maybe_single()).data or {}
            cot = ejecutar_maybe_single(sb.table("cotizaciones").select("nombre_identificado").eq("id", r.get("cotizacion_id")).maybe_single()).data or {}
            nombre = cot.get("nombre_identificado")
            if nombre:
                entrada["items"].append(nombre)
        except Exception:
            pass

    integ = ejecutar_maybe_single(sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "outlook").maybe_single()).data
    if not integ or not integ.get("refresh_token"):
        return 0

    try:
        access_token = outlook_service.get_valid_access_token(integ["access_token"], integ["refresh_token"], user_id, sb)
    except Exception as e:
        print(f"[Outlook agent] no se pudo autenticar para iniciar compra: {e}")
        return 0

    enviados = 0
    for entrada in por_conversacion.values():
        conv = entrada["conv"]
        if conv.get("estado") == "compra_iniciada":
            continue
        cuerpo = redactar_inicio_compra(conv.get("proveedor_nombre"), entrada["items"])
        # No mapea a ningún evento del catálogo (homologación/inicio de compra
        # no está entre los 16 eventos) — mismo criterio que el agente de
        # Gmail: texto fijo, la etiqueta es sólo para la auditoría.
        if _enviar_y_registrar(sb, access_token, conv, integ["email"], cuerpo, "compra_iniciada", evento="supplier_intake_started", nuevo_tipo="compra"):
            enviados += 1
    return enviados
