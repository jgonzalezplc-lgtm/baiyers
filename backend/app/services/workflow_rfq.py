"""Adaptador Fase D entre rfq_batches, Gmail y el workflow unificado."""
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
            comentario: Optional[str] = None,
            referencia_externa: Optional[str] = None) -> None:
    try:
        _sb().table("workflow_events").insert({
            "instance_id": instance_id, "nodo_id": nodo_id, "accion": accion,
            "canal": "email", "clave_idempotencia": clave,
            "node_execution_id": node_execution_id,
            "communication_rule_id": communication_rule_id,
            "comentario": comentario, "referencia_externa": referencia_externa,
        }).execute()
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate key" not in str(exc).lower():
            raise


def _nodo_rfq(workflow: dict, reglas: list[dict]) -> Optional[dict]:
    ids = {r["nodo_id"] for r in reglas if r.get("evento_plantilla") in {"rfq_requested", "rfq_followup"}}
    return next((n for n in (workflow.get("nodos") or []) if n.get("id") in ids), None)


def asegurar_contexto_rfq(user_id: str, lista_id: str) -> Optional[dict]:
    """Opt-in: sólo activa Fase D si el workflow activo tiene regla RFQ."""
    from app.services.workflow_execution import obtener_workflow_activo
    workflow = obtener_workflow_activo(user_id)
    if not workflow:
        return None
    from app.services.workflow_rollout import motor_unificado_habilitado
    if not motor_unificado_habilitado(user_id):
        return None
    sb = _sb()
    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", workflow["id"]
    ).eq("activa", True).in_("evento_plantilla", ["rfq_requested", "rfq_followup"]).execute().data or []
    nodo = _nodo_rfq(workflow, reglas)
    if not nodo:
        return None
    existentes = sb.table("workflow_instances").select("*").eq(
        "workflow_id", workflow["id"]
    ).eq("lista_proyecto_id", lista_id).eq("execution_owner", "unified").in_(
        "estado_workflow", ["activo", "pausado"]
    ).order("created_at", desc=True).limit(1).execute().data or []
    if existentes:
        instancia = existentes[0]
        if instancia.get("nodo_actual_id") != nodo["id"]:
            sb.table("workflow_instances").update({"nodo_actual_id": nodo["id"]}).eq("id", instancia["id"]).execute()
    else:
        instancia = sb.table("workflow_instances").insert({
            "user_id": user_id, "workflow_id": workflow["id"],
            "lista_proyecto_id": lista_id, "nodo_actual_id": nodo["id"],
            "estado_workflow": "activo", "workflow_version": workflow.get("version"),
            "execution_owner": "unified",
        }).execute().data[0]
    criterio = nodo.get("criterio_cierre") or "todos_resueltos"
    minimo = max(1, int(nodo.get("minimo_respuestas") or 1))
    regla_cierre = next((r for r in reglas if r.get("evento_plantilla") == "rfq_followup"), None) or {}
    resultado_cierre = regla_cierre.get("resultado_al_terminar") or "cotizaciones_recibidas"
    ejecucion = obtener_o_crear_ejecucion_nodo(instancia["id"], nodo["id"], {
        "lista_id": lista_id, "criterio_cierre": criterio, "minimo_respuestas": minimo,
        "resultado_cierre": resultado_cierre,
    })
    _evento(instancia["id"], nodo["id"], "node_entered", f"node_entered:{ejecucion['id']}",
            node_execution_id=ejecucion["id"])
    # Todos los proveedores preparados forman el agregado, incluso si sus
    # correos se envían uno a uno. Así la primera respuesta no puede cerrar
    # prematuramente una tarjeta con otros drafts pendientes.
    sb.table("rfq_batches").update({
        "workflow_instance_id": instancia["id"], "node_execution_id": ejecucion["id"],
        "execution_owner": "unified", "updated_at": _now().isoformat(),
    }).eq("lista_proyecto_id", lista_id).in_(
        "estado", ["draft", "ready_to_send", "failed", "sending", "sent"]
    ).execute()
    return {"workflow": workflow, "instancia": instancia, "ejecucion": ejecucion,
            "nodo": nodo, "reglas": reglas, "criterio_cierre": criterio,
            "minimo_respuestas": minimo}


def enlazar_batch(batch_id: str, contexto: dict) -> None:
    _sb().table("rfq_batches").update({
        "workflow_instance_id": contexto["instancia"]["id"],
        "node_execution_id": contexto["ejecucion"]["id"],
        "execution_owner": "unified", "resolution_state": "pendiente",
        "updated_at": _now().isoformat(),
    }).eq("id", batch_id).execute()


def programar_followups(batch: dict, contexto: dict, *, attempt_number: int = 1) -> list[dict]:
    creadas = []
    for regla in contexto["reglas"]:
        if regla.get("evento_plantilla") != "rfq_followup":
            continue
        dias = max(1, int(regla.get("demora_inicial_dias") or regla.get("repetir_cada_dias") or 1))
        accion = programar_accion(
            node_execution_id=contexto["ejecucion"]["id"],
            instance_id=contexto["instancia"]["id"], nodo_id=contexto["nodo"]["id"],
            visit_number=contexto["ejecucion"]["visit_number"],
            communication_rule_id=regla["id"], recipient_key=batch["id"],
            due_at=proximo_vencimiento(_now(), dias), attempt_number=attempt_number,
        )
        if accion:
            creadas.append(accion)
    return creadas


def registrar_envio_inicial(batch_id: str, contexto: dict, gmail_message_id: Optional[str]) -> None:
    regla = next((r for r in contexto["reglas"] if r.get("evento_plantilla") == "rfq_requested"), None)
    _evento(
        contexto["instancia"]["id"], contexto["nodo"]["id"], "mail_sent",
        f"rfq_initial_sent:{batch_id}", node_execution_id=contexto["ejecucion"]["id"],
        communication_rule_id=(regla or {}).get("id"), referencia_externa=gmail_message_id,
    )


def _cancelar_batch(batch: dict) -> None:
    _sb().table("workflow_scheduled_actions").update({
        "estado": "cancelada", "lease_token": None, "lease_until": None,
        "updated_at": _now().isoformat(),
    }).eq("node_execution_id", batch["node_execution_id"]).eq(
        "recipient_key", batch["id"]
    ).in_("estado", ["programada", "reservada"]).execute()


def _evaluar_cierre(batch: dict, *, forzar_manual: bool = False) -> dict:
    sb = _sb()
    ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("*").eq(
        "id", batch["node_execution_id"]
    ).maybe_single()).data
    if not ejecucion or ejecucion.get("estado") not in ("activa", "esperando"):
        return {"cerrada": False}
    batches = sb.table("rfq_batches").select("id,resolution_state").eq(
        "node_execution_id", ejecucion["id"]
    ).execute().data or []
    ctx = ejecucion.get("context_snapshot") or {}
    criterio = ctx.get("criterio_cierre") or "todos_resueltos"
    resultado_cierre = ctx.get("resultado_cierre") or "cotizaciones_recibidas"
    completas = sum(1 for b in batches if b.get("resolution_state") == "completa")
    resueltas = sum(1 for b in batches if b.get("resolution_state") in ("completa", "descartada"))
    cerrada = (
        criterio == "todos_resueltos" and bool(batches) and resueltas == len(batches)
    ) or (
        criterio == "minimo_respuestas" and completas >= int(ctx.get("minimo_respuestas") or 1)
    )
    if forzar_manual and criterio == "cierre_manual":
        cerrada = True
    if (criterio == "cierre_manual" and not forzar_manual) or not cerrada:
        return {"cerrada": False, "criterio": criterio, "completas": completas, "resueltas": resueltas}

    instancia = ejecutar_maybe_single(sb.table("workflow_instances").select("*").eq(
        "id", ejecucion["instance_id"]
    ).maybe_single()).data
    if completas == 0 and not forzar_manual:
        sb.table("workflow_node_executions").update({
            "estado": "pausada", "resultado": "sin_cotizaciones",
            "updated_at": _now().isoformat(),
        }).eq("id", ejecucion["id"]).execute()
        sb.table("workflow_instances").update({
            "estado_workflow": "pausado", "updated_at": _now().isoformat(),
        }).eq("id", instancia["id"]).execute()
        _evento(instancia["id"], ejecucion["nodo_id"], "loop_exhausted",
                f"rfq_all_discarded:{ejecucion['id']}", node_execution_id=ejecucion["id"],
                comentario="Todos los proveedores fueron descartados sin cotización completa")
        return {"cerrada": False, "pausada": True, "criterio": criterio,
                "completas": completas, "resueltas": resueltas}
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("*").eq(
        "id", instancia["workflow_id"]
    ).maybe_single()).data
    sb.table("workflow_scheduled_actions").update({
        "estado": "cancelada", "lease_token": None, "lease_until": None,
        "updated_at": _now().isoformat(),
    }).eq("node_execution_id", ejecucion["id"]).in_(
        "estado", ["programada", "reservada"]
    ).execute()
    from app.services.workflow_engine import siguiente_nodo
    siguiente = siguiente_nodo(workflow.get("conexiones") or [], ejecucion["nodo_id"], resultado_cierre)
    if not siguiente:
        siguiente = siguiente_nodo(workflow.get("conexiones") or [], ejecucion["nodo_id"])
    sb.table("workflow_node_executions").update({
        "estado": "completada", "resultado": resultado_cierre,
        "completed_at": _now().isoformat(), "updated_at": _now().isoformat(),
    }).eq("id", ejecucion["id"]).eq("estado", ejecucion["estado"]).execute()
    sb.table("workflow_instances").update({
        "nodo_actual_id": siguiente or ejecucion["nodo_id"], "updated_at": _now().isoformat(),
    }).eq("id", instancia["id"]).execute()
    _evento(instancia["id"], ejecucion["nodo_id"], "node_completed",
            f"node_completed:{ejecucion['id']}:{resultado_cierre}",
            node_execution_id=ejecucion["id"], comentario=criterio)
    if siguiente:
        _evento(instancia["id"], siguiente, "transition_applied",
                f"transition:{ejecucion['id']}:{resultado_cierre}:{siguiente}",
                node_execution_id=ejecucion["id"])
    return {"cerrada": True, "criterio": criterio, "siguiente_nodo_id": siguiente,
            "completas": completas, "resueltas": resueltas}


def registrar_respuesta_rfq(conversation_id: str, gmail_message_id: str, *, completa: bool) -> dict:
    """Normaliza una respuesta Gmail; idempotente por message id + batch."""
    sb = _sb()
    rows = sb.table("rfq_batches").select("*").eq("conversation_id", conversation_id).eq(
        "execution_owner", "unified"
    ).limit(1).execute().data or []
    if not rows:
        return {"aplicada": False, "motivo": "rfq_legacy_o_sin_batch"}
    batch = rows[0]
    instancia_id = batch["workflow_instance_id"]
    ejecucion = ejecutar_maybe_single(sb.table("workflow_node_executions").select("nodo_id").eq(
        "id", batch["node_execution_id"]
    ).maybe_single()).data or {}
    _evento(instancia_id, ejecucion.get("nodo_id") or "", "rfq_respuesta_recibida",
            f"gmail:{gmail_message_id}:rfq_respuesta_recibida:{batch['id']}",
            node_execution_id=batch["node_execution_id"], referencia_externa=gmail_message_id)
    if not completa:
        return {"aplicada": True, "completa": False, **_evaluar_cierre(batch)}
    sb.table("rfq_batches").update({
        "resolution_state": "completa", "resolved_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }).eq("id", batch["id"]).execute()
    _cancelar_batch(batch)
    _evento(instancia_id, ejecucion.get("nodo_id") or "", "rfq_completa",
            f"gmail:{gmail_message_id}:rfq_completa:{batch['id']}",
            node_execution_id=batch["node_execution_id"], referencia_externa=gmail_message_id)
    return {"aplicada": True, "completa": True, **_evaluar_cierre(batch)}


def descartar_batch_por_agotamiento(batch: dict, regla: dict) -> dict:
    sb = _sb()
    sb.table("rfq_batches").update({
        "resolution_state": "descartada", "resolved_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }).eq("id", batch["id"]).execute()
    _cancelar_batch(batch)
    _evento(batch["workflow_instance_id"], "", "proveedor_descartado",
            f"rfq_exhausted:{batch['id']}:{regla['id']}",
            node_execution_id=batch["node_execution_id"], communication_rule_id=regla["id"],
            comentario="sin_respuesta")
    return _evaluar_cierre({**batch, "resolution_state": "descartada"})


def cerrar_rfq_manualmente(user_id: str, instance_id: str) -> dict:
    from app.services.organizacion import ids_organizacion
    sb = _sb()
    instancia = ejecutar_maybe_single(sb.table("workflow_instances").select("*").eq(
        "id", instance_id
    ).in_("user_id", ids_organizacion(user_id)).maybe_single()).data
    if not instancia:
        raise ValueError("Instancia no encontrada")
    ejecuciones = sb.table("workflow_node_executions").select("*").eq(
        "instance_id", instance_id
    ).in_("estado", ["activa", "esperando"]).order("visit_number", desc=True).limit(1).execute().data or []
    if not ejecuciones:
        raise ValueError("No hay una tarjeta RFQ activa")
    ejecucion = ejecuciones[0]
    snapshot = ejecucion.get("context_snapshot") or {}
    if snapshot.get("criterio_cierre") != "cierre_manual":
        raise ValueError("La tarjeta no está configurada con cierre manual")
    batches = sb.table("rfq_batches").select("*").eq("node_execution_id", ejecucion["id"]).limit(1).execute().data or []
    if not batches:
        raise ValueError("No hay RFQ asociadas a la tarjeta")
    return _evaluar_cierre(batches[0], forzar_manual=True)
