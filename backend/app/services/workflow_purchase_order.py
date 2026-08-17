"""Fase F: adaptador durable entre ordenes_compra, Gmail y workflow."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.services.supabase import ejecutar_maybe_single
from app.services.workflow_automation import proximo_vencimiento
from app.services.workflow_automation_service import obtener_o_crear_ejecucion_nodo, programar_accion


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _evento(instance_id: str, nodo_id: str, accion: str, clave: str, *,
            node_execution_id: Optional[str] = None,
            communication_rule_id: Optional[str] = None,
            referencia_externa: Optional[str] = None,
            comentario: Optional[str] = None) -> None:
    try:
        _sb().table("workflow_events").insert({
            "instance_id": instance_id, "nodo_id": nodo_id, "accion": accion,
            "canal": "email", "clave_idempotencia": clave,
            "node_execution_id": node_execution_id,
            "communication_rule_id": communication_rule_id,
            "referencia_externa": referencia_externa, "comentario": comentario,
        }).execute()
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate key" not in str(exc).lower():
            raise


def asegurar_contexto_oc(user_id: str, lista_id: Optional[str]) -> Optional[dict]:
    if not lista_id:
        return None
    sb = _sb()
    instancias = sb.table("workflow_instances").select("*").eq(
        "lista_proyecto_id", lista_id
    ).eq("execution_owner", "unified").eq("estado_workflow", "activo").order(
        "created_at", desc=True
    ).limit(1).execute().data or []
    if not instancias:
        return None
    instancia = instancias[0]
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("*").eq(
        "id", instancia["workflow_id"]
    ).maybe_single()).data
    nodo = next((n for n in (workflow.get("nodos") or []) if n.get("id") == instancia.get("nodo_actual_id")), None)
    if not nodo or nodo.get("tipo") != "emision_oc":
        return None
    ejecucion = obtener_o_crear_ejecucion_nodo(
        instancia["id"], nodo["id"], {"lista_id": lista_id},
    )
    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", workflow["id"]
    ).eq("nodo_id", nodo["id"]).eq("activa", True).execute().data or []
    _evento(instancia["id"], nodo["id"], "node_entered", f"node_entered:{ejecucion['id']}",
            node_execution_id=ejecucion["id"])
    return {"instancia": instancia, "workflow": workflow, "nodo": nodo,
            "ejecucion": ejecucion, "reglas": reglas}


def enlazar_oc(oc_id: str, lista_id: Optional[str], contexto: Optional[dict]) -> None:
    if not contexto:
        return
    _sb().table("ordenes_compra").update({
        "lista_proyecto_id": lista_id,
        "workflow_instance_id": contexto["instancia"]["id"],
        "node_execution_id": contexto["ejecucion"]["id"],
        "execution_owner": "unified",
    }).eq("id", oc_id).execute()


def contexto_de_oc(oc_id: str) -> Optional[dict]:
    sb = _sb()
    oc = ejecutar_maybe_single(sb.table("ordenes_compra").select("*").eq("id", oc_id).maybe_single()).data
    if not oc or oc.get("execution_owner") != "unified" or not oc.get("node_execution_id"):
        return None
    ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("*").eq(
        "id", oc["node_execution_id"]
    ).maybe_single()).data
    instancia = ejecutar_maybe_single(sb.table("workflow_instances").select("*").eq(
        "id", oc["workflow_instance_id"]
    ).maybe_single()).data
    if not ejecucion or not instancia:
        return None
    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", instancia["workflow_id"]
    ).eq("nodo_id", ejecucion["nodo_id"]).eq("activa", True).execute().data or []
    return {"oc": oc, "ejecucion": ejecucion, "instancia": instancia, "reglas": reglas}


def _programar_reglas(contexto: dict, evento: str) -> list[dict]:
    creadas = []
    for regla in contexto["reglas"]:
        if regla.get("evento_plantilla") != evento:
            continue
        dias = max(1, int(regla.get("demora_inicial_dias") or regla.get("repetir_cada_dias") or 1))
        accion = programar_accion(
            node_execution_id=contexto["ejecucion"]["id"],
            instance_id=contexto["instancia"]["id"], nodo_id=contexto["ejecucion"]["nodo_id"],
            visit_number=contexto["ejecucion"]["visit_number"],
            communication_rule_id=regla["id"], recipient_key=contexto["oc"]["id"],
            due_at=proximo_vencimiento(_now(), dias), attempt_number=1,
        )
        if accion:
            creadas.append(accion)
    return creadas


def registrar_oc_emitida(oc_id: str, gmail_message_id: Optional[str] = None) -> dict:
    contexto = contexto_de_oc(oc_id)
    if not contexto:
        return {"aplicada": False}
    _evento(
        contexto["instancia"]["id"], contexto["ejecucion"]["nodo_id"], "oc_emitida",
        f"oc_emitida:{oc_id}", node_execution_id=contexto["ejecucion"]["id"],
        referencia_externa=gmail_message_id,
    )
    acciones = _programar_reglas(contexto, "purchase_order_ack_reminder") if contexto["oc"].get("proveedor_email") else []
    return {"aplicada": True, "acciones": acciones}


def _cancelar_eventos(contexto: dict, eventos: list[str]) -> None:
    ids = [r["id"] for r in contexto["reglas"] if r.get("evento_plantilla") in eventos]
    if ids:
        _sb().table("workflow_scheduled_actions").update({
            "estado": "cancelada", "lease_token": None, "lease_until": None,
            "updated_at": _now().isoformat(),
        }).eq("node_execution_id", contexto["ejecucion"]["id"]).eq(
            "recipient_key", contexto["oc"]["id"]
        ).in_("communication_rule_id", ids).in_("estado", ["programada", "reservada"]).execute()


def registrar_acuse_oc(oc_id: str, fuente_id: str) -> dict:
    contexto = contexto_de_oc(oc_id)
    if not contexto:
        return {"aplicada": False}
    _cancelar_eventos(contexto, ["purchase_order_ack_reminder"])
    _evento(
        contexto["instancia"]["id"], contexto["ejecucion"]["nodo_id"],
        "oc_recepcion_confirmada", f"oc_ack:{oc_id}:{fuente_id}",
        node_execution_id=contexto["ejecucion"]["id"], referencia_externa=fuente_id,
    )
    if any(r.get("evento_plantilla") == "purchase_order_acknowledged_internal" for r in contexto["reglas"]):
        _avisar_interno(contexto, "purchase_order_acknowledged_internal", {
            "numero_oc": contexto["oc"].get("numero_oc") or "OC",
            "proveedor_nombre": contexto["oc"].get("proveedor_nombre") or "Proveedor",
        })
    return {"aplicada": True, "acciones": _programar_reglas(contexto, "dispatch_status_request")}


def _destinatarios_internos(contexto: dict) -> list[dict]:
    filas = _sb().table("workflow_node_assignments").select(
        "responsables(id,nombre,email,activo)"
    ).eq("workflow_id", contexto["instancia"]["workflow_id"]).eq(
        "nodo_id", contexto["ejecucion"]["nodo_id"]
    ).execute().data or []
    salida, vistos = [], set()
    for fila in filas:
        r = fila.get("responsables") or {}
        if r.get("activo") and r.get("email") and r["id"] not in vistos:
            vistos.add(r["id"]); salida.append(r)
    return salida


def _avisar_interno(contexto: dict, evento: str, variables: dict) -> int:
    from app.services.organizacion import resolver_organizacion
    from app.services.mail_template_service import render, reservar_envio, actualizar_entrega_reservada
    from app.services.gmail_service import get_gmail_service, send_email
    sb = _sb()
    instancia = contexto["instancia"]
    org = resolver_organizacion(instancia["user_id"])
    integration = ejecutar_maybe_single(sb.table("user_integrations").select("*").eq(
        "user_id", instancia["user_id"]
    ).eq("provider", "gmail").maybe_single()).data
    if not org or not integration:
        return 0
    service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
    enviados = 0
    for responsable in _destinatarios_internos(contexto):
        reserva = reservar_envio(
            org.organizacion_id, evento, responsable["email"],
            f"{evento}:{contexto['oc']['id']}:{responsable['id']}",
            workflow_id=instancia["workflow_id"], workflow_nodo_id=contexto["ejecucion"]["nodo_id"],
            responsable_id=responsable["id"],
        )
        if not reserva["adquirida"]:
            continue
        renderizado = render(evento, {"nombre_responsable": responsable.get("nombre") or responsable["email"], **variables},
                             organizacion_id=org.organizacion_id, workflow_id=instancia["workflow_id"],
                             nodo_id=contexto["ejecucion"]["nodo_id"])
        try:
            msg = send_email(service, responsable["email"], renderizado["subject"], renderizado["body"], integration["email"])
            actualizar_entrega_reservada(reserva["entrega"]["id"], reserva["reservation_token"], "enviado",
                                         gmail_message_id=msg.get("id"), gmail_thread_id=msg.get("threadId"))
            enviados += 1
        except Exception as exc:
            actualizar_entrega_reservada(reserva["entrega"]["id"], reserva["reservation_token"],
                                         "delivery_uncertain", error=str(exc))
    return enviados


def registrar_despacho_oc(oc_id: str, fuente_id: str, detalle: str = "") -> dict:
    contexto = contexto_de_oc(oc_id)
    if not contexto:
        return {"aplicada": False}
    _cancelar_eventos(contexto, ["purchase_order_ack_reminder", "dispatch_status_request"])
    _evento(
        contexto["instancia"]["id"], contexto["ejecucion"]["nodo_id"],
        "despacho_informado", f"oc_dispatch:{oc_id}:{fuente_id}",
        node_execution_id=contexto["ejecucion"]["id"], referencia_externa=fuente_id,
        comentario=detalle,
    )
    oc = contexto["oc"]
    if any(r.get("evento_plantilla") == "dispatch_notified_internal" for r in contexto["reglas"]):
        _avisar_interno(contexto, "dispatch_notified_internal", {
            "numero_oc": oc.get("numero_oc") or "OC",
            "proveedor_nombre": oc.get("proveedor_nombre") or "Proveedor",
            "detalle_despacho": detalle or "Sin detalle adicional",
        })
    sb = _sb()
    ejecucion, instancia = contexto["ejecucion"], contexto["instancia"]
    ordenes = sb.table("ordenes_compra").select("id,estado").eq(
        "node_execution_id", ejecucion["id"]
    ).execute().data or []
    pendientes = [orden for orden in ordenes if orden.get("estado") != "despachada"]
    if pendientes:
        return {
            "aplicada": True,
            "resuelto": False,
            "ordenes_pendientes": len(pendientes),
        }
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("conexiones,nodos").eq(
        "id", instancia["workflow_id"]
    ).maybe_single()).data or {}
    from app.services.workflow_engine import siguiente_nodo
    siguiente = siguiente_nodo(workflow.get("conexiones") or [], ejecucion["nodo_id"], "despacho_informado")
    if not siguiente:
        siguiente = siguiente_nodo(workflow.get("conexiones") or [], ejecucion["nodo_id"])
    siguiente_tipo = next((n.get("tipo") for n in workflow.get("nodos") or [] if n.get("id") == siguiente), None)
    sb.table("workflow_node_executions").update({
        "estado": "completada", "resultado": "despacho_informado",
        "completed_at": _now().isoformat(), "updated_at": _now().isoformat(),
    }).eq("id", ejecucion["id"]).execute()
    sb.table("workflow_instances").update({
        "nodo_actual_id": siguiente or ejecucion["nodo_id"],
        "estado_workflow": "completado" if not siguiente or siguiente_tipo == "fin" else "activo",
        "updated_at": _now().isoformat(),
    }).eq("id", instancia["id"]).execute()
    _evento(instancia["id"], ejecucion["nodo_id"], "node_completed",
            f"node_completed:{ejecucion['id']}:despacho_informado", node_execution_id=ejecucion["id"])
    return {"aplicada": True, "resuelto": True, "siguiente_nodo_id": siguiente,
            "workflow_completado": not siguiente or siguiente_tipo == "fin"}


def avisar_oc_emitida_interno(oc_id: str) -> int:
    contexto = contexto_de_oc(oc_id)
    if not contexto or not any(r.get("evento_plantilla") == "purchase_order_internal_copy" for r in contexto["reglas"]):
        return 0
    oc = contexto["oc"]
    return _avisar_interno(contexto, "purchase_order_internal_copy", {
        "numero_oc": oc.get("numero_oc") or "OC", "proveedor_nombre": oc.get("proveedor_nombre") or "Proveedor",
        "monto": f"${int(oc.get('precio_total') or 0):,}".replace(",", "."), "moneda": oc.get("moneda") or "CLP",
    })
