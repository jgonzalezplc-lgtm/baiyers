from fastapi import APIRouter, Depends
from app.config import settings
from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "etapa": "1 - Base tecnica",
        "environment": settings.environment,
    }


@router.get("/gasto-ia")
async def gasto_ia(ctx: AuthContext = Depends(get_auth_context)):
    """Gasto estimado de Gemini del día, para mirar sin entrar a AI Studio.

    Es una estimación en memoria y por proceso (ver `services/gemini_budget.py`),
    no un dato contable. Exige sesión: revela el ritmo de uso de la plataforma.
    """
    from app.services.gemini_budget import estado
    return estado()
