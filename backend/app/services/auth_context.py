"""
AuthContext — verificación real de identidad (cierre del riesgo de seguridad
más importante detectado en PLAN_DATA_FOUNDATION.md).

Hasta ahora, todos los routers confían en el `user_id` que manda el cliente
por query/body — cualquiera que lo adivine o lo copie puede actuar como esa
persona, y desde la Fase B del multi-usuario (ids_organizacion) eso da
acceso a TODA la organización, no solo a una cuenta.

Este módulo agrega una dependencia FastAPI que verifica el JWT real de
Supabase (`Authorization: Bearer <token>`) contra el servidor de Supabase
Auth — no se decodifica el JWT a mano ni se maneja ningún secreto localmente.
Devuelve un `AuthContext` con el `actor_user_id` YA VERIFICADO y su
`organization_id` real.

Migración deliberadamente incremental (mismo criterio que la Fase B del
multi-usuario): el frontend hoy NO manda este header en ninguno de sus ~39
puntos de fetch, así que esta dependencia se adopta ruta por ruta, no de
golpe. Los routers que no la usan todavía siguen funcionando exactamente
igual que antes (sin cambios) hasta que se migran uno por uno.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request


@dataclass(frozen=True)
class AuthContext:
    actor_user_id: str          # verificado contra Supabase — nunca del body/query
    organization_id: str
    organization_nombre: str
    user_ids_organizacion: list[str]
    es_admin: bool


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def verificar_token(authorization: Optional[str]) -> str:
    """Extrae y verifica el JWT del header `Authorization: Bearer <token>`
    contra el servidor real de Supabase Auth. Devuelve el `user_id`
    verificado o lanza 401. Nunca confía en nada que no venga firmado."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta el header Authorization: Bearer <token>")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacío")

    sb = _sb()
    try:
        resp = sb.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    if not resp or not resp.user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return resp.user.id


async def get_auth_context(
    request: Request = None,          # lo inyecta FastAPI; opcional para poder
    authorization: Optional[str] = Header(default=None),   # llamarla directo en tests
) -> AuthContext:
    """Dependencia FastAPI: `ctx: AuthContext = Depends(get_auth_context)`.

    Verifica el token, resuelve la organización real del usuario (mismo
    resolutor que ya usa el resto de la Fase B — una sola fuente de verdad)
    y devuelve un contexto listo para usar en filtros `.in_("user_id", ...)`.
    """
    from app.services.organizacion import obtener_organizacion, resolver_organizacion

    # `tenant_guard.exigir_sesion` ya verificó el token de este request contra
    # Supabase; reusar su resultado evita un segundo roundtrip por request.
    ya_verificado = getattr(getattr(request, "state", None), "actor_user_id", None)
    actor_user_id = ya_verificado or verificar_token(authorization)
    ctx = resolver_organizacion(actor_user_id)
    if not ctx:
        # Red de seguridad: un usuario sin fila en membresias_organizacion
        # (ej. se registró después del backfill de la 030, y hoy no hay
        # trigger que le cree su organización personal al firmar up) no
        # debe quedar bloqueado de toda la app — se autocrea igual que ya
        # hace `obtener_organizacion()` para el endpoint /mia, y recién si
        # eso también falla se corta con 403.
        obtener_organizacion(actor_user_id)
        ctx = resolver_organizacion(actor_user_id)
    if not ctx:
        raise HTTPException(status_code=403, detail="Usuario sin organización asignada")

    return AuthContext(
        actor_user_id=actor_user_id,
        organization_id=ctx.organizacion_id,
        organization_nombre=ctx.nombre,
        user_ids_organizacion=ctx.user_ids_miembros,
        es_admin=ctx.es_admin,
    )
