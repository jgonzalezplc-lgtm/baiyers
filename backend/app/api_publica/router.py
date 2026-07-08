"""Router principal de la API publica v1 de Claria."""
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api_publica.auth import verificar_api_key, crear_api_key, revocar_api_key, listar_api_keys
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


# ─── API Key management (autenticado con API key o sesion web) ────────────────

from fastapi import Header
from pydantic import BaseModel

class CreateKeyRequest(BaseModel):
    nombre: str
    modo: str = "live"  # live | test


@router.post("/keys", summary="Crear API key", status_code=201, tags=["API Keys"])
async def crear_key(
    body: CreateKeyRequest,
    x_claria_user_id: str = Header(..., description="User ID (solo para uso interno desde /developers)"),
    x_claria_user_plan: str = Header(default="free"),
):
    """Crea una nueva API key. Llamado desde la UI /developers."""
    result = await crear_api_key(x_claria_user_id, body.nombre, x_claria_user_plan, body.modo)
    return result


@router.get("/keys", summary="Listar API keys", tags=["API Keys"])
async def listar_keys(
    x_claria_user_id: str = Header(...),
):
    keys = await listar_api_keys(x_claria_user_id)
    return {"keys": keys}


@router.delete("/keys/{key_id}", summary="Revocar API key", tags=["API Keys"])
async def revocar_key(
    key_id: str,
    x_claria_user_id: str = Header(...),
):
    await revocar_api_key(key_id, x_claria_user_id)
    return {"revocada": True, "key_id": key_id}


# ─── Error handler global para ClariaAPIError ─────────────────────────────────

from fastapi import FastAPI

def register_error_handlers(app: FastAPI):
    @app.exception_handler(ClariaAPIError)
    async def claria_error_handler(request: Request, exc: ClariaAPIError):
        return exc.to_response()
