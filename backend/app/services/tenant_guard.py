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
    "GET /api/aprobaciones/token/{token}",
    "POST /api/aprobaciones/token/{token}/decidir",
    "GET /api/oc/info/{token}",
    "POST /api/oc/confirmar/{token}",
    # OAuth: los llama Google/Microsoft, no el navegador con sesión Baiyer.
    "GET /api/gmail/auth",
    "GET /api/gmail/callback",
    "GET /api/outlook/auth",
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

# ── 3. DEUDA — esto tiene que llegar a CERO ─────────────────────────────────
# Rutas que todavía deducen la identidad de un `user_id` que manda el cliente.
# Están acá SÓLO para que activar el guardia no rompa la app mientras se
# migran (Bloque 3). Cada línea que se borra de esta lista es un agujero menos.
#
# No agregar rutas nuevas acá bajo ninguna circunstancia: una ruta nueva se
# escribe con `Depends(get_auth_context)` desde el principio. Esta lista sólo
# puede achicarse.
DEUDA_SIN_AUTENTICAR: frozenset[str] = frozenset({
    # Riesgo alto: leen o escriben datos de toda una organización.
    # Envían correo en nombre del usuario con su integración conectada.
    # Sesiones y feedback de búsqueda (Supplier Capability Intelligence).
    # Estos dos NO se pueden cerrar todavía sin romper cosas reales: el
    # servidor MCP (`mcp/tools/cotizar.py`) y la API pública
    # (`api_publica/endpoints/cotizar.py`) los consumen server-to-server por
    # HTTP contra localhost:8000, sin un JWT de usuario. El arreglo correcto no
    # es una exención por IP (falsificable, y ya cargamos con la complejidad de
    # `es_llamada_interna()` en llm_rate_limit.py) sino que esos dos caminos
    # llamen a la capa de servicios en proceso en vez de pegarle a su propia
    # API. Es refactor con alcance propio, no parte de este bloque.
    # Mientras tanto: rate limit por IP + topes de tamaño, y el único dato de
    # otra organización alcanzable es la lista de proveedores propios que
    # inyecta `incluir_proveedores_custom` si se acierta un UUID ajeno.
    "POST /api/identificar",
    "POST /api/buscar",
    # `procurement.py` es código muerto sobre tablas que no existen en
    # producción. No se migra: se borra (Bloque 5).
    "POST /api/procurement/eventos",
    "GET /api/procurement/eventos",
    "GET /api/procurement/eventos/{evento_id}",
    "POST /api/procurement/eventos/{evento_id}/items",
    "POST /api/procurement/items/{item_id}/proveedores",
    "DELETE /api/procurement/items/{item_id}",
    "DELETE /api/procurement/proveedores/{qs_id}",
    "PATCH /api/procurement/proveedores/{qs_id}/badge",
    "POST /api/procurement/cotizar",
    "POST /api/procurement/proveedores/{qs_id}/respuesta",
    "POST /api/procurement/proveedores/{qs_id}/seleccionar",
    "POST /api/procurement/proveedores/{qs_id}/emitir-oc",
    "POST /api/procurement/proveedores/{qs_id}/recibir",
    "GET /api/procurement/calendario",
})


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
    if plantilla.startswith(PREFIJOS_CON_GUARDIA_PROPIO):
        return
    clave = _clave(request)
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
