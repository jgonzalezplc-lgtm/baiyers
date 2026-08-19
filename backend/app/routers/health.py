from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "etapa": "1 - Base tecnica",
        "environment": settings.environment,
    }
