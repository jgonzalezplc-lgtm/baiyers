"""Guardia deny-by-default del borde HTTP.

Motivo (2026-08-24, antes de los pilotos con clientes empresa reales): el
backend consulta Supabase con la service key, así que **bypassea RLS**. Las
políticas de la 031 no son una segunda capa para este camino. Lo único que
separa a una organización de otra en un endpoint que recibe `user_id` por
query/body es que ese UUID sea difícil de adivinar — un identificador, no una
credencial, y que además viaja en la query string (logs de Railway/Cloudflare,
historial del navegador, cabecera `Referer`).

Este módulo invierte la política: **toda ruta bajo `/api` exige un token de
Supabase verificado, salvo que esté listada explícitamente acá.** Un endpoint
nuevo nace cerrado. Si alguien quiere abrirlo, tiene que escribirlo en una de
estas listas, y eso se ve en el diff.

Se implementa como dependencia global (no como middleware ASGI) a propósito:
las dependencias corren DESPUÉS del ruteo, así que `request.scope["route"]`
ya trae la plantilla real (`/api/proyectos/{proyecto_id}`) y el match es
exacto — nada de prefijos ni regex hechos a mano, que es donde estas
allowlists se rompen en silencio.
"""
from fastapi import HTTPException, Request

# ── 1. Públicas de verdad ────────────────────────────────────────────────────
# Cada una tiene un motivo por el que NO puede exigir sesión. No agregar nada
# acá sin ese motivo escrito.
RUTAS_PUBLICAS: frozenset[str] = frozenset({
    "GET /api/health",                              # liveness de Railway
    # Magic links: el autorizador/proveedor decide desde el correo, sin cuenta.
    # El token del path ES la credencial y se valida en el endpoint.
    "GET /api/oc/info/{token}",
    "POST /api/oc/confirmar/{token}",
    # OAuth: SÓLO los callbacks, que los invoca Google/Microsoft y no pueden
    # traer sesión Baiyer. Confían en la firma HMAC del `state`, no en el
    # `user_id` que traen. Iniciar el flujo es `POST /{gmail,outlook}/conectar`,
    # que exige sesión: hasta el 2026-08-25 existía `GET /api/gmail/auth?user_id=`
    # sin autenticar, y alcanzaba para dejar el buzón del atacante conectado a la
    # cuenta de la víctima (ver services/oauth_state.py).
    "GET /api/gmail/callback",
    "GET /api/outlook/callback",
    "POST /api/gmail/webhook",                      # Pub/Sub de Google
    # Sin datos de ninguna organización.
    "GET /api/proveedores/plantilla",               # CSV de ejemplo, estático
    "GET /api/mail-templates/eventos",              # catálogo de los 16 eventos
    # Verifica el access_token por su cuenta (ver cuenta.py) y se usa para
    # darse de baja; migrarlo a AuthContext es cosmético, no de seguridad.
    "POST /api/cuenta/eliminar",
    # Se llama durante el registro, antes de que exista sesión utilizable.
    "POST /api/onboarding/investigar-empresa",
})

# ── 2. Con guardia propio ────────────────────────────────────────────────────
# No usan AuthContext porque tienen otro mecanismo de identidad, igual de
# verificado. No son deuda.
PREFIJOS_CON_GUARDIA_PROPIO: tuple[str, ...] = (
    "/api/admin-control-plane",   # JWT de Supabase + fila activa en admin_users
    "/api/mcp",                   # tokens OAuth MCP opacos y hashados
    "/api/v1",                    # API pública por api_key
)

# Excepciones a lo anterior: rutas que caen bajo uno de esos prefijos pero NO
# tienen el guardia del prefijo, así que necesitan sesión web como cualquier otra.
# Los tres endpoints de `/api/v1/keys` son los que EMITEN la api_key, de modo que
# no pueden autenticarse con ella; la exención por prefijo los dejaba sin ninguna
# capa y su identidad salía del header `X-Claria-User-Id` sin verificar.
RUTAS_CON_SESION_DENTRO_DE_PREFIJO: frozenset[str] = frozenset({
    "POST /api/v1/keys",
    "GET /api/v1/keys",
    "DELETE /api/v1/keys/{key_id}",
})

# ── 3. DEUDA — en cero ───────────────────────────────────────────────────────
# Rutas que deducían la identidad de un `user_id` mandado por el cliente.
# Empezó con 72 entradas y hoy está vacía. Las últimas dos (`POST /api/buscar` y
# `POST /api/identificar`) se cerraron cuando el servidor MCP y la API pública
# dejaron de pegarle por HTTP a la propia API y pasaron a usar
# `services/cotizacion_pipeline.py` en proceso.
#
# No agregar rutas acá bajo ninguna circunstancia: una ruta nueva se escribe con
# `Depends(get_auth_context)` desde el principio. Si algo realmente no puede
# exigir sesión, va en RUTAS_PUBLICAS con el motivo escrito.
DEUDA_SIN_AUTENTICAR: frozenset[str] = frozenset()


def _clave(request: Request) -> str:
    """`METODO /plantilla/con/{parametros}` — la plantilla, nunca la URL
    concreta, para que `/api/proyectos/<uuid-ajeno>` no pueda hacerse pasar
    por una entrada distinta de la allowlist."""
    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", None) or request.url.path
    return f"{request.method} {plantilla}"


async def exigir_sesion(request: Request) -> None:
    """Dependencia global. Deja pasar sólo si la ruta está explícitamente
    exceptuada o si el request trae un token de Supabase verificado."""
    if request.method == "OPTIONS":       # preflight de CORS, sin cuerpo
        return
    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", None) or request.url.path
    if not plantilla.startswith("/api"):
        return
    clave = _clave(request)
    if plantilla.startswith(PREFIJOS_CON_GUARDIA_PROPIO) and clave not in RUTAS_CON_SESION_DENTRO_DE_PREFIJO:
        return
    if clave in RUTAS_PUBLICAS or clave in DEUDA_SIN_AUTENTICAR:
        return

    from app.services.auth_context import verificar_token

    # Guarda el actor verificado para que `get_auth_context` no tenga que
    # volver a preguntarle a Supabase en el mismo request.
    request.state.actor_user_id = verificar_token(request.headers.get("authorization"))


def rutas_desprotegidas(app) -> list[str]:
    """Introspección para el test de aislamiento: toda ruta `/api` que hoy no
    exige sesión. El test afirma que este conjunto es exactamente
    `RUTAS_PUBLICAS | DEUDA_SIN_AUTENTICAR` más los prefijos con guardia
    propio — así, un endpoint nuevo sin auth hace fallar el build en vez de
    filtrar datos en producción."""
    from app.services.auth_context import get_auth_context

    def recorrer(router):
        for r in getattr(router, "routes", []):
            if type(r).__name__ == "_IncludedRouter":
                yield from recorrer(r.original_router)
            else:
                yield r

    def usa_auth_context(dependant) -> bool:
        if dependant is None:
            return False
        if dependant.call is get_auth_context:
            return True
        return any(usa_auth_context(sub) for sub in dependant.dependencies)

    salida: list[str] = []
    for r in recorrer(app):
        plantilla = getattr(r, "path", "") or ""
        if not plantilla.startswith("/api") or plantilla.startswith(PREFIJOS_CON_GUARDIA_PROPIO):
            continue
        if usa_auth_context(getattr(r, "dependant", None)):
            continue
        for metodo in sorted(getattr(r, "methods", None) or []):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            salida.append(f"{metodo} {plantilla}")
    return sorted(set(salida))
