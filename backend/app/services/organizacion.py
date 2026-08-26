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
    # `.maybe_single()` en postgrest-py 2.x devuelve `None` desde `.execute()`
    # (no un objeto con `.data = None`) cuando no hay ninguna fila — bug real
    # encontrado en producción: crasheaba con AttributeError para cualquier
    # usuario sin fila en membresias_organizacion (ej. creado después del
    # backfill de la 030), tumbando resolver_organizacion y con él CASI TODOS
    # los endpoints que dependen de AuthContext (dashboard, listas, gmail,
    # workflows...).
    resp = sb.table("membresias_organizacion").select(
        "rol, organizacion_id, organizaciones(id, nombre, owner_user_id)"
    ).eq("user_id", auth_uid).maybe_single().execute()
    membresia = resp.data if resp else None
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


def obtener_perfil_organizacion(organizacion_id: str) -> dict:
    """Perfil de marca de la organización (nombre/rut/dirección/logo) para
    personalizar documentos generados (OC, informes). Nunca lanza: si no
    encuentra nada, devuelve {} y el llamador cae a su propio fallback de
    marca genérica — nunca debe tumbar la generación de un documento."""
    if not organizacion_id:
        return {}
    sb = _sb()
    try:
        resp = sb.table("organizaciones").select(
            "nombre, rut, direccion, logo_url, industria, pais, sitio_web"
        ).eq("id", organizacion_id).maybe_single().execute()
        return (resp.data if resp else None) or {}
    except Exception:
        return {}


def obtener_codigo_oc(organizacion_id: str) -> str:
    """Código de empresa para numerar OCs (`BVITAL`), asignado una sola vez.

    Se persiste en `organizaciones.codigo_oc` en vez de derivarse del nombre en
    cada emisión: si la empresa se renombra, las OCs nuevas cambiarían de código
    y su correlativo arrancaría de cero, conviviendo dos series para la misma
    empresa. Un identificador impreso en un documento comercial no puede depender
    de un campo editable.

    Nunca lanza: ante cualquier problema devuelve un código derivado del nombre.
    No poder emitir una OC es peor que emitirla con un código imperfecto.
    """
    from app.services.oc_numeracion import derivar_token, desambiguar

    if not organizacion_id:
        return desambiguar(derivar_token(None), set())

    sb = _sb()
    try:
        fila = ejecutar_maybe_single(
            sb.table("organizaciones").select("nombre, codigo_oc").eq("id", organizacion_id).maybe_single()
        ).data or {}
    except Exception as e:
        # Con la 047 sin aplicar, `codigo_oc` no existe y PostgREST rechaza el
        # select entero. Se reintenta pidiendo sólo el nombre: sin él el código
        # sería "BEMPRESA" para todos, que es justo lo que hay que evitar.
        print(f"[OC] sin columna codigo_oc ({e}); se deriva del nombre")
        try:
            fila = ejecutar_maybe_single(
                sb.table("organizaciones").select("nombre").eq("id", organizacion_id).maybe_single()
            ).data or {}
        except Exception:
            return desambiguar(derivar_token(None), set())
        return desambiguar(derivar_token(fila.get("nombre")), set())

    if fila.get("codigo_oc"):
        return fila["codigo_oc"]

    token = derivar_token(fila.get("nombre"))
    try:
        tomados = {
            (f or {}).get("codigo_oc")
            for f in (sb.table("organizaciones").select("codigo_oc").execute().data or [])
        }
        codigo = desambiguar(token, {c for c in tomados if c})
        sb.table("organizaciones").update({"codigo_oc": codigo}).eq("id", organizacion_id).execute()
        return codigo
    except Exception as e:
        # La columna puede no existir todavía (migración 047 sin aplicar). El
        # código igual sirve para numerar; sólo no queda fijado.
        print(f"[OC] no se pudo persistir el código de la organización: {e}")
        return desambiguar(token, set())


def nombres_de_usuarios(auth_uids: list[str]) -> dict[str, str]:
    """Fase D — resuelve una lista de user_ids a nombres legibles para el
    'hecho por X'. Prioriza nombre_usuario del metadata → empresa → email.
    Nunca lanza: los ids no resueltos quedan como string vacío."""
    if not auth_uids:
        return {}
    sb = _sb()
    fuera = {}
    unicos = {u for u in auth_uids if u}
    for uid in unicos:
        try:
            resp = sb.auth.admin.get_user_by_id(uid)
            u = resp.user if resp else None
            if not u:
                fuera[uid] = ""
                continue
            meta = u.user_metadata or {}
            fuera[uid] = (meta.get("nombre_usuario") or meta.get("empresa") or (u.email or "")) or ""
        except Exception:
            fuera[uid] = ""
    return fuera


def estado_onboarding_de_usuarios(usuario_baiyer_ids: list[str]) -> dict[str, str]:
    """Para el roster de responsables: ¿esta persona ya aceptó su invitación
    y usa Baiyer, o la cuenta existe pero nunca inició sesión? Mismo patrón
    de batching que `nombres_de_usuarios()`. Nunca lanza: un id que no se
    puede resolver queda como "invitacion_pendiente" (nunca se asume
    "activo" sin evidencia real de que inició sesión)."""
    if not usuario_baiyer_ids:
        return {}
    sb = _sb()
    fuera = {}
    unicos = {u for u in usuario_baiyer_ids if u}
    for uid in unicos:
        try:
            resp = sb.auth.admin.get_user_by_id(uid)
            u = resp.user if resp else None
            fuera[uid] = "activo" if (u and getattr(u, "last_sign_in_at", None)) else "invitacion_pendiente"
        except Exception:
            fuera[uid] = "invitacion_pendiente"
    return fuera


def listar_miembros(auth_uid: str) -> list[dict]:
    """Fase D — miembros de la organización del `auth_uid` con nombre e info
    de rol, para poblar el mapa de 'hecho por X' en el frontend."""
    ctx = resolver_organizacion(auth_uid)
    if not ctx:
        return []
    sb = _sb()
    filas = sb.table("membresias_organizacion").select("user_id, rol").eq(
        "organizacion_id", ctx.organizacion_id
    ).execute().data or []
    nombres = nombres_de_usuarios([f["user_id"] for f in filas])
    return [
        {"user_id": f["user_id"], "nombre": nombres.get(f["user_id"], "") or "", "rol": f["rol"]}
        for f in filas
    ]


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


def _linkear_responsable(sb, ctx: ContextoOrganizacion, responsable_id: str, usuario_baiyer_id: str) -> None:
    """Vincula un responsable del canvas a la cuenta Baiyer recién invitada.

    El filtro por los `user_id` de la organización no es cosmético: el backend
    usa la service key, así que sin él un admin de la empresa A que conociera un
    `responsable_id` de la empresa B podía reescribir su `usuario_baiyer_id` y
    dejar al responsable legítimo desconectado de sus aprobaciones y avisos.
    """
    afectadas = sb.table("responsables").update(
        {"usuario_baiyer_id": usuario_baiyer_id}
    ).eq("id", responsable_id).in_("user_id", ctx.user_ids_miembros).execute().data
    if not afectadas:
        raise ValueError("El responsable no pertenece a tu organización")


def invitar_a_organizacion(
    invitador_auth_uid: str, email: str, rol: str = "miembro",
    responsable_id: Optional[str] = None,
) -> dict:
    """Fase C: invita a un correo a la organización del invitador.

    Requiere que el invitador sea admin. Usa el flujo nativo de Supabase Auth
    para crear el usuario y enviar el correo de invitación (magic link con
    token) — no reimplementamos nada de auth. Al aceptar el correo, la
    persona setea su contraseña; ya queda como miembro real de la
    organización porque acá insertamos la membresía en el mismo paso.

    Si viene `responsable_id`, además vincula ese responsable (creado desde
    el canvas del Workflow Builder) al nuevo `usuario_baiyer_id`, para que
    la Fase 4 pueda dispararle notificaciones directas.

    La respuesta es deliberadamente uniforme para todo email que no sea ya
    miembro de ESTA organización: siempre `{"estado": "invitada"}`, sin
    `user_id`. Antes distinguía tres casos —invitado nuevo (devolvía el UUID
    recién creado), "ya pertenece a otra organización" (confirmaba que la cuenta
    existe) y ya miembro— así que cualquier usuario autenticado podía mapear qué
    correos tienen cuenta en Baiyer y quedarse con sus UUIDs. Distinguir "ya
    miembro" no filtra nada: el invitador es admin y ya puede listar su propio
    roster.

    Levanta ValueError sólo por condiciones del INVITADOR (no es admin, email
    con formato inválido), nunca por algo que revele el estado de la cuenta
    ajena.
    """
    from app.config import settings

    sb = _sb()
    ctx = resolver_organizacion(invitador_auth_uid)
    if not ctx:
        raise ValueError("Invitador sin organización")
    if not ctx.es_admin:
        raise ValueError("Solo un admin de la organización puede invitar")

    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("Email inválido")

    # Chequeo defensivo: si el usuario ya existe en auth.users, verificar
    # que no esté en otra organización (regla actual: 1 usuario = 1 org).
    try:
        existentes = sb.auth.admin.list_users()
        ya_existe = next(
            (u for u in (existentes or [])
             if (u.email or "").lower() == email),
            None,
        )
    except Exception:
        ya_existe = None

    if ya_existe:
        # Si ya está en NUESTRA organización, no reinvitar — solo linkear
        # el responsable si vino uno. Es idempotente.
        _resp_ya_miembro = sb.table("membresias_organizacion").select(
            "organizacion_id"
        ).eq("user_id", ya_existe.id).maybe_single().execute()
        ya_miembro = _resp_ya_miembro.data if _resp_ya_miembro else None
        if ya_miembro and ya_miembro["organizacion_id"] == ctx.organizacion_id:
            if responsable_id:
                _linkear_responsable(sb, ctx, responsable_id, ya_existe.id)
            return {"email": email, "estado": "ya_miembro"}
        if ya_miembro:
            # Pertenece a otra organización (1 usuario = 1 org). No se invita ni
            # se linkea nada, pero la respuesta es la misma que la de un alta
            # normal: decir la verdad acá es exactamente la fuga de enumeración.
            # El admin igual ve el efecto real en el roster, donde el
            # responsable queda "sin vincular".
            print(f"[Organizacion] invitación no cursada: {email} ya pertenece a otra organización")
            return {"email": email, "estado": "invitada"}

    # Nombre legible del invitador — para que aparezca en el correo template
    # como {{ .Data.invitado_por_nombre }} en vez del UUID crudo.
    invitador_nombre = ""
    try:
        u = sb.auth.admin.get_user_by_id(invitador_auth_uid)
        m = (u.user.user_metadata or {}) if u and u.user else {}
        invitador_nombre = (
            m.get("nombre_usuario") or m.get("empresa") or (u.user.email if u and u.user else "")
        ) or ""
    except Exception:
        pass

    redirect_to = f"{settings.frontend_url.rstrip('/')}/auth/aceptar-invitacion"
    try:
        resp = sb.auth.admin.invite_user_by_email(
            email, {"redirect_to": redirect_to, "data": {
                "organizacion_id": ctx.organizacion_id,
                "organizacion_nombre": ctx.nombre,
                "invitado_por": invitador_auth_uid,
                "invitado_por_nombre": invitador_nombre,
            }},
        )
        nuevo_user = resp.user
    except Exception as e:
        # El detalle de Supabase se queda en el log: sus mensajes distinguen
        # "email ya registrado" de un fallo de envío, que es la misma fuga que
        # cierra el bloque de arriba.
        print(f"[Organizacion] invite_user_by_email falló para {email}: {e}")
        return {"email": email, "estado": "invitada"}

    if not nuevo_user:
        print(f"[Organizacion] Supabase no devolvió usuario al invitar a {email}")
        return {"email": email, "estado": "invitada"}

    # Membresía idempotente (ON CONFLICT en la migración 030 vía UNIQUE(user_id)).
    try:
        sb.table("membresias_organizacion").insert({
            "organizacion_id": ctx.organizacion_id,
            "user_id": nuevo_user.id,
            "rol": rol if rol in ("admin", "miembro") else "miembro",
            "invitado_por": invitador_auth_uid,
        }).execute()
    except Exception:
        pass  # ya existía — el flujo de invitación puede reintentar

    if responsable_id:
        try:
            _linkear_responsable(sb, ctx, responsable_id, nuevo_user.id)
        except Exception as e:
            print(f"[Organizacion] no se pudo linkear responsable {responsable_id}: {e}")

    _sincronizar_membresia_capo(sb, ctx.organizacion_id, ctx.owner_user_id, nuevo_user.id, rol)

    return {"email": email, "estado": "invitada"}


def _sincronizar_membresia_capo(sb, organizacion_id: str, owner_user_id: str, invitado_user_id: str, rol: str) -> None:
    """Espejo hacia `organizations`/`organization_memberships` (el modelo de
    CAPO, migración 028) — el puente hoy solo funciona en la dirección
    CAPO → Baiyer (`admin_control_plane._operational_org_id`). Sin este
    espejo, invitar a alguien desde Baiyer (Fase C) deja a esa persona bien
    en `organizaciones` pero con su organización individual huérfana en
    `organizations`, y CAPO nunca se entera de que ahora es miembro de otra.

    Nunca lanza: un fallo acá no debe tumbar la invitación real, que ya
    quedó confirmada en `membresias_organizacion` antes de llegar aquí.
    """
    try:
        org_capo = sb.table("organizations").select("id").eq(
            "slug", f"user-{owner_user_id}"
        ).limit(1).execute().data
        if not org_capo:
            return  # el dueño todavía no tiene fila en CAPO — nada que sincronizar
        organization_id_capo = org_capo[0]["id"]

        sb.table("organization_memberships").update(
            {"estado": "removed", "es_principal": False}
        ).eq("user_id", invitado_user_id).neq("organization_id", organization_id_capo).execute()

        rol_capo = "admin" if rol == "admin" else "member"
        existente = sb.table("organization_memberships").select("id").eq(
            "organization_id", organization_id_capo
        ).eq("user_id", invitado_user_id).limit(1).execute().data
        valores = {"rol": rol_capo, "estado": "active", "es_principal": True}
        if existente:
            sb.table("organization_memberships").update(valores).eq("id", existente[0]["id"]).execute()
        else:
            sb.table("organization_memberships").insert({
                "organization_id": organization_id_capo, "user_id": invitado_user_id, **valores,
            }).execute()
    except Exception as e:
        print(f"[Organizacion] no se pudo sincronizar membresía hacia CAPO: {e}")


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
