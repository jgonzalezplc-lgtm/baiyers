"""
Workflow Builder — Fase 4 (ejecución real).

Conecta el motor puro de `workflow_engine.py` al flujo real de autorización
de listas (`listas.solicitar_aprobacion` / `aprobaciones.decidir`). No
reemplaza `approval_requests` como fuente del magic link — este módulo sólo
decide QUIÉN(es) deben recibir la solicitud según el ciclo activo del
usuario, y qué pasa cuando alguien decide.

Si el usuario no tiene ningún workflow `activo`, o el nodo de autorización
no tiene responsables asignados todavía, este módulo devuelve None y el
llamador cae al flujo legado (un solo `aprobador_email` escrito a mano) —
nunca rompe la compatibilidad existente.
"""
from typing import Optional

from app.services.workflow_engine import evaluar_condicion, resolver_autorizadores, siguiente_nodo
from app.services.supabase import ejecutar_maybe_single


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _index_nodos(nodos: list[dict]) -> dict[str, dict]:
    return {n["id"]: n for n in nodos if n.get("id")}


def obtener_workflow_activo(user_id: str) -> Optional[dict]:
    """El workflow activo más reciente de la organización. Si hay varios ciclos
    activos con nombres distintos, se usa el más recién activado — elegir
    cuál aplica por categoría/proyecto queda para una mejora futura."""
    from app.services.organizacion import ids_organizacion
    sb = _sb()
    rows = sb.table("workflow_definitions").select("*").in_("user_id", ids_organizacion(user_id)).eq(
        "estado", "activo"
    ).order("updated_at", desc=True).limit(1).execute().data or []
    return rows[0] if rows else None


def _responsables_para_roles(user_id: str, workflow_id: str, roles: list[str]) -> list[dict]:
    if not roles:
        return []
    sb = _sb()
    asignaciones = sb.table("responsable_roles").select(
        "rol_clave, orden_autorizacion, responsables(id, nombre, email, activo)"
    ).eq("workflow_id", workflow_id).in_("rol_clave", roles).execute().data or []
    responsables = []
    vistos = set()
    for a in asignaciones:
        r = a.get("responsables")
        if not r or not r.get("activo") or not r.get("email") or r["id"] in vistos:
            continue
        vistos.add(r["id"])
        responsables.append({
            "id": r["id"], "nombre": r["nombre"], "email": r["email"],
            "orden_autorizacion": a.get("orden_autorizacion"),
        })
    return responsables


def _monto_de_lista(lista_id: Optional[str]) -> float:
    if not lista_id:
        return 0
    from app.routers.listas import _monto_total, _parse_lista
    sb = _sb()
    proy = ejecutar_maybe_single(sb.table("proyectos").select("descripcion").eq("id", lista_id).maybe_single()).data
    data = _parse_lista(proy or {}) if proy else None
    return _monto_total(data) if data else 0


def _nodo_autorizacion_para_monto(nodos: list[dict], conexiones: list[dict], monto_total: float) -> Optional[dict]:
    """Camina el grafo desde 'inicio' por conexiones sin resultado (tareas
    intermedias tipo cotizar/revisar) hasta encontrar el primer nodo de
    autorización real para este monto. Si hay un nodo 'decision' de tramos
    (ver `compilar_a_grafo`), evalúa la condición de cada tramo candidato."""
    por_id = _index_nodos(nodos)
    actual_id = "inicio"
    visitados = set()
    while actual_id and actual_id not in visitados:
        visitados.add(actual_id)
        nodo = por_id.get(actual_id)
        if not nodo:
            return None
        if nodo["tipo"] == "autorizacion":
            return nodo
        if nodo["tipo"] == "decision":
            for c in conexiones:
                if c.get("origen_nodo_id") != actual_id:
                    continue
                candidato = por_id.get(c.get("destino_nodo_id"))
                if not candidato:
                    continue
                if evaluar_condicion(candidato.get("condicion_entrada"), {"monto_total": monto_total}):
                    return candidato
            return None
        if nodo["tipo"] == "fin":
            return None
        actual_id = siguiente_nodo(conexiones, actual_id)
    return None


def previsualizar_autorizadores(user_id: str, monto_total: float) -> Optional[dict]:
    """Solo lectura — para que el frontend muestre a quién le va a llegar la
    solicitud antes de enviarla, sin crear ninguna `workflow_instances`."""
    workflow = obtener_workflow_activo(user_id)
    if not workflow:
        return None
    nodos, conexiones = workflow.get("nodos") or [], workflow.get("conexiones") or []
    nodo = _nodo_autorizacion_para_monto(nodos, conexiones, monto_total)
    if not nodo:
        return None
    responsables = _responsables_para_roles(user_id, workflow["id"], nodo.get("roles") or [])
    if not responsables:
        return None
    return {
        "nodo_nombre": nodo.get("nombre") or nodo["id"],
        "modo_autorizacion": nodo.get("modo_autorizacion", "paralela"),
        "responsables": responsables,
    }


def iniciar_autorizacion_workflow(user_id: str, lista_id: str, monto_total: float) -> Optional[dict]:
    """Punto de entrada desde `solicitar_aprobacion`. Devuelve None si no hay
    workflow activo aplicable (el llamador usa el flujo legado). Si hay uno,
    crea la `workflow_instances` y devuelve a quién(es) hay que escribirles
    ahora mismo (respetando modo paralelo/secuencial)."""
    workflow = obtener_workflow_activo(user_id)
    if not workflow:
        return None

    nodos, conexiones = workflow.get("nodos") or [], workflow.get("conexiones") or []
    nodo = _nodo_autorizacion_para_monto(nodos, conexiones, monto_total)
    if not nodo:
        return None

    responsables = _responsables_para_roles(user_id, workflow["id"], nodo.get("roles") or [])
    if not responsables:
        return None  # nadie asignado todavía a ese rol — cae al flujo legado

    sb = _sb()
    instancia = sb.table("workflow_instances").insert({
        "user_id": user_id, "workflow_id": workflow["id"], "lista_proyecto_id": lista_id,
        "nodo_actual_id": nodo["id"], "estado_workflow": "activo",
    }).execute().data[0]

    nodo_con_responsables = {**nodo, "responsables": responsables}
    resolucion = resolver_autorizadores(nodo_con_responsables, {})
    pendientes_ids = set(resolucion["pendientes"])
    a_notificar = [r for r in responsables if r["id"] in pendientes_ids]

    return {
        "workflow_id": workflow["id"], "workflow_instance_id": instancia["id"],
        "nodo_id": nodo["id"], "nodo_nombre": nodo.get("nombre") or nodo["id"],
        "modo_autorizacion": nodo.get("modo_autorizacion", "paralela"),
        "responsables_todos": responsables, "responsables_a_notificar": a_notificar,
    }


def registrar_evento(instance_id: str, nodo_id: str, responsable_id: Optional[str], accion: str, actor_nombre: str = "") -> None:
    sb = _sb()
    sb.table("workflow_events").insert({
        "instance_id": instance_id, "nodo_id": nodo_id, "actor_responsable_id": responsable_id,
        "accion": accion, "canal": "email",
        "clave_idempotencia": f"{instance_id}:{nodo_id}:{responsable_id}:{accion}",
    }).execute()


def avanzar_tras_decision(approval_request: dict) -> dict:
    """Se llama desde `aprobaciones.decidir()` cuando la solicitud decidida
    pertenece a un workflow. Mira todas las solicitudes hermanas del mismo
    nodo/instancia para saber si ya se resolvió (todos decidieron, o hubo un
    rechazo), y si corresponde, resuelve a quién avisar en el siguiente nodo.

    Devuelve:
      resuelto: bool — si el nodo actual ya tiene un resultado definitivo.
      resultado: "aprobado" | "rechazado" | None
      terminado: bool — True si el workflow llegó a 'fin' (la lista queda
        aprobada de verdad); False si hay que notificar a un nodo siguiente.
      siguiente: dict | None — como `iniciar_autorizacion_workflow`, para el
        siguiente nodo de autorización si el workflow no terminó.
    """
    sb = _sb()
    instance_id = approval_request["workflow_instance_id"]
    nodo_id = approval_request["workflow_nodo_id"]

    instancia = sb.table("workflow_instances").select("*").eq("id", instance_id).single().execute().data
    workflow = sb.table("workflow_definitions").select("*").eq("id", instancia["workflow_id"]).single().execute().data
    nodos, conexiones = workflow.get("nodos") or [], workflow.get("conexiones") or []
    por_id = _index_nodos(nodos)
    nodo = por_id.get(nodo_id)

    hermanas = sb.table("approval_requests").select("responsable_id, estado").eq(
        "workflow_instance_id", instance_id
    ).eq("workflow_nodo_id", nodo_id).execute().data or []
    decisiones = {
        h["responsable_id"]: ("aprobado" if h["estado"] == "aprobado" else "rechazado")
        for h in hermanas if h["estado"] in ("aprobado", "rechazado") and h.get("responsable_id")
    }

    responsables_asignados = _responsables_para_roles(approval_request["user_id"], workflow["id"], nodo.get("roles") or [])
    nodo_con_responsables = {**nodo, "responsables": responsables_asignados}
    resolucion = resolver_autorizadores(nodo_con_responsables, decisiones)

    if not resolucion["resuelto"]:
        return {"resuelto": False, "resultado": None, "terminado": False, "siguiente": None}

    resultado = resolucion["resultado"]
    if resultado == "rechazado":
        sb.table("workflow_instances").update({"estado_workflow": "cancelado"}).eq("id", instance_id).execute()
        return {"resuelto": True, "resultado": "rechazado", "terminado": True, "siguiente": None}

    siguiente_id = siguiente_nodo(conexiones, nodo_id, "aprobado")
    siguiente_tipo = por_id.get(siguiente_id, {}).get("tipo") if siguiente_id else None

    if not siguiente_id or siguiente_tipo == "fin":
        sb.table("workflow_instances").update({"estado_workflow": "completado", "nodo_actual_id": siguiente_id or nodo_id}).eq("id", instance_id).execute()
        return {"resuelto": True, "resultado": "aprobado", "terminado": True, "siguiente": None}

    siguiente_nodo_obj = por_id.get(siguiente_id)
    if siguiente_nodo_obj and siguiente_nodo_obj["tipo"] == "decision":
        monto_total = _monto_de_lista(instancia.get("lista_proyecto_id"))
        siguiente_nodo_obj = _nodo_autorizacion_para_monto(nodos, conexiones, monto_total or 0) or siguiente_nodo_obj

    if not siguiente_nodo_obj or siguiente_nodo_obj["tipo"] != "autorizacion":
        # El siguiente paso no es una autorización más (ej: emisión de OC) —
        # para esta fase, eso ya no bloquea: la lista queda aprobada y el
        # flujo de compra existente sigue igual que siempre.
        sb.table("workflow_instances").update({"estado_workflow": "completado", "nodo_actual_id": siguiente_id}).eq("id", instance_id).execute()
        return {"resuelto": True, "resultado": "aprobado", "terminado": True, "siguiente": None}

    responsables_siguiente = _responsables_para_roles(approval_request["user_id"], workflow["id"], siguiente_nodo_obj.get("roles") or [])
    if not responsables_siguiente:
        # Nadie asignado al siguiente tramo — no dejar la lista atascada:
        # se da por aprobada tal como está y se registra la brecha.
        sb.table("workflow_instances").update({"estado_workflow": "completado", "nodo_actual_id": siguiente_id}).eq("id", instance_id).execute()
        return {"resuelto": True, "resultado": "aprobado", "terminado": True, "siguiente": None}

    sb.table("workflow_instances").update({"nodo_actual_id": siguiente_id}).eq("id", instance_id).execute()
    resolucion_siguiente = resolver_autorizadores({**siguiente_nodo_obj, "responsables": responsables_siguiente}, {})
    pendientes_ids = set(resolucion_siguiente["pendientes"])

    return {
        "resuelto": True, "resultado": "aprobado", "terminado": False,
        "siguiente": {
            "workflow_id": workflow["id"], "workflow_instance_id": instance_id,
            "nodo_id": siguiente_id, "nodo_nombre": siguiente_nodo_obj.get("nombre") or siguiente_id,
            "modo_autorizacion": siguiente_nodo_obj.get("modo_autorizacion", "paralela"),
            "responsables_todos": responsables_siguiente,
            "responsables_a_notificar": [r for r in responsables_siguiente if r["id"] in pendientes_ids],
        },
    }
