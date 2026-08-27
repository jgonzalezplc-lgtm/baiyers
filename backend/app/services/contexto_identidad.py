"""Quién es el usuario, cuál es su empresa y quién cumple cada rol.

Existe para que un cliente MCP no tenga que preguntarle al usuario datos que
Baiyer ya conoce. Antes `baiyer_status` devolvía sólo el id y el nombre de la
organización, así que el asistente terminaba pidiendo por chat el correo, la
dirección o quién autoriza —datos que están en la base y que el usuario ya
cargó una vez.

**Sólo lectura, y nunca lanza.** Cada bloque se resuelve por separado: si falla
uno, los demás igual viajan. Un perfil incompleto es útil; una excepción en la
tool de estado deja al cliente sin nada.

La dirección administrativa y la de despacho van SEPARADAS y etiquetadas a
propósito: no son intercambiables, y confundirlas fue lo que casi manda una
dirección de Buenos Aires a un proveedor chileno (ver `obtener_despacho_organizacion`).
"""
from typing import Any

from app.services.mcp_context import ApplicationActorContext


def contexto_identidad(actor: ApplicationActorContext) -> dict[str, Any]:
    """Perfil del usuario, de su empresa y el roster de roles."""
    return {
        "usuario": _usuario(actor),
        "organizacion": _organizacion(actor),
        "roles": _roles(actor),
    }


def _usuario(actor: ApplicationActorContext) -> dict[str, Any]:
    datos: dict[str, Any] = {"user_id": actor.actor_user_id, "es_admin": actor.is_admin}
    try:
        from app.services.supabase import get_supabase

        usuario = get_supabase().auth.admin.get_user_by_id(actor.actor_user_id)
        cuenta = getattr(usuario, "user", None)
        if cuenta:
            meta = cuenta.user_metadata or {}
            datos["email"] = cuenta.email
            datos["nombre"] = meta.get("nombre_usuario") or meta.get("full_name")
    except Exception as e:
        print(f"[Identidad] no se pudo leer el usuario: {type(e).__name__}: {e}")
    return datos


def _organizacion(actor: ApplicationActorContext) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": actor.organization_id, "nombre": actor.organization_name,
    }
    try:
        from app.services.organizacion import (
            obtener_despacho_organizacion, obtener_perfil_organizacion,
        )

        perfil = obtener_perfil_organizacion(actor.organization_id) or {}
        datos.update({
            "rut": perfil.get("rut"),
            "industria": perfil.get("industria"),
            "pais": perfil.get("pais"),
            "sitio_web": perfil.get("sitio_web"),
            # Administrativa: la scrapea el onboarding del sitio web y NO está
            # verificada. No sirve como destino de entrega.
            "direccion_administrativa": perfil.get("direccion"),
        })
        despacho = obtener_despacho_organizacion(actor.organization_id)
        datos["despacho"] = despacho or None
        datos["despacho_configurado"] = bool(despacho)
    except Exception as e:
        print(f"[Identidad] no se pudo leer la organización: {type(e).__name__}: {e}")
    return datos


def _roles(actor: ApplicationActorContext) -> list[dict[str, Any]]:
    """Responsables activos con el rol que cumplen (autorizador, comprador…).

    Se listan para toda la organización, no sólo para el usuario actual: quien
    autoriza una compra rara vez es quien la inicia.
    """
    try:
        from app.services.supabase import get_supabase
        from app.services.workflow_service import listar_responsables

        personas: dict[str, dict] = {}
        for user_id in actor.organization_user_ids:
            for fila in listar_responsables(user_id):
                personas[fila["id"]] = fila
        if not personas:
            return []

        sb = get_supabase()
        vinculos = sb.table("responsable_roles").select(
            "responsable_id, workflow_roles(clave, nombre)"
        ).in_("responsable_id", list(personas)).execute().data or []

        roles_por_persona: dict[str, list[str]] = {}
        for v in vinculos:
            rol = (v.get("workflow_roles") or {}).get("clave")
            if rol:
                roles_por_persona.setdefault(v["responsable_id"], []).append(rol)

        return [
            {"nombre": p.get("nombre"), "email": p.get("email"), "cargo": p.get("cargo"),
             "roles": roles_por_persona.get(pid, [])}
            for pid, p in personas.items()
        ]
    except Exception as e:
        print(f"[Identidad] no se pudieron leer los roles: {type(e).__name__}: {e}")
        return []
