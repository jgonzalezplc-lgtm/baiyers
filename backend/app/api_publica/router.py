"""Router principal de la API publica v1 de Claria."""
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api_publica.auth import (
    verificar_api_key, crear_api_key, revocar_api_key, listar_api_keys,
    plan_de_organizacion,
)
from app.api_publica.error_handler import ClariaAPIError
from app.api_publica.endpoints import cotizar, oc, proveedores, estadisticas, webhooks

router = APIRouter(prefix="/api/v1", tags=["API Pública v1"])

# Register all sub-routers
router.include_router(cotizar.router)
router.include_router(oc.router)
router.include_router(proveedores.router)
router.include_router(estadisticas.router)
router.include_router(webhooks.router)


# ─── Health & info ────────────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def api_root():
    return {
        "api": "Claria API",
        "version": "v1",
        "status": "ok",
        "docs": "https://docs.claria.cc",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/ping", summary="Health check")
async def ping(client_ctx: dict = Depends(verificar_api_key)):
    """Verifica conectividad y validez de la API key."""
    return {
        "pong": True,
        "plan": client_ctx["plan"],
        "test_mode": client_ctx["is_test"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ─── API Key management (sesion web de Supabase, NO api_key) ──────────────────
# Ojo: estos tres endpoints son los que EMITEN la api_key, así que no pueden
# autenticarse con `verificar_api_key` como el resto de `/api/v1`. Usan la sesión
# web (`get_auth_context`), igual que cualquier ruta interna.
#
# Hasta el 2026-08-25 la identidad venía en el header `X-Claria-User-Id` y el plan
# en `X-Claria-User-Plan`, ambos sin verificar: con el UUID de un usuario de otra
# empresa se podía emitir una key `live` válida contra su organización y elegirse
# el plan `enterprise`. `tenant_guard` no lo atrapaba porque exime el prefijo
# `/api/v1` entero asumiendo que todo ahí adentro va por api_key.

from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

class CreateKeyRequest(BaseModel):
    nombre: str
    modo: str = "live"  # live | test


@router.post("/keys", summary="Crear API key", status_code=201, tags=["API Keys"])
async def crear_key(
    body: CreateKeyRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Crea una nueva API key. Llamado desde la UI /developers."""
    return await crear_api_key(
        ctx.actor_user_id, body.nombre, plan_de_organizacion(ctx.organization_id), body.modo,
    )


@router.get("/keys", summary="Listar API keys", tags=["API Keys"])
async def listar_keys(ctx: AuthContext = Depends(get_auth_context)):
    keys = await listar_api_keys(ctx.actor_user_id)
    return {"keys": keys}


@router.delete("/keys/{key_id}", summary="Revocar API key", tags=["API Keys"])
async def revocar_key(key_id: str, ctx: AuthContext = Depends(get_auth_context)):
    await revocar_api_key(key_id, ctx.actor_user_id)
    return {"revocada": True, "key_id": key_id}


# ─── Error handler global para ClariaAPIError ─────────────────────────────────

from fastapi import FastAPI

def register_error_handlers(app: FastAPI):
    @app.exception_handler(ClariaAPIError)
    async def claria_error_handler(request: Request, exc: ClariaAPIError):
        return exc.to_response()
