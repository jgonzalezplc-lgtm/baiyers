"""
Resolutor central de organización — FASE A (fundación).

En este momento SOLO expone el resolutor y utilidades de lectura. Ningún
router lo consume todavía: eso es la Fase B, donde los ~22 routers que hoy
filtran por `.eq("user_id", auth_uid)` pasarán a `.in_("user_id", ids)` para
que un miembro de la misma organización vea los datos compartidos.

Modelo hoy:
- Un usuario pertenece a exactamente una organización (regla de producto).
- El `owner_user_id` de la organización es el dueño histórico de los datos:
  todas las filas de proyectos/cotizaciones/suppliers/etc. con ese `user_id`
  pertenecen a esa organización. NO cambia al invitar gente nueva.
- Cada miembro tiene un rol: 'admin' o 'miembro'. Admin puede invitar/quitar
  miembros y (Fase C+) gestionar responsables/workflows.
"""
from dataclasses import dataclass
from typing import Optional


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


@dataclass(frozen=True)
class ContextoOrganizacion:
    """Todo lo que un endpoint necesita saber sobre la organización del que
    hace la request. Se construye una vez al principio y se pasa a las capas
    de datos, en vez de propagar auth_uid crudo."""
    organizacion_id: str
    nombre: str
    owner_user_id: str
    user_ids_miembros: list[str]
    rol: str
    es_admin: bool


def resolver_organizacion(auth_uid: str) -> Optional[ContextoOrganizacion]:
    """Devuelve el contexto de organización del `auth_uid` dado, o None si el
    usuario todavía no tiene organización (nunca debería pasar tras la
    migración 030, pero se maneja como caso defensivo).

    Es la única entrada correcta a este módulo desde los routers en Fase B —
    no leas `membresias_organizacion` a mano.
    """
    sb = _sb()
    membresia = sb.table("membresias_organizacion").select(
        "rol, organizacion_id, organizaciones(id, nombre, owner_user_id)"
    ).eq("user_id", auth_uid).maybe_single().execute().data
    if not membresia:
        return None

    org = membresia["organizaciones"]
    miembros = sb.table("membresias_organizacion").select("user_id").eq(
        "organizacion_id", org["id"]
    ).execute().data or []

    rol = membresia["rol"]
    return ContextoOrganizacion(
        organizacion_id=org["id"],
        nombre=org["nombre"],
        owner_user_id=org["owner_user_id"],
        user_ids_miembros=[m["user_id"] for m in miembros],
        rol=rol,
        es_admin=rol == "admin",
    )


def obtener_organizacion(auth_uid: str) -> dict:
    """Versión pública liviana para el endpoint del frontend. Nunca devuelve
    None: si por alguna razón un usuario no tiene organización, la crea al
    vuelo (mismo backfill que la migración 030). Esto es la red de seguridad
    para el flujo de registro nuevo."""
    contexto = resolver_organizacion(auth_uid)
    if contexto:
        return _contexto_a_dict(contexto)

    sb = _sb()
    # Nombre por defecto = empresa del user_metadata, o el email.
    user = sb.auth.admin.get_user_by_id(auth_uid)
    meta = (user.user.user_metadata or {}) if user and user.user else {}
    nombre = meta.get("empresa") or (user.user.email if user and user.user else "Mi organización")
    org = sb.table("organizaciones").insert({
        "nombre": nombre, "owner_user_id": auth_uid,
    }).execute().data[0]
    sb.table("membresias_organizacion").insert({
        "organizacion_id": org["id"], "user_id": auth_uid, "rol": "admin",
    }).execute()
    return _contexto_a_dict(resolver_organizacion(auth_uid))


def ids_organizacion(auth_uid: str) -> list[str]:
    """Lista de user_ids que comparten organización con `auth_uid` (incluye
    al propio `auth_uid`). Es el punto de intercambio principal en Fase B:
    los routers reemplazan `.eq("user_id", uid)` por `.in_("user_id", ids)`
    y así los miembros de la misma organización ven los mismos datos.

    Contrato importante: si el usuario no está en ninguna organización (caso
    defensivo; nunca debería pasar tras el backfill), devuelve `[auth_uid]` —
    nunca una lista vacía, nunca uno ajeno. Esto garantiza que un fallo del
    resolutor NUNCA amplía visibilidad, solo la mantiene igual que antes.
    """
    ctx = resolver_organizacion(auth_uid)
    if not ctx:
        return [auth_uid]
    return ctx.user_ids_miembros


def _contexto_a_dict(ctx: Optional[ContextoOrganizacion]) -> dict:
    if not ctx:
        return {}
    return {
        "organizacion_id": ctx.organizacion_id,
        "nombre": ctx.nombre,
        "owner_user_id": ctx.owner_user_id,
        "user_ids_miembros": ctx.user_ids_miembros,
        "rol": ctx.rol,
        "es_admin": ctx.es_admin,
    }
