"""
Persistencia de workflows de compras (Fase 1 — fundación). Guarda y valida
borradores; no ejecuta nada real todavía (eso es una fase posterior, y ni
siquiera entonces reemplaza `aprobaciones.py` — lo decora).
"""
from datetime import datetime, timezone
from typing import Optional

from app.services.workflow_engine import ROLES_BASE, validar_grafo
from app.services.supabase import ejecutar_maybe_single


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ids_organizacion(user_id: str) -> list[str]:
    from app.services.organizacion import ids_organizacion
    return ids_organizacion(user_id)


def crear_borrador(
    user_id: str, nombre: str, nodos: list[dict], conexiones: list[dict],
    origen: str = "visual", roles: Optional[list[dict]] = None,
) -> dict:
    sb = _sb()
    ins = sb.table("workflow_definitions").insert({
        "user_id": user_id, "nombre": nombre, "version": 1, "estado": "borrador",
        "origen": origen, "nodos": nodos, "conexiones": conexiones,
    }).execute()
    workflow = ins.data[0]

    for rol in (roles or [{"clave": r, "nombre": r.capitalize()} for r in sorted(ROLES_BASE)]):
        sb.table("workflow_roles").insert({
            "workflow_id": workflow["id"],
            "clave": rol["clave"], "nombre": rol["nombre"], "descripcion": rol.get("descripcion"),
        }).execute()

    return obtener_workflow(user_id, workflow["id"])


def crear_version_borrador(user_id: str, workflow_id: str, nodos: list[dict],
                           conexiones: list[dict]) -> dict:
    """Clona una definición activa/archivada a una nueva versión editable.

    `nodos` y `conexiones` vienen del canvas para conservar también los cambios
    locales propuestos por el chat antes de que el usuario recargue la página.
    Las instancias existentes continúan fijadas a la versión anterior.
    """
    sb = _sb()
    origen = obtener_workflow(user_id, workflow_id)
    if not origen:
        raise ValueError("Workflow no encontrado")
    if origen.get("estado") == "borrador":
        return origen

    versiones = sb.table("workflow_definitions").select("version").in_(
        "user_id", _ids_organizacion(user_id)
    ).eq("nombre", origen["nombre"]).execute().data or []
    siguiente_version = max([int(v.get("version") or 1) for v in versiones] or [0]) + 1
    nueva = sb.table("workflow_definitions").insert({
        "user_id": user_id,
        "nombre": origen["nombre"],
        "version": siguiente_version,
        "estado": "borrador",
        "origen": "mixto",
        "nodos": nodos,
        "conexiones": conexiones,
        "creado_por": user_id,
    }).execute().data[0]
    nuevo_id = nueva["id"]

    for rol in origen.get("roles") or []:
        sb.table("workflow_roles").insert({
            "workflow_id": nuevo_id, "clave": rol["clave"],
            "nombre": rol["nombre"], "descripcion": rol.get("descripcion"),
        }).execute()
    for asignacion in origen.get("responsables") or []:
        sb.table("responsable_roles").insert({
            "workflow_id": nuevo_id,
            "responsable_id": asignacion["responsable_id"],
            "rol_clave": asignacion["rol_clave"],
            "orden_autorizacion": asignacion.get("orden_autorizacion"),
        }).execute()

    nodos_validos = {n.get("id") for n in nodos if n.get("id")}
    asignaciones = sb.table("workflow_node_assignments").select("*").eq(
        "workflow_id", workflow_id
    ).execute().data or []
    for fila in asignaciones:
        if fila.get("nodo_id") not in nodos_validos:
            continue
        sb.table("workflow_node_assignments").insert({
            "workflow_id": nuevo_id, "nodo_id": fila["nodo_id"],
            "rol_clave": fila["rol_clave"], "responsable_id": fila["responsable_id"],
            "modo": fila["modo"], "orden": fila.get("orden"),
            "es_propietario_excepcion": fila.get("es_propietario_excepcion", False),
        }).execute()

    reglas = sb.table("workflow_node_communication_rules").select("*").eq(
        "workflow_id", workflow_id
    ).execute().data or []
    campos_regla = {
        "nodo_id", "rol_clave", "evento_plantilla", "audiencia", "canal",
        "destinatario_tipo", "disparador_tipo", "disparador_evento",
        "demora_inicial_dias", "repetir_cada_dias", "max_intentos",
        "evento_termino", "alcance_termino", "resultado_al_terminar",
        "politica_agotamiento", "resultado_agotamiento", "activa",
    }
    for fila in reglas:
        if fila.get("nodo_id") not in nodos_validos:
            continue
        sb.table("workflow_node_communication_rules").insert({
            "workflow_id": nuevo_id,
            **{campo: fila.get(campo) for campo in campos_regla},
        }).execute()
    return obtener_workflow(user_id, nuevo_id)


def actualizar_borrador(user_id: str, workflow_id: str, nodos: list[dict], conexiones: list[dict], nombre: Optional[str] = None) -> dict:
    sb = _sb()
    existente = ejecutar_maybe_single(sb.table("workflow_definitions").select("id,estado").eq("id", workflow_id).eq("user_id", user_id).maybe_single()).data
    if not existente:
        raise ValueError("Workflow no encontrado")
    if existente["estado"] != "borrador":
        raise ValueError("Solo se puede editar un workflow en estado 'borrador' — activa una nueva versión para modificarlo")

    cambios = {"nodos": nodos, "conexiones": conexiones, "updated_at": _now()}
    if nombre:
        cambios["nombre"] = nombre
    sb.table("workflow_definitions").update(cambios).eq("id", workflow_id).execute()
    return obtener_workflow(user_id, workflow_id)


def listar_workflows(user_id: str) -> list[dict]:
    sb = _sb()
    return sb.table("workflow_definitions").select(
        "id,nombre,version,estado,origen,created_at,updated_at"
    ).in_("user_id", _ids_organizacion(user_id)).order("created_at", desc=True).execute().data or []


def obtener_workflow(user_id: str, workflow_id: str) -> Optional[dict]:
    sb = _sb()
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("*").eq("id", workflow_id).in_(
        "user_id", _ids_organizacion(user_id)
    ).maybe_single()).data
    if not workflow:
        return None
    roles = sb.table("workflow_roles").select("*").eq("workflow_id", workflow_id).execute().data or []
    responsables = sb.table("responsable_roles").select(
        "*, responsables(id,nombre,cargo,email,telefono,activo,usuario_baiyer_id)"
    ).eq("workflow_id", workflow_id).execute().data or []

    # Roster: ¿cada responsable ya aceptó su invitación o sigue pendiente?
    # "sin_vincular" no necesita llamar a Supabase Auth (nunca se invitó).
    from app.services.organizacion import estado_onboarding_de_usuarios
    ids_vinculados = [
        r["responsables"]["usuario_baiyer_id"]
        for r in responsables if r.get("responsables") and r["responsables"].get("usuario_baiyer_id")
    ]
    estados = estado_onboarding_de_usuarios(ids_vinculados)
    for r in responsables:
        resp = r.get("responsables") or {}
        uid = resp.get("usuario_baiyer_id")
        resp["estado_onboarding"] = estados.get(uid, "invitacion_pendiente") if uid else "sin_vincular"

    return {**workflow, "roles": roles, "responsables": responsables}


def eliminar_workflow(user_id: str, workflow_id: str) -> None:
    """Borra un ciclo (borrador o archivado). Nunca borra el ciclo activo —
    la organización no puede quedarse sin ninguno por accidente; hay que
    activar un reemplazo primero. `responsable_roles` de este workflow se
    borran solos por ON DELETE CASCADE (migración 027); los `responsables`
    (personas) no se tocan, son de la organización, no del workflow."""
    sb = _sb()
    workflow = obtener_workflow(user_id, workflow_id)
    if not workflow:
        raise ValueError("Workflow no encontrado")
    if workflow["estado"] == "activo":
        raise ValueError("No se puede eliminar el ciclo activo — activa un reemplazo primero")
    sb.table("workflow_definitions").delete().eq("id", workflow_id).execute()


def validar_workflow(user_id: str, workflow_id: str) -> list[dict]:
    workflow = obtener_workflow(user_id, workflow_id)
    if not workflow:
        raise ValueError("Workflow no encontrado")
    errores = validar_grafo(workflow.get("nodos") or [], workflow.get("conexiones") or [])
    from app.services.workflow_automation import validar_automatizacion
    from app.services.workflow_automation_service import listar_configuracion_workflow
    config = listar_configuracion_workflow(user_id, workflow_id)
    responsables_rows = _sb().table("responsables").select("id,activo,email").in_(
        "user_id", _ids_organizacion(user_id)
    ).execute().data or []
    responsables = {r["id"]: r for r in responsables_rows}
    errores.extend(validar_automatizacion(
        workflow.get("nodos") or [], workflow.get("conexiones") or [],
        config["asignaciones"], config["reglas"], responsables,
    ))
    return errores


def activar_workflow(user_id: str, workflow_id: str) -> dict:
    """Valida el grafo; si pasa, archiva cualquier versión activa previa con
    el mismo nombre (transición explícita, no un trigger) y activa esta."""
    sb = _sb()
    workflow = obtener_workflow(user_id, workflow_id)
    if not workflow:
        raise ValueError("Workflow no encontrado")
    if workflow["estado"] == "activo":
        return workflow

    errores = validar_workflow(user_id, workflow_id)
    if errores:
        raise ValueError(f"El workflow tiene {len(errores)} error(es) de validación, no se puede activar")

    anterior = sb.table("workflow_definitions").select("id").in_("user_id", _ids_organizacion(user_id)).eq(
        "nombre", workflow["nombre"]
    ).eq("estado", "activo").execute().data or []
    for a in anterior:
        sb.table("workflow_definitions").update({"estado": "archivado", "updated_at": _now()}).eq("id", a["id"]).execute()

    sb.table("workflow_definitions").update({"estado": "activo", "updated_at": _now()}).eq("id", workflow_id).execute()
    return obtener_workflow(user_id, workflow_id)


def obtener_estado_workflow(user_id: str) -> dict:
    """Resumen operativo del ciclo de la organización para el dashboard.

    Prioriza el ciclo nuevo activo. Si todavía es borrador, informa si ya
    pasó la validación para que la UI no lo confunda con una ausencia total.
    Mantiene compatibilidad con los workflows de aprobación legados.
    """
    sb = _sb()
    ids = _ids_organizacion(user_id)
    rows = sb.table("workflow_definitions").select(
        "id,nombre,estado,nodos,conexiones,updated_at,created_at"
    ).in_("user_id", ids).in_("estado", ["activo", "borrador"]).order(
        "updated_at", desc=True
    ).execute().data or []

    activos = [row for row in rows if row.get("estado") == "activo"]
    candidato = activos[0] if activos else (rows[0] if rows else None)
    if candidato:
        nodos = candidato.get("nodos") or []
        errores = validar_grafo(nodos, candidato.get("conexiones") or [])
        tiene_autorizacion = any(n.get("tipo") == "autorizacion" for n in nodos)
        estado = "activo" if candidato.get("estado") == "activo" else (
            "borrador_validado" if not errores else "borrador_pendiente"
        )
        return {
            "configurado": estado == "activo",
            "estado": estado,
            "workflow_id": candidato["id"],
            "nombre": candidato.get("nombre") or "Ciclo de compras",
            "tiene_autorizacion": tiene_autorizacion,
            "errores_validacion": len(errores),
            "origen": "workflow_builder",
        }

    legados = sb.table("approval_workflows").select("id,nombre,pasos").in_(
        "user_id", ids
    ).eq("activo", True).limit(1).execute().data or []
    if legados:
        legado = legados[0]
        return {
            "configurado": True,
            "estado": "activo",
            "workflow_id": legado["id"],
            "nombre": legado.get("nombre") or "Ciclo de autorizaciones",
            "tiene_autorizacion": bool(legado.get("pasos")),
            "errores_validacion": 0,
            "origen": "legacy",
        }

    return {
        "configurado": False,
        "estado": "sin_configurar",
        "workflow_id": None,
        "nombre": None,
        "tiene_autorizacion": False,
        "errores_validacion": 0,
        "origen": None,
    }


# ─── Responsables ───────────────────────────────────────────────────────────

def crear_responsable(
    user_id: str, nombre: str, cargo: Optional[str] = None, email: Optional[str] = None,
    telefono: Optional[str] = None, suplente_id: Optional[str] = None,
) -> dict:
    sb = _sb()
    ins = sb.table("responsables").insert({
        "user_id": user_id, "nombre": nombre, "cargo": cargo, "email": email,
        "telefono": telefono, "suplente_id": suplente_id,
    }).execute()
    return ins.data[0]


def listar_responsables(user_id: str, incluir_inactivos: bool = False) -> list[dict]:
    sb = _sb()
    q = sb.table("responsables").select("*").eq("user_id", user_id)
    if not incluir_inactivos:
        q = q.eq("activo", True)
    return q.order("nombre").execute().data or []


def actualizar_responsable(user_id: str, responsable_id: str, cambios: dict) -> dict:
    sb = _sb()
    existente = ejecutar_maybe_single(sb.table("responsables").select("id").eq("id", responsable_id).eq("user_id", user_id).maybe_single()).data
    if not existente:
        raise ValueError("Responsable no encontrado")
    campos_validos = {"nombre", "cargo", "email", "telefono", "suplente_id", "activo"}
    cambios_filtrados = {k: v for k, v in cambios.items() if k in campos_validos and v is not None}
    if cambios_filtrados:
        cambios_filtrados["updated_at"] = _now()
        sb.table("responsables").update(cambios_filtrados).eq("id", responsable_id).execute()
    return sb.table("responsables").select("*").eq("id", responsable_id).single().execute().data


def asignar_rol(user_id: str, responsable_id: str, workflow_id: str, rol_clave: str, orden_autorizacion: Optional[int] = None) -> dict:
    sb = _sb()
    responsable = ejecutar_maybe_single(sb.table("responsables").select("id").eq("id", responsable_id).eq("user_id", user_id).maybe_single()).data
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("id").eq("id", workflow_id).eq("user_id", user_id).maybe_single()).data
    if not responsable or not workflow:
        raise ValueError("Responsable o workflow no encontrado")

    existente = ejecutar_maybe_single(sb.table("responsable_roles").select("id").eq("responsable_id", responsable_id).eq(
        "workflow_id", workflow_id
    ).eq("rol_clave", rol_clave).maybe_single()).data
    if existente:
        sb.table("responsable_roles").update({"orden_autorizacion": orden_autorizacion}).eq("id", existente["id"]).execute()
        return sb.table("responsable_roles").select("*").eq("id", existente["id"]).single().execute().data

    ins = sb.table("responsable_roles").insert({
        "responsable_id": responsable_id, "workflow_id": workflow_id,
        "rol_clave": rol_clave, "orden_autorizacion": orden_autorizacion,
    }).execute()
    return ins.data[0]


def quitar_rol(user_id: str, responsable_id: str, workflow_id: str, rol_clave: str) -> None:
    sb = _sb()
    workflow = ejecutar_maybe_single(sb.table("workflow_definitions").select("id").eq("id", workflow_id).eq("user_id", user_id).maybe_single()).data
    if not workflow:
        raise ValueError("Workflow no encontrado")
    sb.table("responsable_roles").delete().eq("responsable_id", responsable_id).eq(
        "workflow_id", workflow_id
    ).eq("rol_clave", rol_clave).execute()
