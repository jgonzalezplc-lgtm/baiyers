"""Persistencia base de la automatización por tarjeta (PRD Fase A).

No ejecuta correos ni conecta el cron. Expone operaciones pequeñas para que
las fases siguientes no repitan consultas ni claves idempotentes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.services.workflow_automation import clave_idempotencia
from app.services.supabase import ejecutar_maybe_single


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def listar_configuracion_nodo(workflow_id: str, nodo_id: str) -> dict:
    sb = _sb()
    asignaciones = sb.table("workflow_node_assignments").select(
        "*, responsables(id,nombre,cargo,email,activo,usuario_baiyer_id)"
    ).eq("workflow_id", workflow_id).eq("nodo_id", nodo_id).execute().data or []
    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", workflow_id
    ).eq("nodo_id", nodo_id).order("created_at").execute().data or []
    return {"asignaciones": asignaciones, "reglas": reglas}


def _workflow_editable(user_id: str, workflow_id: str) -> dict:
    from app.services.organizacion import ids_organizacion
    workflow = ejecutar_maybe_single(
        _sb().table("workflow_definitions").select("id,estado,nodos,conexiones").eq(
            "id", workflow_id
        ).in_("user_id", ids_organizacion(user_id)).maybe_single()
    ).data
    if not workflow:
        raise ValueError("Workflow no encontrado")
    if workflow.get("estado") != "borrador":
        raise ValueError("Solo se puede configurar una versión en borrador")
    return workflow


def listar_configuracion_workflow(user_id: str, workflow_id: str) -> dict:
    from app.services.organizacion import ids_organizacion
    workflow = ejecutar_maybe_single(
        _sb().table("workflow_definitions").select("id").eq("id", workflow_id).in_(
            "user_id", ids_organizacion(user_id)
        ).maybe_single()
    ).data
    if not workflow:
        raise ValueError("Workflow no encontrado")
    sb = _sb()
    asignaciones = sb.table("workflow_node_assignments").select(
        "*, responsables(id,nombre,cargo,email,activo,usuario_baiyer_id)"
    ).eq("workflow_id", workflow_id).execute().data or []
    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", workflow_id
    ).order("created_at").execute().data or []
    return {"asignaciones": asignaciones, "reglas": reglas}


def asignar_responsable_nodo(user_id: str, workflow_id: str, nodo_id: str,
                             rol_clave: str, responsable_id: str,
                             modo: str = "individual", orden: Optional[int] = None,
                             es_propietario_excepcion: bool = False) -> dict:
    workflow = _workflow_editable(user_id, workflow_id)
    nodo = next((n for n in (workflow.get("nodos") or []) if n.get("id") == nodo_id), None)
    if not nodo:
        raise ValueError("Tarjeta no encontrada")
    if rol_clave not in (nodo.get("roles") or []):
        raise ValueError("El rol no participa en esta tarjeta")
    from app.services.organizacion import ids_organizacion
    responsable = ejecutar_maybe_single(
        _sb().table("responsables").select("id,activo").eq("id", responsable_id).in_(
            "user_id", ids_organizacion(user_id)
        ).maybe_single()
    ).data
    if not responsable or not responsable.get("activo"):
        raise ValueError("Responsable activo no encontrado")
    if modo not in {"individual", "paralelo", "secuencial"}:
        raise ValueError("Modo de asignación inválido")
    if modo == "secuencial" and (not isinstance(orden, int) or orden < 1):
        raise ValueError("El modo secuencial requiere un orden mayor o igual a 1")
    if modo != "secuencial":
        orden = None

    sb = _sb()
    existentes = sb.table("workflow_node_assignments").select("id,responsable_id,created_at").eq(
        "workflow_id", workflow_id
    ).eq("nodo_id", nodo_id).eq("rol_clave", rol_clave).order("created_at").execute().data or []
    if modo == "individual":
        sb.table("workflow_node_assignments").delete().eq("workflow_id", workflow_id).eq(
            "nodo_id", nodo_id
        ).eq("rol_clave", rol_clave).execute()
    elif modo == "paralelo":
        for fila in existentes:
            sb.table("workflow_node_assignments").update({"modo": "paralelo", "orden": None}).eq("id", fila["id"]).execute()
    else:
        for indice, fila in enumerate(existentes, start=1):
            sb.table("workflow_node_assignments").update({"modo": "secuencial", "orden": indice}).eq("id", fila["id"]).execute()
        orden = len(existentes) + 1
    payload = {
        "workflow_id": workflow_id, "nodo_id": nodo_id, "rol_clave": rol_clave,
        "responsable_id": responsable_id, "modo": modo, "orden": orden,
        "es_propietario_excepcion": es_propietario_excepcion,
    }
    ins = sb.table("workflow_node_assignments").upsert(
        payload, on_conflict="workflow_id,nodo_id,rol_clave,responsable_id"
    ).execute()
    return ins.data[0]


def quitar_responsable_nodo(user_id: str, workflow_id: str, assignment_id: str) -> None:
    _workflow_editable(user_id, workflow_id)
    _sb().table("workflow_node_assignments").delete().eq("id", assignment_id).eq(
        "workflow_id", workflow_id
    ).execute()


def guardar_regla_comunicacion(user_id: str, workflow_id: str, nodo_id: str,
                               datos: dict, rule_id: Optional[str] = None) -> dict:
    workflow = _workflow_editable(user_id, workflow_id)
    if not any(n.get("id") == nodo_id for n in (workflow.get("nodos") or [])):
        raise ValueError("Tarjeta no encontrada")
    from app.services.mail_events import EVENTOS
    evento = datos.get("evento_plantilla")
    if evento not in EVENTOS:
        raise ValueError("Evento de plantilla desconocido")
    datos = {**datos, "audiencia": EVENTOS[evento].audiencia}
    campos = {
        "rol_clave", "evento_plantilla", "audiencia", "canal", "destinatario_tipo",
        "disparador_tipo", "disparador_evento", "demora_inicial_dias",
        "repetir_cada_dias", "max_intentos", "evento_termino", "alcance_termino",
        "resultado_al_terminar", "politica_agotamiento", "resultado_agotamiento", "activa",
    }
    payload = {k: v for k, v in datos.items() if k in campos}
    payload.update({"workflow_id": workflow_id, "nodo_id": nodo_id})
    from app.services.workflow_automation import validar_automatizacion
    regla_validacion = {**payload, "id": "__nueva__"}
    errores = [
        e for e in validar_automatizacion(
            workflow.get("nodos") or [], workflow.get("conexiones") or [], [], [regla_validacion]
        ) if e.get("regla_id") == "__nueva__"
    ]
    if errores:
        raise ValueError(errores[0]["mensaje"])
    sb = _sb()
    if rule_id:
        existente = ejecutar_maybe_single(
            sb.table("workflow_node_communication_rules").select("id").eq("id", rule_id).eq(
                "workflow_id", workflow_id
            ).maybe_single()
        ).data
        if not existente:
            raise ValueError("Regla no encontrada")
        from datetime import datetime, timezone
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = sb.table("workflow_node_communication_rules").update(payload).eq("id", rule_id).execute()
    else:
        resp = sb.table("workflow_node_communication_rules").insert(payload).execute()
    return resp.data[0]


def eliminar_regla_comunicacion(user_id: str, workflow_id: str, rule_id: str) -> None:
    _workflow_editable(user_id, workflow_id)
    _sb().table("workflow_node_communication_rules").delete().eq("id", rule_id).eq(
        "workflow_id", workflow_id
    ).execute()


def crear_ejecucion_nodo(instance_id: str, nodo_id: str, visit_number: int,
                          context_snapshot: Optional[dict] = None) -> dict:
    ins = _sb().table("workflow_node_executions").insert({
        "instance_id": instance_id,
        "nodo_id": nodo_id,
        "visit_number": visit_number,
        "estado": "activa",
        "context_snapshot": context_snapshot or {},
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return ins.data[0]


def obtener_o_crear_ejecucion_nodo(instance_id: str, nodo_id: str,
                                    context_snapshot: Optional[dict] = None) -> dict:
    sb = _sb()
    existentes = sb.table("workflow_node_executions").select("*").eq(
        "instance_id", instance_id
    ).eq("nodo_id", nodo_id).order("visit_number", desc=True).limit(1).execute().data or []
    if existentes and existentes[0].get("estado") in ("activa", "esperando"):
        return existentes[0]
    visit_number = (existentes[0].get("visit_number", 0) + 1) if existentes else 1
    return crear_ejecucion_nodo(instance_id, nodo_id, visit_number, context_snapshot)


def programar_accion(*, node_execution_id: str, instance_id: str, nodo_id: str,
                     visit_number: int, communication_rule_id: str,
                     recipient_key: str, due_at: datetime,
                     attempt_number: int = 1) -> dict:
    idem = clave_idempotencia(
        instance_id=instance_id, nodo_id=nodo_id, visit_number=visit_number,
        rule_id=communication_rule_id, recipient_key=recipient_key,
        attempt_number=attempt_number,
    )
    payload = {
        "node_execution_id": node_execution_id,
        "communication_rule_id": communication_rule_id,
        "recipient_key": recipient_key,
        "due_at": due_at.isoformat(),
        "attempt_number": attempt_number,
        "idempotency_key": idem,
    }
    try:
        return _sb().table("workflow_scheduled_actions").insert(payload).execute().data[0]
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate key" not in str(exc).lower():
            raise
        rows = _sb().table("workflow_scheduled_actions").select("*").eq(
            "idempotency_key", idem
        ).limit(1).execute().data or []
        return rows[0] if rows else {}


def reservar_accion(action_id: str, lease_seconds: int = 300) -> Optional[dict]:
    """Adquiere una acción vencida usando la RPC atómica de la migración 041."""
    token = str(uuid4())
    resp = _sb().rpc("claim_workflow_scheduled_action", {
        "p_action_id": action_id,
        "p_lease_token": token,
        "p_lease_seconds": lease_seconds,
    }).execute()
    rows = resp.data or []
    return rows[0] if rows else None
