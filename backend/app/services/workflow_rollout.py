"""Fase G: selección explícita de dueño, métricas comparables y rollback."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.supabase import ejecutar_maybe_single


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def obtener_rollout(organization_id: str) -> dict:
    """Ausencia de fila significa legacy. Si 045 aún no está aplicada se
    conserva temporalmente el opt-in A-F para no cortar producción al desplegar."""
    try:
        fila = ejecutar_maybe_single(_sb().table("workflow_rollout_settings").select("*").eq(
            "organization_id", organization_id
        ).maybe_single()).data
    except Exception:
        return {"organization_id": organization_id, "execution_mode": "compatibility", "migration_pending": True}
    return fila or {"organization_id": organization_id, "execution_mode": "legacy", "migration_pending": False}


def motor_unificado_habilitado(user_id: str) -> bool:
    from app.services.organizacion import resolver_organizacion
    org = resolver_organizacion(user_id)
    if not org:
        return False
    rollout = obtener_rollout(org.organizacion_id)
    return rollout["execution_mode"] in ("unified", "compatibility")


def cambiar_rollout(user_id: str, organization_id: str, execution_mode: str,
                    reason: str = "") -> dict:
    if execution_mode not in ("legacy", "unified"):
        raise ValueError("Modo de ejecución inválido")
    if execution_mode == "unified":
        from app.services.workflow_execution import obtener_workflow_activo
        from app.services.workflow_service import validar_workflow
        workflow = obtener_workflow_activo(user_id)
        if not workflow:
            raise ValueError("No existe un workflow activo para habilitar el motor unificado")
        errores = validar_workflow(user_id, workflow["id"])
        if errores:
            raise ValueError(f"El workflow activo tiene {len(errores)} error(es) de validación")
    now = datetime.now(timezone.utc).isoformat()
    filas = _sb().table("workflow_rollout_settings").upsert({
        "organization_id": organization_id,
        "execution_mode": execution_mode,
        "changed_by": user_id,
        "change_reason": reason.strip() or ("Habilitación manual" if execution_mode == "unified" else "Rollback manual"),
        "changed_at": now,
    }, on_conflict="organization_id").execute().data or []
    return filas[0] if filas else obtener_rollout(organization_id)


def obtener_metricas_rollout(user_ids: list[str], organization_id: str) -> dict:
    sb = _sb()
    instancias = sb.table("workflow_instances").select(
        "id,execution_owner,estado_workflow,created_at,updated_at"
    ).in_("user_id", user_ids).execute().data or []
    ids = [i["id"] for i in instancias]
    eventos = sb.table("workflow_events").select("instance_id,accion").in_(
        "instance_id", ids
    ).execute().data or [] if ids else []
    acciones = sb.table("workflow_scheduled_actions").select("id,instance_id,estado").in_(
        "instance_id", ids
    ).execute().data or [] if ids else []
    action_ids = [a["id"] for a in acciones]
    entregas_inciertas = sb.table("mail_delivery_events").select("scheduled_action_id").in_(
        "scheduled_action_id", action_ids
    ).eq("estado", "delivery_uncertain").execute().data or [] if action_ids else []

    def resumen(owner: str) -> dict:
        propias = [i for i in instancias if i.get("execution_owner", "legacy") == owner]
        propias_ids = {i["id"] for i in propias}
        propios_eventos = [e for e in eventos if e.get("instance_id") in propias_ids]
        propias_acciones = [a for a in acciones if a.get("instance_id") in propias_ids]
        return {
            "instancias": len(propias),
            "activas": sum(i.get("estado_workflow") in ("activo", "pausado") for i in propias),
            "completadas": sum(i.get("estado_workflow") == "completado" for i in propias),
            "eventos": len(propios_eventos),
            "loops_agotados": sum(a.get("estado") == "agotada" for a in propias_acciones),
            "envios_inciertos": sum(
                e.get("scheduled_action_id") in {a["id"] for a in propias_acciones}
                for e in entregas_inciertas
            ),
        }

    return {
        "rollout": obtener_rollout(organization_id),
        "legacy": resumen("legacy"),
        "unified": resumen("unified"),
        "nota": "El cambio de modo sólo gobierna instancias nuevas; las existentes conservan execution_owner.",
    }
