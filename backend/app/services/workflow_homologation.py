"""Fase E: expediente mínimo y orquestación humana de homologación."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.services.supabase import ejecutar_maybe_single
from app.services.workflow_automation import proximo_vencimiento
from app.services.workflow_automation_service import obtener_o_crear_ejecucion_nodo, programar_accion

REQUISITOS_BASICOS = [
    "Razón social, RUT, giro y domicilio",
    "Contacto comercial y de facturación",
    "Datos bancarios y certificado de titularidad emitido por el banco",
    "Condiciones de pago vigentes",
]


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evento(instance_id: str, nodo_id: str, accion: str, clave: str, *,
            node_execution_id: Optional[str] = None,
            communication_rule_id: Optional[str] = None,
            responsable_id: Optional[str] = None,
            referencia_externa: Optional[str] = None,
            comentario: Optional[str] = None) -> None:
    try:
        _sb().table("workflow_events").insert({
            "instance_id": instance_id, "nodo_id": nodo_id, "accion": accion,
            "canal": "email", "clave_idempotencia": clave,
            "node_execution_id": node_execution_id,
            "communication_rule_id": communication_rule_id,
            "actor_responsable_id": responsable_id,
            "referencia_externa": referencia_externa, "comentario": comentario,
        }).execute()
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate key" not in str(exc).lower():
            raise


def _asignados(workflow_id: str, nodo_id: str) -> list[dict]:
    filas = _sb().table("workflow_node_assignments").select(
        "responsable_id,modo,orden,responsables(id,nombre,email,activo,usuario_baiyer_id)"
    ).eq("workflow_id", workflow_id).eq("nodo_id", nodo_id).order("orden").execute().data or []
    return [f["responsables"] for f in filas if (f.get("responsables") or {}).get("activo")]


def _reglas(workflow_id: str, nodo_id: str) -> list[dict]:
    return _sb().table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", workflow_id
    ).eq("nodo_id", nodo_id).eq("activa", True).execute().data or []


def _enviar_reservado(*, user_id: str, org, evento: str, destinatario: str,
                      idempotency_key: str, variables: dict, workflow_id: str,
                      nodo_id: str, proveedor_id: Optional[str] = None,
                      responsable_id: Optional[str] = None,
                      conversation: Optional[dict] = None) -> tuple[dict, Optional[dict]]:
    sb = _sb()
    from app.services.mail_template_service import render, reservar_envio, actualizar_entrega_reservada
    renderizado = render(evento, variables, organizacion_id=org.organizacion_id,
                         workflow_id=workflow_id, nodo_id=nodo_id)
    reserva = reservar_envio(
        org.organizacion_id, evento, destinatario, idempotency_key,
        workflow_id=workflow_id, workflow_nodo_id=nodo_id,
        proveedor_id=proveedor_id, responsable_id=responsable_id,
    )
    if not reserva["adquirida"]:
        entrega = reserva.get("entrega") or {}
        if entrega.get("estado") == "enviado":
            return entrega, None
        raise RuntimeError("El envío ya fue reservado y su resultado es incierto")
    integration = ejecutar_maybe_single(sb.table("user_integrations").select("*").eq(
        "user_id", user_id
    ).eq("provider", "gmail").maybe_single()).data
    if not integration:
        actualizar_entrega_reservada(
            reserva["entrega"]["id"], reserva["reservation_token"], "fallido",
            error="Gmail no conectado",
        )
        raise ValueError("Gmail no conectado")
    from app.services.gmail_service import get_gmail_service, send_email, send_email_threaded
    try:
        service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            }).eq("user_id", user_id).eq("provider", "gmail").execute()
        if conversation and conversation.get("gmail_thread_id"):
            msg = send_email_threaded(
                service, destinatario, renderizado["subject"], renderizado["body"],
                integration["email"], conversation["gmail_thread_id"], in_reply_to_msgid=None,
            )
        else:
            msg = send_email(service, destinatario, renderizado["subject"], renderizado["body"], integration["email"])
        actualizar_entrega_reservada(
            reserva["entrega"]["id"], reserva["reservation_token"], "enviado",
            gmail_message_id=msg.get("id"), gmail_thread_id=msg.get("threadId"),
        )
        return reserva["entrega"], {"msg": msg, "renderizado": renderizado, "integration": integration}
    except Exception as exc:
        actualizar_entrega_reservada(
            reserva["entrega"]["id"], reserva["reservation_token"],
            "delivery_uncertain", error=str(exc),
        )
        raise


def iniciar_homologacion(user_id: str, lista_id: str, resultado_ids: list[str], resolucion: dict) -> dict:
    sb = _sb()
    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(user_id)
    if not org:
        raise ValueError("Organización no resoluble")
    instancia = ejecutar_maybe_single(sb.table("workflow_instances").select("*").eq(
        "id", resolucion["workflow_instance_id"]
    ).maybe_single()).data
    if not instancia or instancia.get("execution_owner") != "unified":
        raise ValueError("La instancia no pertenece al motor unificado")
    nodo = resolucion.get("nodo") or {}
    requisitos = nodo.get("requisitos_homologacion") or REQUISITOS_BASICOS
    ejecucion = obtener_o_crear_ejecucion_nodo(
        instancia["id"], resolucion["nodo_id"],
        {"lista_id": lista_id, "requisitos": requisitos},
    )
    asignados = _asignados(instancia["workflow_id"], resolucion["nodo_id"])
    if not asignados:
        raise ValueError("La tarjeta de homologación no tiene responsable asignado")
    responsable = asignados[0]
    reglas = _reglas(instancia["workflow_id"], resolucion["nodo_id"])
    proyecto = ejecutar_maybe_single(sb.table("proyectos").select("nombre").eq("id", lista_id).maybe_single()).data or {}
    _evento(instancia["id"], resolucion["nodo_id"], "node_entered",
            f"node_entered:{ejecucion['id']}", node_execution_id=ejecucion["id"])

    # Una notificación interna por ejecución/responsable, no por proveedor.
    if responsable.get("email"):
        from app.config import settings
        _enviar_reservado(
            user_id=user_id, org=org, evento="internal_task_assigned",
            destinatario=responsable["email"],
            idempotency_key=f"homologation_task:{ejecucion['id']}:{responsable['id']}",
            variables={"nombre_responsable": responsable.get("nombre") or responsable["email"],
                       "tarea": resolucion.get("nodo_nombre") or "Homologar proveedores",
                       "lista_nombre": proyecto.get("nombre") or "la compra",
                       "link_baiyer": f"{settings.frontend_url}/listas/{lista_id}"},
            workflow_id=instancia["workflow_id"], nodo_id=resolucion["nodo_id"],
            responsable_id=responsable["id"],
        )

    casos, omitidos = [], []
    batch_items = sb.table("rfq_batch_items").select("rfq_batch_id,resultado_id").in_(
        "resultado_id", list(dict.fromkeys(resultado_ids))
    ).execute().data or []
    batch_ids = list({i["rfq_batch_id"] for i in batch_items})
    batches = sb.table("rfq_batches").select("*").in_("id", batch_ids).execute().data or [] if batch_ids else []
    for batch in batches:
        proveedor = ejecutar_maybe_single(sb.table("proveedores").select("id,nombre,email").eq(
            "id", batch["proveedor_id"]
        ).maybe_single()).data or {}
        email = batch.get("destinatario_email") or proveedor.get("email")
        if not email:
            omitidos.append({"proveedor_id": batch["proveedor_id"], "motivo": "sin_email"})
            continue
        conv = ejecutar_maybe_single(sb.table("gmail_conversations").select("*").eq(
            "id", batch.get("conversation_id")
        ).maybe_single()).data if batch.get("conversation_id") else None
        if not conv:
            omitidos.append({"proveedor_id": batch["proveedor_id"], "motivo": "sin_conversacion_gmail"})
            continue
        caso = sb.table("supplier_homologation_cases").upsert({
            "organizacion_id": org.organizacion_id, "user_id": user_id,
            "proveedor_id": batch["proveedor_id"], "lista_proyecto_id": lista_id,
            "workflow_instance_id": instancia["id"], "node_execution_id": ejecucion["id"],
            "responsable_id": responsable["id"], "conversation_id": (conv or {}).get("id"),
            "estado": "solicitado", "requisitos": requisitos, "solicitado_at": _now(),
            "updated_at": _now(),
        }, on_conflict="node_execution_id,proveedor_id").execute().data[0]
        entrega, enviado = _enviar_reservado(
            user_id=user_id, org=org, evento="supplier_intake_started", destinatario=email,
            idempotency_key=f"supplier_intake_started:{caso['id']}",
            variables={"proveedor_nombre": proveedor.get("nombre") or "estimados",
                       "empresa_nombre": org.nombre,
                       "requisitos": "\n".join(f"- {r}" for r in requisitos)},
            workflow_id=instancia["workflow_id"], nodo_id=resolucion["nodo_id"],
            proveedor_id=batch["proveedor_id"], conversation=conv,
        )
        if enviado and conv:
            ahora = _now()
            msg = enviado["msg"]
            sb.table("gmail_messages").upsert({
                "conversation_id": conv["id"], "gmail_message_id": msg.get("id"),
                "gmail_thread_id": conv["gmail_thread_id"], "direction": "outbound",
                "from_email": enviado["integration"]["email"], "to_email": email,
                "subject": enviado["renderizado"]["subject"], "body_text": enviado["renderizado"]["body"],
                "received_at": ahora, "procesado": True,
            }, on_conflict="gmail_message_id").execute()
            sb.table("gmail_conversations").update({
                "tipo": "homologacion", "estado": "waiting_for_supplier", "last_message_at": ahora,
            }).eq("id", conv["id"]).execute()
        for regla in reglas:
            if regla.get("evento_plantilla") != "supplier_intake_followup":
                continue
            dias = max(1, int(regla.get("demora_inicial_dias") or regla.get("repetir_cada_dias") or 1))
            programar_accion(
                node_execution_id=ejecucion["id"], instance_id=instancia["id"],
                nodo_id=resolucion["nodo_id"], visit_number=ejecucion["visit_number"],
                communication_rule_id=regla["id"], recipient_key=caso["id"],
                due_at=proximo_vencimiento(datetime.now(timezone.utc), dias), attempt_number=1,
            )
        casos.append(caso)
    if not casos:
        sb.table("workflow_instances").update({"estado_workflow": "pausado"}).eq("id", instancia["id"]).execute()
        raise ValueError("No se pudo resolver ningún proveedor seleccionado para homologación")
    return {"casos": len(casos), "omitidos": omitidos, "node_execution_id": ejecucion["id"]}


def registrar_recepcion_antecedentes(conversation_id: str, gmail_message_id: str,
                                     adjuntos: list[str], cuerpo: str = "") -> dict:
    sb = _sb()
    casos = sb.table("supplier_homologation_cases").select("*").eq(
        "conversation_id", conversation_id
    ).in_("estado", ["solicitado", "recepcion_parcial", "requiere_aclaracion"]).limit(1).execute().data or []
    if not casos:
        return {"aplicada": False}
    caso = casos[0]
    recibidos = list(dict.fromkeys([*(caso.get("antecedentes_recibidos") or []), *adjuntos]))
    estado = "en_revision" if adjuntos else "recepcion_parcial"
    sb.table("supplier_homologation_cases").update({
        "estado": estado, "antecedentes_recibidos": recibidos,
        "recibido_at": _now(), "updated_at": _now(),
    }).eq("id", caso["id"]).execute()
    ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("nodo_id").eq(
        "id", caso["node_execution_id"]
    ).maybe_single()).data or {}
    _evento(
        caso["workflow_instance_id"], ejecucion.get("nodo_id") or "",
        "documentacion_recibida", f"gmail:{gmail_message_id}:documentacion:{caso['id']}",
        node_execution_id=caso["node_execution_id"], referencia_externa=gmail_message_id,
        comentario=f"{len(adjuntos)} adjunto(s); revisión humana requerida",
    )
    return {"aplicada": True, "caso_id": caso["id"], "estado": estado}


def listar_casos(user_id: str, instance_id: Optional[str] = None,
                 lista_id: Optional[str] = None) -> list[dict]:
    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(user_id)
    if not org:
        return []
    q = _sb().table("supplier_homologation_cases").select(
        "*, proveedores(id,nombre,email), responsables(id,nombre,email,usuario_baiyer_id)"
    ).eq("organizacion_id", org.organizacion_id)
    if instance_id:
        q = q.eq("workflow_instance_id", instance_id)
    if lista_id:
        q = q.eq("lista_proyecto_id", lista_id)
    return q.order("created_at", desc=True).execute().data or []


def _cancelar_acciones(caso: dict) -> None:
    _sb().table("workflow_scheduled_actions").update({
        "estado": "cancelada", "lease_token": None, "lease_until": None,
        "updated_at": _now(),
    }).eq("node_execution_id", caso["node_execution_id"]).eq(
        "recipient_key", caso["id"]
    ).in_("estado", ["programada", "reservada"]).execute()


def _resolver_agregado(caso: dict) -> dict:
    sb = _sb()
    casos = sb.table("supplier_homologation_cases").select("id,estado").eq(
        "node_execution_id", caso["node_execution_id"]
    ).execute().data or []
    if not casos or any(c.get("estado") not in ("homologado", "rechazado") for c in casos):
        return {"resuelto": False}
    ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("*").eq(
        "id", caso["node_execution_id"]
    ).maybe_single()).data
    if not ejecucion or ejecucion.get("estado") not in ("activa", "esperando"):
        return {"resuelto": True, "ya_resuelto": True}
    resultado = "proveedor_rechazado" if any(c["estado"] == "rechazado" for c in casos) else "proveedor_homologado"
    instancia = ejecutar_maybe_single(sb.table("workflow_instances").select("*").eq(
        "id", caso["workflow_instance_id"]
    ).maybe_single()).data
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("conexiones").eq(
        "id", instancia["workflow_id"]
    ).maybe_single()).data or {}
    from app.services.workflow_engine import siguiente_nodo
    siguiente = siguiente_nodo(workflow.get("conexiones") or [], ejecucion["nodo_id"], resultado)
    if not siguiente:
        siguiente = siguiente_nodo(workflow.get("conexiones") or [], ejecucion["nodo_id"])
    sb.table("workflow_scheduled_actions").update({
        "estado": "cancelada", "lease_token": None, "lease_until": None, "updated_at": _now(),
    }).eq("node_execution_id", ejecucion["id"]).in_(
        "estado", ["programada", "reservada"]
    ).execute()
    sb.table("workflow_node_executions").update({
        "estado": "completada", "resultado": resultado,
        "completed_at": _now(), "updated_at": _now(),
    }).eq("id", ejecucion["id"]).execute()
    sb.table("workflow_instances").update({
        "nodo_actual_id": siguiente or ejecucion["nodo_id"], "updated_at": _now(),
    }).eq("id", instancia["id"]).execute()
    try:
        import json
        proyecto = ejecutar_maybe_single(sb.table("proyectos").select("descripcion").eq(
            "id", caso["lista_proyecto_id"]
        ).maybe_single()).data or {}
        data = json.loads(proyecto.get("descripcion") or "{}")
        aprobacion = data.get("aprobacion") or {}
        aprobacion.update({
            "estado": "aprobado" if resultado == "proveedor_homologado" else "rechazado",
            "resultado_homologacion": resultado,
            "nodo_actual_id": siguiente,
            "homologacion_decidida_at": _now(),
        })
        data["aprobacion"] = aprobacion
        sb.table("proyectos").update({
            "descripcion": json.dumps(data, ensure_ascii=False),
        }).eq("id", caso["lista_proyecto_id"]).execute()
    except Exception as exc:
        print(f"[Homologación] no se pudo reflejar resultado en la lista: {exc}")
    _evento(instancia["id"], ejecucion["nodo_id"], "node_completed",
            f"node_completed:{ejecucion['id']}:{resultado}", node_execution_id=ejecucion["id"])
    if siguiente:
        _evento(instancia["id"], siguiente, "transition_applied",
                f"transition:{ejecucion['id']}:{resultado}:{siguiente}",
                node_execution_id=ejecucion["id"])
    return {"resuelto": True, "resultado": resultado, "siguiente_nodo_id": siguiente}


def decidir_caso(actor_user_id: str, es_admin: bool, caso_id: str, decision: str,
                 comentario: str = "", requisitos_pendientes: Optional[list[str]] = None) -> dict:
    if decision not in {"incompleta", "homologado", "rechazado"}:
        raise ValueError("Decisión inválida")
    sb = _sb()
    caso = ejecutar_maybe_single(sb.table("supplier_homologation_cases").select(
        "*, responsables(usuario_baiyer_id)"
    ).eq("id", caso_id).maybe_single()).data
    if not caso:
        raise ValueError("Caso no encontrado")
    from app.services.organizacion import resolver_organizacion
    actor_org = resolver_organizacion(actor_user_id)
    if not actor_org or actor_org.organizacion_id != caso.get("organizacion_id"):
        raise PermissionError("El caso no pertenece a tu organización")
    asignado_user = (caso.get("responsables") or {}).get("usuario_baiyer_id")
    if not es_admin and asignado_user != actor_user_id:
        raise PermissionError("No eres responsable de este caso")
    if caso["estado"] in ("homologado", "rechazado"):
        raise ValueError("El caso ya tiene una decisión terminal")
    if decision == "incompleta":
        pendientes = requisitos_pendientes or caso.get("requisitos") or []
        sb.table("supplier_homologation_cases").update({
            "estado": "requiere_aclaracion", "comentario_decision": comentario,
            "updated_at": _now(),
        }).eq("id", caso_id).execute()
        _cancelar_acciones(caso)
        instancia = ejecutar_maybe_single(sb.table("workflow_instances").select("*").eq(
            "id", caso["workflow_instance_id"]
        ).maybe_single()).data
        ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("*").eq(
            "id", caso["node_execution_id"]
        ).maybe_single()).data
        conv = ejecutar_maybe_single(sb.table("gmail_conversations").select("*").eq(
            "id", caso["conversation_id"]
        ).maybe_single()).data
        proveedor = ejecutar_maybe_single(sb.table("proveedores").select("nombre,email").eq(
            "id", caso["proveedor_id"]
        ).maybe_single()).data or {}
        org = resolver_organizacion(instancia["user_id"])
        _enviar_reservado(
            user_id=instancia["user_id"], org=org, evento="supplier_intake_missing_information",
            destinatario=conv.get("proveedor_email") or proveedor.get("email"),
            idempotency_key=f"supplier_intake_missing:{caso_id}:{len(caso.get('antecedentes_recibidos') or [])}",
            variables={"proveedor_nombre": proveedor.get("nombre") or "estimados",
                       "requisitos_pendientes": "\n".join(f"- {r}" for r in pendientes),
                       "comentario": comentario},
            workflow_id=instancia["workflow_id"], nodo_id=ejecucion["nodo_id"],
            proveedor_id=caso["proveedor_id"], conversation=conv,
        )
        reglas = _reglas(instancia["workflow_id"], ejecucion["nodo_id"])
        for regla in reglas:
            if regla.get("evento_plantilla") == "supplier_intake_followup":
                existentes = sb.table("workflow_scheduled_actions").select("attempt_number").eq(
                    "node_execution_id", ejecucion["id"]
                ).eq("communication_rule_id", regla["id"]).eq("recipient_key", caso_id).order(
                    "attempt_number", desc=True
                ).limit(1).execute().data or []
                intento = (existentes[0]["attempt_number"] + 1) if existentes else 1
                programar_accion(
                    node_execution_id=ejecucion["id"], instance_id=instancia["id"],
                    nodo_id=ejecucion["nodo_id"], visit_number=ejecucion["visit_number"],
                    communication_rule_id=regla["id"], recipient_key=caso_id,
                    due_at=proximo_vencimiento(datetime.now(timezone.utc), max(1, int(regla.get("repetir_cada_dias") or 1))),
                    attempt_number=intento,
                )
        return {"estado": "requiere_aclaracion", "resuelto": False}

    nuevo = decision
    sb.table("supplier_homologation_cases").update({
        "estado": nuevo, "comentario_decision": comentario,
        "decidido_por_user_id": actor_user_id, "decidido_at": _now(), "updated_at": _now(),
    }).eq("id", caso_id).execute()
    _cancelar_acciones(caso)
    ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("nodo_id").eq(
        "id", caso["node_execution_id"]
    ).maybe_single()).data or {}
    _evento(caso["workflow_instance_id"], ejecucion.get("nodo_id") or "",
            "proveedor_homologado" if decision == "homologado" else "proveedor_rechazado",
            f"homologation_decision:{caso_id}:{decision}", node_execution_id=caso["node_execution_id"],
            responsable_id=caso.get("responsable_id"), comentario=comentario)
    return {"estado": nuevo, **_resolver_agregado({**caso, "estado": nuevo})}
