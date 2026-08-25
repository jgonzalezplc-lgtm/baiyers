from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, identificar, buscar, gmail, outlook, oc, suppliers, calendario, recurrencias, estadisticas, facturas, proveedores_import, proveedores, proyectos, reportes, chat, historico, analisis, aprobaciones, listas, rfq, workflows, contacto, onboarding, cuenta, notificaciones, procurement_profile, search_feedback, admin_control_plane, organizacion, mail_templates, cotizaciones as cotizaciones_router
from app.mcp import oauth as mcp_oauth
from app.mcp import transport as mcp_transport
from app.mcp import discovery as mcp_discovery
from app.api_publica.router import router as api_v1_router, register_error_handlers
from app.api_publica.error_handler import ClariaAPIError

from fastapi import Depends
from app.config import settings
from app.services.tenant_guard import exigir_sesion

# `/docs`, `/redoc` y `/openapi.json` sólo fuera de producción. En prod servían
# el mapa completo de ~200 endpoints, incluido todo el plano administrativo
# (`/api/admin-control-plane/*`: dump de tablas, correos de usuarios,
# recuperación de contraseña de cualquiera). No es una vulnerabilidad por sí
# sola —`tenant_guard` cierra las rutas— pero le ahorra a un atacante todo el
# trabajo de descubrimiento. Local sigue igual de cómodo.
_docs = {} if not settings.is_production else {
    "docs_url": None, "redoc_url": None, "openapi_url": None,
}

app = FastAPI(
    title="Cotizador Inteligente API",
    version="0.1.0",
    description="API para automatizacion de cotizaciones de procurement",
    # Deny-by-default: toda ruta /api exige sesión verificada salvo las
    # listadas explícitamente en tenant_guard. Un endpoint nuevo nace cerrado.
    dependencies=[Depends(exigir_sesion)],
    **_docs,
)

# Orígenes permitidos: localhost + los definidos en CORS_ORIGINS (coma-separados),
# p.ej. "https://cotizador.cl,https://www.cotizador.cl". En producción, define esa
# variable con tu dominio final.
import os

_cors_extra = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *_cors_extra],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Sin esto, una excepción que no sea HTTPException (KeyError, un error de
# postgrest, etc.) se escapa hasta el ServerErrorMiddleware por defecto de
# Starlette — que queda AFUERA del middleware de CORS agregado arriba, así
# que su respuesta ("Internal Server Error" en texto plano) nunca lleva
# headers de CORS. El navegador entonces bloquea la lectura de esa
# respuesta y la reporta como "Failed to fetch", sin mostrar el status real
# (500) ni ningún detalle — un bug real encontrado en producción con
# /api/onboarding/sesion/{id}/confirmar. Este handler corre DENTRO del
# middleware de CORS (FastAPI lo intercepta antes de llegar al
# ServerErrorMiddleware), así que cualquier error no manejado se ve como un
# 500 JSON normal, con CORS, en vez de una falla opaca de red.
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse


@app.exception_handler(HTTPException)
async def manejador_http_exception(request: Request, exc: HTTPException):
    # OAuth requiere `error` en el nivel superior (RFC 6749/7591), mientras
    # FastAPI normalmente lo envolvería dentro de `detail`.
    if request.url.path.startswith("/api/mcp/oauth") and isinstance(exc.detail, dict) and exc.detail.get("error"):
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(Exception)
async def manejador_excepciones_no_capturadas(request: Request, exc: Exception):
    import traceback
    print(f"[UNCAUGHT] {request.method} {request.url.path}: {exc!r}")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor. Intenta de nuevo en unos segundos."})


app.include_router(health.router)
app.include_router(identificar.router)
app.include_router(buscar.router)
app.include_router(gmail.router)
app.include_router(outlook.router)
app.include_router(oc.router)
app.include_router(suppliers.router)
app.include_router(calendario.router)
app.include_router(recurrencias.router)
app.include_router(estadisticas.router)
app.include_router(facturas.router)
app.include_router(proveedores_import.router)
app.include_router(proveedores.router)
app.include_router(proyectos.router)
app.include_router(reportes.router)
app.include_router(chat.router)
app.include_router(historico.router)
app.include_router(analisis.router)
app.include_router(aprobaciones.router)
app.include_router(listas.router)
app.include_router(rfq.router)
app.include_router(workflows.router)
app.include_router(contacto.router)
app.include_router(onboarding.router)
app.include_router(cuenta.router)
app.include_router(notificaciones.router)
app.include_router(procurement_profile.router)
app.include_router(search_feedback.router)
app.include_router(admin_control_plane.router)
app.include_router(organizacion.router)
app.include_router(mail_templates.router)
app.include_router(cotizaciones_router.router)
app.include_router(mcp_oauth.router)
app.include_router(mcp_transport.router)
app.include_router(mcp_discovery.router)
app.include_router(api_v1_router)
register_error_handlers(app)


@app.on_event("startup")
async def startup_event():
    from app.config import settings
    from app.mcp.streamable import start_streamable_server
    from app.services.gemini_budget import instrumentar as instrumentar_gemini

    # Mide el gasto de Gemini envolviendo el SDK una sola vez, en vez de tocar
    # los 20 sitios que crean un GenerativeModel. Sólo avisa por log: nunca
    # bloquea una llamada.
    instrumentar_gemini()

    await start_streamable_server()

    if settings.should_run_cron:
        from app.services.web_quote_service import recover_web_quote_jobs
        await recover_web_quote_jobs()
        from app.services.cron import start_cron
        start_cron()
    else:
        print(f"[Cron] Deshabilitado en environment={settings.environment}")


@app.on_event("shutdown")
async def shutdown_event():
    from app.mcp.streamable import stop_streamable_server
    await stop_streamable_server()


@app.get("/")
async def root():
    from app.config import settings

    return {
        "status": "ok",
        "producto": "Cotizador Inteligente",
        "version": "0.1.0",
        "environment": settings.environment,
    }


# Debe ir al final: el mount raíz recibe /api/mcp y los well-known con path,
# mientras los routers FastAPI anteriores conservan prioridad.
from app.mcp.streamable import streamable_http_app
app.mount("/", streamable_http_app)
