from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, identificar, buscar, gmail, oc, suppliers, calendario, recurrencias, estadisticas, facturas, proveedores_import, proyectos, reportes, chat, historico, procurement, ledger, analisis, aprobaciones, listas, contacto, cotizaciones as cotizaciones_router
from app.mcp import oauth as mcp_oauth
from app.mcp import transport as mcp_transport
from app.api_publica.router import router as api_v1_router, register_error_handlers
from app.api_publica.error_handler import ClariaAPIError

app = FastAPI(
    title="Cotizador Inteligente API",
    version="0.1.0",
    description="API para automatizacion de cotizaciones de procurement"
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

app.include_router(health.router)
app.include_router(identificar.router)
app.include_router(buscar.router)
app.include_router(gmail.router)
app.include_router(oc.router)
app.include_router(suppliers.router)
app.include_router(calendario.router)
app.include_router(recurrencias.router)
app.include_router(estadisticas.router)
app.include_router(facturas.router)
app.include_router(proveedores_import.router)
app.include_router(proyectos.router)
app.include_router(reportes.router)
app.include_router(chat.router)
app.include_router(historico.router)
app.include_router(procurement.router)
app.include_router(ledger.router)
app.include_router(analisis.router)
app.include_router(aprobaciones.router)
app.include_router(listas.router)
app.include_router(contacto.router)
app.include_router(cotizaciones_router.router)
app.include_router(mcp_oauth.router)
app.include_router(mcp_transport.router)
app.include_router(api_v1_router)
register_error_handlers(app)


@app.on_event("startup")
async def startup_event():
    from app.services.cron import start_cron
    start_cron()


@app.get("/")
async def root():
    return {"status": "ok", "producto": "Cotizador Inteligente", "version": "0.1.0"}
