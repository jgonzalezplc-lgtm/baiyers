"""Lectura del ciclo de compras y del motor que lo ejecuta.

Existe por un agujero concreto: una empresa puede tener su proceso dibujado,
validado y con responsables asignados, y aun así **el grafo no gobierna nada**,
porque el motor está en `legacy` (el default). Desde el MCP no había forma de
saberlo — `get_purchase_context` decía `origen: "derivado"` y punto, sin
explicar que existía un proceso configurado que no se estaba usando.

Cada respuesta trae `aviso` y `configurar_en` cuando algo falta, porque un
estado que no dice qué hacer obliga a adivinar. `legacy` es una palabra que no
significa nada para quien no leyó el código.

**Sólo lectura.** Cambiar de motor NO se expone acá a propósito: decide quién le
manda correos a proveedores reales y con qué cadencia. Es una decisión que el
PRD pide tomar con un checkpoint observado, no algo que un modelo pueda apretar
con un `confirmed=true` que se pone él mismo.
"""
from typing import Any, Optional

from app.services.mcp_context import ApplicationActorContext


def _url(ruta: str) -> str:
    from app.config import settings
    return f"{settings.frontend_url.rstrip('/')}{ruta}"


def estado_rollout(actor: ApplicationActorContext) -> dict[str, Any]:
    """Qué motor gobierna las compras nuevas de esta organización."""
    from app.services.workflow_execution import obtener_workflow_activo
    from app.services.workflow_rollout import obtener_rollout

    try:
        rollout = obtener_rollout(actor.organization_id)
        modo = rollout.get("execution_mode", "legacy")
    except Exception as e:
        print(f"[WorkflowLectura] no se pudo leer el rollout: {type(e).__name__}: {e}")
        modo = "legacy"

    try:
        workflow = obtener_workflow_activo(actor.actor_user_id)
    except Exception:
        workflow = None

    gobierna = modo in ("unified", "compatibility") and bool(workflow)
    datos: dict[str, Any] = {
        "execution_mode": modo,
        "workflow_activo": bool(workflow),
        "workflow_nombre": (workflow or {}).get("nombre"),
        # La pregunta que de verdad importa, respondida sin jerga.
        "el_grafo_gobierna_las_compras": gobierna,
    }

    if gobierna:
        datos["aviso"] = None
    elif workflow:
        datos["aviso"] = (
            f"Existe un ciclo de compras activo ('{workflow.get('nombre')}') pero el motor está "
            "en 'legacy': el grafo NO gobierna las compras. Las autorizaciones salen al correo "
            "fijo de configuración, no a los responsables del ciclo."
        )
        datos["configurar_en"] = _url("/settings/rollout")
    else:
        datos["aviso"] = (
            "No hay ningún ciclo de compras configurado. Baiyer usa el flujo por defecto: "
            "un solo correo autorizador y sin reglas por monto."
        )
        datos["configurar_en"] = _url("/settings/autorizaciones")
    return datos


def workflow_activo(actor: ApplicationActorContext) -> dict[str, Any]:
    """El ciclo de compras de la organización: etapas, roles y responsables."""
    from app.services.workflow_execution import obtener_workflow_activo

    rollout = estado_rollout(actor)
    try:
        workflow = obtener_workflow_activo(actor.actor_user_id)
    except Exception as e:
        print(f"[WorkflowLectura] no se pudo leer el workflow: {type(e).__name__}: {e}")
        workflow = None

    if not workflow:
        return {
            "existe": False,
            "el_grafo_gobierna_las_compras": False,
            "aviso": rollout["aviso"],
            "configurar_en": _url("/settings/autorizaciones"),
        }

    return {
        "existe": True,
        "id": workflow.get("id"),
        "nombre": workflow.get("nombre"),
        "estado": workflow.get("estado"),
        "version": workflow.get("version"),
        "etapas": _etapas(workflow),
        "roles": _roles(workflow.get("id")),
        "el_grafo_gobierna_las_compras": rollout["el_grafo_gobierna_las_compras"],
        "aviso": rollout["aviso"],
        # Siempre presente: editar el ciclo es la acción natural después de verlo.
        "configurar_en": _url(f"/settings/autorizaciones/canvas/{workflow.get('id')}"),
    }


def _etapas(workflow: dict) -> list[dict[str, Any]]:
    """Las tarjetas del canvas, con el nombre que les puso la empresa."""
    return [
        {"id": n.get("id"), "tipo": n.get("tipo"),
         "label": n.get("label") or n.get("titulo") or n.get("id")}
        for n in (workflow.get("nodos") or [])
    ]


def _roles(workflow_id: Optional[str]) -> list[dict[str, Any]]:
    """Roles del ciclo con quién los cumple. Un rol sin responsable es un hueco
    real del proceso, así que se lista igual en vez de omitirlo."""
    if not workflow_id:
        return []
    try:
        from app.services.supabase import get_supabase

        sb = get_supabase()
        roles = sb.table("workflow_roles").select("id,clave,nombre").eq(
            "workflow_id", workflow_id
        ).execute().data or []
        if not roles:
            return []

        vinculos = sb.table("responsable_roles").select(
            "rol_id, responsables(nombre, email)"
        ).in_("rol_id", [r["id"] for r in roles]).execute().data or []

        personas: dict[str, list[dict]] = {}
        for v in vinculos:
            persona = v.get("responsables") or {}
            if persona.get("nombre") or persona.get("email"):
                personas.setdefault(v["rol_id"], []).append(
                    {"nombre": persona.get("nombre"), "email": persona.get("email")}
                )

        return [
            {"clave": r.get("clave"), "nombre": r.get("nombre"),
             "responsables": personas.get(r["id"], []),
             "sin_responsable": not personas.get(r["id"])}
            for r in roles
        ]
    except Exception as e:
        print(f"[WorkflowLectura] no se pudieron leer los roles: {type(e).__name__}: {e}")
        return []
