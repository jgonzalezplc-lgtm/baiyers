"""Scheduler durable del workflow unificado (PRD Fase C).

En esta fase ejecuta únicamente comunicaciones internas de autorización.
RFQ, homologación y OC se conectan en fases posteriores. Todas las acciones
se adquieren con lease y todo correo se reserva antes de Gmail.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services.workflow_automation import proximo_vencimiento
from app.services.workflow_automation_service import (
    obtener_o_crear_ejecucion_nodo, programar_accion, reservar_accion,
)


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(valor: Optional[str]) -> datetime:
    if not valor:
        return _now()
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _actualizar_accion(action_id: str, estado: str, **campos) -> None:
    payload = {"estado": estado, "updated_at": _now().isoformat(), **campos}
    _sb().table("workflow_scheduled_actions").update(payload).eq("id", action_id).execute()


def _evento(instance_id: str, nodo_id: str, accion: str, clave: str,
            *, responsable_id: Optional[str] = None,
            node_execution_id: Optional[str] = None,
            communication_rule_id: Optional[str] = None,
            comentario: Optional[str] = None) -> None:
    try:
        _sb().table("workflow_events").insert({
            "instance_id": instance_id, "nodo_id": nodo_id,
            "actor_responsable_id": responsable_id, "accion": accion,
            "canal": "email", "clave_idempotencia": clave,
            "node_execution_id": node_execution_id,
            "communication_rule_id": communication_rule_id,
            "comentario": comentario,
        }).execute()
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate key" not in str(exc).lower():
            raise


def programar_recordatorios_autorizacion(
    resolucion: dict, *, responsable_id: str, lista_id: str, lista_nombre: str,
) -> list[dict]:
    """Crea acciones para las reglas `approval_reminder` de la tarjeta.
    Es inocua para instancias legacy y es idempotente por visita/regla/persona."""
    if resolucion.get("execution_owner") != "unified":
        return []
    sb = _sb()
    ejecucion = obtener_o_crear_ejecucion_nodo(
        resolucion["workflow_instance_id"], resolucion["nodo_id"],
        {"lista_id": lista_id, "lista_nombre": lista_nombre},
    )
    _evento(
        resolucion["workflow_instance_id"], resolucion["nodo_id"], "node_entered",
        f"node_entered:{ejecucion['id']}", node_execution_id=ejecucion["id"],
    )
    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", resolucion["workflow_id"]
    ).eq("nodo_id", resolucion["nodo_id"]).eq("evento_plantilla", "approval_reminder").eq(
        "activa", True
    ).execute().data or []
    creadas = []
    for regla in reglas:
        dias = int(regla.get("demora_inicial_dias") or regla.get("repetir_cada_dias") or 1)
        due_at = proximo_vencimiento(_now(), max(dias, 1))
        creada = programar_accion(
            node_execution_id=ejecucion["id"],
            instance_id=resolucion["workflow_instance_id"], nodo_id=resolucion["nodo_id"],
            visit_number=ejecucion["visit_number"], communication_rule_id=regla["id"],
            recipient_key=responsable_id, due_at=due_at, attempt_number=1,
        )
        if creada:
            creadas.append(creada)
    return creadas


def cancelar_recordatorios_autorizacion(instance_id: str, nodo_id: str,
                                        responsable_id: Optional[str] = None) -> int:
    sb = _sb()
    ejecuciones = sb.table("workflow_node_executions").select("id").eq(
        "instance_id", instance_id
    ).eq("nodo_id", nodo_id).in_("estado", ["activa", "esperando"]).execute().data or []
    if not ejecuciones:
        return 0
    ids = [e["id"] for e in ejecuciones]
    q = sb.table("workflow_scheduled_actions").update({
        "estado": "cancelada", "lease_token": None, "lease_until": None,
        "updated_at": _now().isoformat(),
    }).in_("node_execution_id", ids).in_("estado", ["programada", "reservada"])
    if responsable_id:
        q = q.eq("recipient_key", responsable_id)
    filas = q.execute().data or []
    return len(filas)


def completar_ejecucion_autorizacion(instance_id: str, nodo_id: str, resultado: str) -> None:
    sb = _sb()
    ejecuciones = sb.table("workflow_node_executions").select("id").eq(
        "instance_id", instance_id
    ).eq("nodo_id", nodo_id).in_("estado", ["activa", "esperando"]).execute().data or []
    for ejecucion in ejecuciones:
        sb.table("workflow_node_executions").update({
            "estado": "completada", "resultado": resultado,
            "completed_at": _now().isoformat(), "updated_at": _now().isoformat(),
        }).eq("id", ejecucion["id"]).execute()
        _evento(instance_id, nodo_id, "node_completed", f"node_completed:{ejecucion['id']}:{resultado}",
                node_execution_id=ejecucion["id"])


def _agotar(action: dict, regla: dict, ejecucion: dict, instancia: dict) -> dict:
    politica = regla.get("politica_agotamiento") or "pausar"
    _actualizar_accion(action["id"], "agotada", lease_token=None, lease_until=None)
    _evento(instancia["id"], ejecucion["nodo_id"], "loop_exhausted",
            f"loop_exhausted:{action['id']}", responsable_id=action.get("recipient_key"),
            node_execution_id=ejecucion["id"], communication_rule_id=regla["id"],
            comentario=politica)
    # En autorización interna ninguna política debe aprobar por ausencia de
    # respuesta. Escalar/timeout quedan pausados para intervención humana.
    _sb().table("workflow_instances").update({"estado_workflow": "pausado"}).eq(
        "id", instancia["id"]
    ).execute()
    return {"estado": "agotada", "politica": politica}


def _procesar_followup_rfq(action: dict, regla: dict, ejecucion: dict, instancia: dict) -> dict:
    sb = _sb()
    batches = sb.table("rfq_batches").select("*").eq("id", action["recipient_key"]).eq(
        "node_execution_id", ejecucion["id"]
    ).limit(1).execute().data or []
    if not batches:
        _actualizar_accion(action["id"], "cancelada", lease_token=None, lease_until=None)
        return {"estado": "cancelada", "motivo": "rfq_inexistente"}
    batch = batches[0]
    if batch.get("execution_owner") != "unified" or batch.get("resolution_state") != "pendiente":
        _actualizar_accion(action["id"], "cancelada", lease_token=None, lease_until=None)
        return {"estado": "cancelada", "motivo": "rfq_resuelta_o_legacy"}

    max_intentos = regla.get("max_intentos")
    if max_intentos and action["attempt_number"] > max_intentos:
        if regla.get("politica_agotamiento") == "descartar_entidad":
            from app.services.workflow_rfq import descartar_batch_por_agotamiento
            _actualizar_accion(action["id"], "agotada", lease_token=None, lease_until=None)
            cierre = descartar_batch_por_agotamiento(batch, regla)
            return {"estado": "agotada", "politica": "descartar_entidad", "cierre": cierre}
        return _agotar(action, regla, ejecucion, instancia)

    conversaciones = sb.table("gmail_conversations").select("*").eq(
        "id", batch.get("conversation_id")
    ).limit(1).execute().data or []
    integraciones = sb.table("user_integrations").select("*").eq(
        "user_id", instancia["user_id"]
    ).eq("provider", "gmail").limit(1).execute().data or []
    if not conversaciones or not integraciones:
        _actualizar_accion(action["id"], "fallida", last_error="Conversación o Gmail no resoluble")
        return {"estado": "fallida"}
    conv, integration = conversaciones[0], integraciones[0]
    items = sb.table("rfq_batch_items").select("cotizacion_id").eq(
        "rfq_batch_id", batch["id"]
    ).execute().data or []
    cot_ids = [i["cotizacion_id"] for i in items]
    cotizaciones = sb.table("cotizaciones").select("nombre_identificado").in_(
        "id", cot_ids
    ).execute().data or [] if cot_ids else []
    items_texto = ", ".join(c.get("nombre_identificado") or "ítem" for c in cotizaciones) or "los ítems solicitados"
    proveedor = sb.table("proveedores").select("nombre").eq(
        "id", batch["proveedor_id"]
    ).limit(1).execute().data or []

    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(instancia["user_id"])
    if not org:
        _actualizar_accion(action["id"], "fallida", last_error="Organización no resoluble")
        return {"estado": "fallida"}
    from app.services.mail_template_service import render, reservar_envio, actualizar_entrega_reservada
    dias = max(0, (_now() - _parse_dt(batch.get("sent_at"))).days)
    renderizado = render("rfq_followup", {
        "proveedor_nombre": (proveedor[0].get("nombre") if proveedor else None) or conv.get("proveedor_nombre") or "estimados",
        "items": items_texto, "dias_transcurridos": dias,
    }, organizacion_id=org.organizacion_id, workflow_id=instancia["workflow_id"],
       nodo_id=ejecucion["nodo_id"])
    reserva = reservar_envio(
        org.organizacion_id, "rfq_followup", batch["destinatario_email"], action["idempotency_key"],
        workflow_id=instancia["workflow_id"], workflow_nodo_id=ejecucion["nodo_id"],
        proveedor_id=batch["proveedor_id"], scheduled_action_id=action["id"],
    )
    if not reserva["adquirida"]:
        estado_previo = (reserva.get("entrega") or {}).get("estado")
        nuevo_estado = "enviada" if estado_previo == "enviado" else "delivery_uncertain"
        _actualizar_accion(action["id"], nuevo_estado, lease_token=None, lease_until=None)
        return {"estado": nuevo_estado, "motivo": "entrega_ya_reservada"}

    from app.services.gmail_service import get_gmail_service, send_email_threaded
    entrega, token = reserva["entrega"], reserva["reservation_token"]
    try:
        service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            }).eq("user_id", instancia["user_id"]).eq("provider", "gmail").execute()
        msg = send_email_threaded(
            service, batch["destinatario_email"], renderizado["subject"], renderizado["body"],
            integration["email"], conv["gmail_thread_id"], in_reply_to_msgid=None,
        )
        actualizar_entrega_reservada(
            entrega["id"], token, "enviado", gmail_message_id=msg.get("id"),
            gmail_thread_id=msg.get("threadId") or conv["gmail_thread_id"],
        )
        ahora = _now().isoformat()
        sb.table("gmail_messages").upsert({
            "conversation_id": conv["id"], "gmail_message_id": msg.get("id"),
            "gmail_thread_id": conv["gmail_thread_id"], "direction": "outbound",
            "from_email": integration["email"], "to_email": batch["destinatario_email"],
            "subject": renderizado["subject"], "body_text": renderizado["body"],
            "received_at": ahora, "procesado": True,
        }, on_conflict="gmail_message_id").execute()
        sb.table("gmail_conversations").update({
            "estado": "waiting_for_supplier", "last_message_at": ahora,
        }).eq("id", conv["id"]).execute()
        _actualizar_accion(action["id"], "enviada", lease_token=None, lease_until=None)
        _evento(instancia["id"], ejecucion["nodo_id"], "mail_sent", f"mail_sent:{action['id']}",
                node_execution_id=ejecucion["id"], communication_rule_id=regla["id"])
    except Exception as exc:
        actualizar_entrega_reservada(entrega["id"], token, "delivery_uncertain", error=str(exc))
        _actualizar_accion(action["id"], "delivery_uncertain", last_error=str(exc)[:1000],
                           lease_token=None, lease_until=None)
        return {"estado": "delivery_uncertain"}

    if regla.get("repetir_cada_dias"):
        programar_accion(
            node_execution_id=ejecucion["id"], instance_id=instancia["id"],
            nodo_id=ejecucion["nodo_id"], visit_number=ejecucion["visit_number"],
            communication_rule_id=regla["id"], recipient_key=batch["id"],
            due_at=proximo_vencimiento(_now(), int(regla["repetir_cada_dias"])),
            attempt_number=action["attempt_number"] + 1,
        )
    return {"estado": "enviada"}


def _procesar_followup_homologacion(action: dict, regla: dict, ejecucion: dict, instancia: dict) -> dict:
    sb = _sb()
    casos = sb.table("supplier_homologation_cases").select("*").eq(
        "id", action["recipient_key"]
    ).eq("node_execution_id", ejecucion["id"]).limit(1).execute().data or []
    if not casos or casos[0].get("estado") in ("homologado", "rechazado"):
        _actualizar_accion(action["id"], "cancelada", lease_token=None, lease_until=None)
        return {"estado": "cancelada", "motivo": "homologacion_resuelta_o_inexistente"}
    caso = casos[0]
    max_intentos = regla.get("max_intentos")
    if max_intentos and action["attempt_number"] > max_intentos:
        return _agotar(action, regla, ejecucion, instancia)
    conv = sb.table("gmail_conversations").select("*").eq(
        "id", caso.get("conversation_id")
    ).limit(1).execute().data or []
    proveedor = sb.table("proveedores").select("nombre,email").eq(
        "id", caso["proveedor_id"]
    ).limit(1).execute().data or []
    integration = sb.table("user_integrations").select("*").eq(
        "user_id", instancia["user_id"]
    ).eq("provider", "gmail").limit(1).execute().data or []
    if not conv or not proveedor or not integration:
        _actualizar_accion(action["id"], "fallida", last_error="Contexto de homologación no resoluble")
        return {"estado": "fallida"}
    conv, proveedor, integration = conv[0], proveedor[0], integration[0]
    destinatario = conv.get("proveedor_email") or proveedor.get("email")
    if not destinatario:
        _actualizar_accion(action["id"], "fallida", last_error="Proveedor sin email")
        return {"estado": "fallida"}
    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(instancia["user_id"])
    if not org:
        _actualizar_accion(action["id"], "fallida", last_error="Organización no resoluble")
        return {"estado": "fallida"}
    from app.services.mail_template_service import render, reservar_envio, actualizar_entrega_reservada
    requisitos = caso.get("requisitos") or []
    recibidos = set(caso.get("antecedentes_recibidos") or [])
    pendientes = [r for r in requisitos if r not in recibidos] or requisitos
    dias = max(0, (_now() - _parse_dt(caso.get("solicitado_at"))).days)
    renderizado = render("supplier_intake_followup", {
        "proveedor_nombre": proveedor.get("nombre") or "estimados",
        "requisitos_pendientes": "\n".join(f"- {r}" for r in pendientes),
        "dias_transcurridos": dias,
    }, organizacion_id=org.organizacion_id, workflow_id=instancia["workflow_id"],
       nodo_id=ejecucion["nodo_id"])
    reserva = reservar_envio(
        org.organizacion_id, "supplier_intake_followup", destinatario, action["idempotency_key"],
        workflow_id=instancia["workflow_id"], workflow_nodo_id=ejecucion["nodo_id"],
        proveedor_id=caso["proveedor_id"], scheduled_action_id=action["id"],
    )
    if not reserva["adquirida"]:
        previo = (reserva.get("entrega") or {}).get("estado")
        estado = "enviada" if previo == "enviado" else "delivery_uncertain"
        _actualizar_accion(action["id"], estado, lease_token=None, lease_until=None)
        return {"estado": estado, "motivo": "entrega_ya_reservada"}
    from app.services.gmail_service import get_gmail_service, send_email_threaded
    entrega, token = reserva["entrega"], reserva["reservation_token"]
    try:
        service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            }).eq("user_id", instancia["user_id"]).eq("provider", "gmail").execute()
        msg = send_email_threaded(
            service, destinatario, renderizado["subject"], renderizado["body"],
            integration["email"], conv["gmail_thread_id"], in_reply_to_msgid=None,
        )
        actualizar_entrega_reservada(
            entrega["id"], token, "enviado", gmail_message_id=msg.get("id"),
            gmail_thread_id=msg.get("threadId") or conv["gmail_thread_id"],
        )
        ahora = _now().isoformat()
        sb.table("gmail_messages").upsert({
            "conversation_id": conv["id"], "gmail_message_id": msg.get("id"),
            "gmail_thread_id": conv["gmail_thread_id"], "direction": "outbound",
            "from_email": integration["email"], "to_email": destinatario,
            "subject": renderizado["subject"], "body_text": renderizado["body"],
            "received_at": ahora, "procesado": True,
        }, on_conflict="gmail_message_id").execute()
        sb.table("gmail_conversations").update({
            "estado": "waiting_for_supplier", "last_message_at": ahora,
        }).eq("id", conv["id"]).execute()
        _actualizar_accion(action["id"], "enviada", lease_token=None, lease_until=None)
        _evento(instancia["id"], ejecucion["nodo_id"], "mail_sent", f"mail_sent:{action['id']}",
                node_execution_id=ejecucion["id"], communication_rule_id=regla["id"])
    except Exception as exc:
        actualizar_entrega_reservada(entrega["id"], token, "delivery_uncertain", error=str(exc))
        _actualizar_accion(action["id"], "delivery_uncertain", last_error=str(exc)[:1000],
                           lease_token=None, lease_until=None)
        return {"estado": "delivery_uncertain"}
    if regla.get("repetir_cada_dias"):
        programar_accion(
            node_execution_id=ejecucion["id"], instance_id=instancia["id"],
            nodo_id=ejecucion["nodo_id"], visit_number=ejecucion["visit_number"],
            communication_rule_id=regla["id"], recipient_key=caso["id"],
            due_at=proximo_vencimiento(_now(), int(regla["repetir_cada_dias"])),
            attempt_number=action["attempt_number"] + 1,
        )
    return {"estado": "enviada"}


def _procesar_recordatorio_oc(action: dict, regla: dict, ejecucion: dict, instancia: dict) -> dict:
    sb = _sb()
    ocs = sb.table("ordenes_compra").select("*").eq("id", action["recipient_key"]).eq(
        "node_execution_id", ejecucion["id"]
    ).limit(1).execute().data or []
    if not ocs:
        _actualizar_accion(action["id"], "cancelada", lease_token=None, lease_until=None)
        return {"estado": "cancelada", "motivo": "oc_inexistente"}
    oc = ocs[0]
    evento = regla.get("evento_plantilla")
    if evento == "purchase_order_ack_reminder" and oc.get("estado") not in ("enviada", "borrador"):
        _actualizar_accion(action["id"], "cancelada", lease_token=None, lease_until=None)
        return {"estado": "cancelada", "motivo": "acuse_ya_resuelto"}
    if evento == "dispatch_status_request" and oc.get("estado") == "despachada":
        _actualizar_accion(action["id"], "cancelada", lease_token=None, lease_until=None)
        return {"estado": "cancelada", "motivo": "despacho_ya_informado"}
    max_intentos = regla.get("max_intentos")
    if max_intentos and action["attempt_number"] > max_intentos:
        return _agotar(action, regla, ejecucion, instancia)
    convs = sb.table("gmail_conversations").select("*").eq("oc_id", oc["id"]).limit(1).execute().data or []
    integrations = sb.table("user_integrations").select("*").eq(
        "user_id", instancia["user_id"]
    ).eq("provider", "gmail").limit(1).execute().data or []
    if not convs or not integrations or not oc.get("proveedor_email"):
        _actualizar_accion(action["id"], "fallida", last_error="OC, conversación o Gmail no resoluble")
        return {"estado": "fallida"}
    conv, integration = convs[0], integrations[0]
    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(instancia["user_id"])
    if not org:
        _actualizar_accion(action["id"], "fallida", last_error="Organización no resoluble")
        return {"estado": "fallida"}
    from app.services.mail_template_service import render, reservar_envio, actualizar_entrega_reservada
    variables = {"proveedor_nombre": oc.get("proveedor_nombre") or "estimados", "numero_oc": oc.get("numero_oc") or "OC"}
    if evento == "purchase_order_ack_reminder":
        variables["dias_transcurridos"] = max(0, (_now() - _parse_dt(oc.get("created_at"))).days)
    renderizado = render(evento, variables, organizacion_id=org.organizacion_id,
                         workflow_id=instancia["workflow_id"], nodo_id=ejecucion["nodo_id"])
    reserva = reservar_envio(
        org.organizacion_id, evento, oc["proveedor_email"], action["idempotency_key"],
        workflow_id=instancia["workflow_id"], workflow_nodo_id=ejecucion["nodo_id"],
        proveedor_id=conv.get("proveedor_id"), scheduled_action_id=action["id"],
    )
    if not reserva["adquirida"]:
        previo = (reserva.get("entrega") or {}).get("estado")
        estado = "enviada" if previo == "enviado" else "delivery_uncertain"
        _actualizar_accion(action["id"], estado, lease_token=None, lease_until=None)
        return {"estado": estado, "motivo": "entrega_ya_reservada"}
    from app.services.gmail_service import get_gmail_service, send_email_threaded
    entrega, token = reserva["entrega"], reserva["reservation_token"]
    try:
        service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            }).eq("user_id", instancia["user_id"]).eq("provider", "gmail").execute()
        msg = send_email_threaded(
            service, oc["proveedor_email"], renderizado["subject"], renderizado["body"],
            integration["email"], conv["gmail_thread_id"], in_reply_to_msgid=None,
        )
        actualizar_entrega_reservada(
            entrega["id"], token, "enviado", gmail_message_id=msg.get("id"),
            gmail_thread_id=msg.get("threadId") or conv["gmail_thread_id"],
        )
        ahora = _now().isoformat()
        sb.table("gmail_messages").upsert({
            "conversation_id": conv["id"], "gmail_message_id": msg.get("id"),
            "gmail_thread_id": conv["gmail_thread_id"], "direction": "outbound",
            "from_email": integration["email"], "to_email": oc["proveedor_email"],
            "subject": renderizado["subject"], "body_text": renderizado["body"],
            "received_at": ahora, "procesado": True,
        }, on_conflict="gmail_message_id").execute()
        _actualizar_accion(action["id"], "enviada", lease_token=None, lease_until=None)
        _evento(instancia["id"], ejecucion["nodo_id"], "mail_sent", f"mail_sent:{action['id']}",
                node_execution_id=ejecucion["id"], communication_rule_id=regla["id"])
    except Exception as exc:
        actualizar_entrega_reservada(entrega["id"], token, "delivery_uncertain", error=str(exc))
        _actualizar_accion(action["id"], "delivery_uncertain", last_error=str(exc)[:1000],
                           lease_token=None, lease_until=None)
        return {"estado": "delivery_uncertain"}
    if regla.get("repetir_cada_dias"):
        programar_accion(
            node_execution_id=ejecucion["id"], instance_id=instancia["id"],
            nodo_id=ejecucion["nodo_id"], visit_number=ejecucion["visit_number"],
            communication_rule_id=regla["id"], recipient_key=oc["id"],
            due_at=proximo_vencimiento(_now(), int(regla["repetir_cada_dias"])),
            attempt_number=action["attempt_number"] + 1,
        )
    return {"estado": "enviada"}


def procesar_accion(action: dict) -> dict:
    sb = _sb()
    ejecucion_rows = sb.table("workflow_node_executions").select("*").eq(
        "id", action["node_execution_id"]
    ).limit(1).execute().data or []
    if not ejecucion_rows:
        _actualizar_accion(action["id"], "cancelada")
        return {"estado": "cancelada", "motivo": "ejecucion_inexistente"}
    ejecucion = ejecucion_rows[0]
    instancia = sb.table("workflow_instances").select("*").eq(
        "id", ejecucion["instance_id"]
    ).single().execute().data
    regla = sb.table("workflow_node_communication_rules").select("*").eq(
        "id", action["communication_rule_id"]
    ).single().execute().data
    if not instancia or not regla or ejecucion.get("estado") not in ("activa", "esperando"):
        _actualizar_accion(action["id"], "cancelada")
        return {"estado": "cancelada", "motivo": "contexto_inactivo"}
    if instancia.get("estado_workflow") == "pausado":
        _actualizar_accion(action["id"], "programada", lease_token=None, lease_until=None)
        return {"estado": "programada", "motivo": "instancia_pausada"}
    if instancia.get("estado_workflow") != "activo" or instancia.get("execution_owner") != "unified":
        _actualizar_accion(action["id"], "cancelada")
        return {"estado": "cancelada", "motivo": "owner_o_estado_invalido"}

    if regla.get("evento_plantilla") == "rfq_followup":
        return _procesar_followup_rfq(action, regla, ejecucion, instancia)
    if regla.get("evento_plantilla") == "supplier_intake_followup":
        return _procesar_followup_homologacion(action, regla, ejecucion, instancia)
    if regla.get("evento_plantilla") in ("purchase_order_ack_reminder", "dispatch_status_request"):
        return _procesar_recordatorio_oc(action, regla, ejecucion, instancia)
    if regla.get("evento_plantilla") != "approval_reminder":
        _actualizar_accion(action["id"], "cancelada")
        return {"estado": "cancelada", "motivo": "evento_fuera_fase_c"}

    max_intentos = regla.get("max_intentos")
    if max_intentos and action["attempt_number"] > max_intentos:
        return _agotar(action, regla, ejecucion, instancia)

    solicitudes = sb.table("approval_requests").select("*").eq(
        "workflow_instance_id", instancia["id"]
    ).eq("workflow_nodo_id", ejecucion["nodo_id"]).eq(
        "responsable_id", action["recipient_key"]
    ).eq("estado", "pendiente").order("created_at", desc=True).limit(1).execute().data or []
    if not solicitudes:
        _actualizar_accion(action["id"], "cancelada")
        return {"estado": "cancelada", "motivo": "autorizacion_resuelta"}
    solicitud = solicitudes[0]

    responsable = sb.table("responsables").select("id,nombre,email").eq(
        "id", action["recipient_key"]
    ).single().execute().data
    proyecto = sb.table("proyectos").select("id,nombre,monto_total").eq(
        "id", instancia["lista_proyecto_id"]
    ).single().execute().data
    if not responsable or not responsable.get("email") or not proyecto:
        _actualizar_accion(action["id"], "fallida", last_error="Destinatario o lista no resoluble")
        return {"estado": "fallida"}

    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(instancia["user_id"])
    if not org:
        _actualizar_accion(action["id"], "fallida", last_error="Organización no resoluble")
        return {"estado": "fallida"}
    integraciones = sb.table("user_integrations").select("*").eq(
        "user_id", instancia["user_id"]
    ).eq("provider", "gmail").limit(1).execute().data or []
    if not integraciones:
        _actualizar_accion(action["id"], "fallida", last_error="Gmail no conectado")
        return {"estado": "fallida"}

    from app.config import settings
    from app.services.gmail_service import get_gmail_service, send_email
    from app.services.mail_template_service import render, reservar_envio, actualizar_entrega_reservada
    dias = max(0, (_now() - _parse_dt(solicitud.get("created_at"))).days)
    renderizado = render("approval_reminder", {
        "nombre_autorizador": responsable.get("nombre") or responsable["email"],
        "item": proyecto.get("nombre") or "Compra",
        "monto": f"${int(proyecto.get('monto_total') or 0):,}".replace(",", "."),
        "dias_pendiente": dias,
        "link_autorizacion": f"{settings.frontend_url}/authorize/{solicitud['token']}",
    }, organizacion_id=org.organizacion_id, workflow_id=instancia["workflow_id"],
       nodo_id=ejecucion["nodo_id"])
    reserva = reservar_envio(
        org.organizacion_id, "approval_reminder", responsable["email"], action["idempotency_key"],
        workflow_id=instancia["workflow_id"], workflow_nodo_id=ejecucion["nodo_id"],
        responsable_id=responsable["id"], scheduled_action_id=action["id"],
    )
    if not reserva["adquirida"]:
        estado_previo = (reserva.get("entrega") or {}).get("estado")
        nuevo_estado = "enviada" if estado_previo == "enviado" else "delivery_uncertain"
        _actualizar_accion(action["id"], nuevo_estado, lease_token=None, lease_until=None)
        return {"estado": nuevo_estado, "motivo": "entrega_ya_reservada"}

    entrega, token = reserva["entrega"], reserva["reservation_token"]
    try:
        integration = integraciones[0]
        service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            }).eq("user_id", instancia["user_id"]).eq("provider", "gmail").execute()
        resultado = send_email(service, responsable["email"], renderizado["subject"], renderizado["body"], integration["email"])
        actualizar_entrega_reservada(
            entrega["id"], token, "enviado",
            gmail_message_id=(resultado or {}).get("id"), gmail_thread_id=(resultado or {}).get("threadId"),
        )
        _actualizar_accion(action["id"], "enviada", lease_token=None, lease_until=None)
        _evento(instancia["id"], ejecucion["nodo_id"], "mail_sent", f"mail_sent:{action['id']}",
                responsable_id=responsable["id"], node_execution_id=ejecucion["id"],
                communication_rule_id=regla["id"])
    except Exception as exc:
        actualizar_entrega_reservada(entrega["id"], token, "delivery_uncertain", error=str(exc))
        _actualizar_accion(action["id"], "delivery_uncertain", last_error=str(exc)[:1000], lease_token=None, lease_until=None)
        return {"estado": "delivery_uncertain"}

    if regla.get("repetir_cada_dias"):
        programar_accion(
            node_execution_id=ejecucion["id"], instance_id=instancia["id"],
            nodo_id=ejecucion["nodo_id"], visit_number=ejecucion["visit_number"],
            communication_rule_id=regla["id"], recipient_key=responsable["id"],
            due_at=proximo_vencimiento(_now(), int(regla["repetir_cada_dias"])),
            attempt_number=action["attempt_number"] + 1,
        )
    return {"estado": "enviada"}


def procesar_acciones_vencidas(limite: int = 50) -> dict:
    sb = _sb()
    now = _now().isoformat()
    # El RPC decide atómicamente si una reserva venció. Así evitamos
    # interpolar timestamps ISO (con ':') dentro de la gramática de `.or_()`.
    rows = sb.table("workflow_scheduled_actions").select("*").lte(
        "due_at", now
    ).in_("estado", ["programada", "reservada"]).order("due_at").limit(limite).execute().data or []
    resultado = {"candidatas": len(rows), "procesadas": 0, "errores": 0}
    for candidata in rows:
        try:
            accion = reservar_accion(candidata["id"])
            if not accion:
                continue
            procesar_accion(accion)
            resultado["procesadas"] += 1
        except Exception as exc:
            resultado["errores"] += 1
            print(f"[WorkflowScheduler] acción {candidata.get('id')} falló: {exc}")
    return resultado


def cambiar_pausa_instancia(user_id: str, instance_id: str, pausar: bool) -> dict:
    from app.services.organizacion import ids_organizacion
    sb = _sb()
    rows = sb.table("workflow_instances").select("*").eq("id", instance_id).in_(
        "user_id", ids_organizacion(user_id)
    ).limit(1).execute().data or []
    if not rows:
        raise ValueError("Instancia no encontrada")
    actual = rows[0]
    if pausar and actual.get("estado_workflow") != "activo":
        raise ValueError("Sólo una instancia activa se puede pausar")
    if not pausar and actual.get("estado_workflow") != "pausado":
        raise ValueError("Sólo una instancia pausada se puede reanudar")
    nuevo = "pausado" if pausar else "activo"
    sb.table("workflow_instances").update({"estado_workflow": nuevo, "updated_at": _now().isoformat()}).eq(
        "id", instance_id
    ).execute()
    _evento(instance_id, actual.get("nodo_actual_id") or "", "workflow_paused" if pausar else "workflow_resumed",
            f"workflow_{'paused' if pausar else 'resumed'}:{instance_id}:{_now().isoformat()}")
    return {**actual, "estado_workflow": nuevo}


def obtener_automatizacion_instancia(user_id: str, instance_id: str) -> dict:
    """Vista operativa compacta de ejecuciones, acciones y envíos inciertos."""
    from app.services.organizacion import ids_organizacion
    sb = _sb()
    rows = sb.table("workflow_instances").select("*").eq("id", instance_id).in_(
        "user_id", ids_organizacion(user_id)
    ).limit(1).execute().data or []
    if not rows:
        raise ValueError("Instancia no encontrada")
    ejecuciones = sb.table("workflow_node_executions").select("*").eq(
        "instance_id", instance_id
    ).order("started_at").execute().data or []
    acciones = sb.table("workflow_scheduled_actions").select("*").eq(
        "instance_id", instance_id
    ).order("due_at").execute().data or []
    eventos = sb.table("workflow_events").select("*").eq(
        "instance_id", instance_id
    ).order("created_at").execute().data or []
    action_ids = [a["id"] for a in acciones]
    inciertos_por_id: dict[str, dict] = {}
    if action_ids:
        inciertos = sb.table("mail_delivery_events").select("*").in_(
            "scheduled_action_id", action_ids
        ).eq("estado", "delivery_uncertain").order("created_at", desc=True).execute().data or []
        inciertos_por_id.update({fila["id"]: fila for fila in inciertos})
    # Los correos iniciales se reservan antes de que exista una scheduled
    # action; se enlazan a la instancia por el id de approval_request.
    solicitudes = sb.table("approval_requests").select("id").eq(
        "workflow_instance_id", instance_id
    ).execute().data or []
    claves_iniciales = [f"approval_requested:{s['id']}" for s in solicitudes]
    if claves_iniciales:
        iniciales = sb.table("mail_delivery_events").select("*").in_(
            "idempotency_key", claves_iniciales
        ).eq("estado", "delivery_uncertain").order("created_at", desc=True).execute().data or []
        inciertos_por_id.update({fila["id"]: fila for fila in iniciales})
    return {
        "instancia": rows[0], "ejecuciones": ejecuciones,
        "acciones": acciones, "eventos": eventos,
        "envios_inciertos": list(inciertos_por_id.values()),
        "metricas": {
            "ejecuciones_total": len(ejecuciones),
            "ejecuciones_completadas": sum(1 for e in ejecuciones if e.get("estado") == "completada"),
            "acciones_programadas": sum(1 for a in acciones if a.get("estado") == "programada"),
            "acciones_enviadas": sum(1 for a in acciones if a.get("estado") == "enviada"),
            "loops_agotados": sum(1 for a in acciones if a.get("estado") == "agotada"),
            "envios_inciertos": len(inciertos_por_id),
            "eventos_total": len(eventos),
        },
    }
