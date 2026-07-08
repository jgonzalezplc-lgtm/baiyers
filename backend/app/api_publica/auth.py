"""Autenticacion por API Key para la API publica de Claria."""
import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import Header, Request
from supabase import create_client

from app.config import settings
from app.api_publica.error_handler import error_invalid_key, error_key_expired
from app.api_publica.rate_limiter import check_rate_limit

SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)

# Cache de keys para evitar DB hits en cada request (TTL 60s en produccion usarias Redis)
_key_cache: dict[str, dict] = {}
_cache_ts: dict[str, float] = {}
_CACHE_TTL = 60  # segundos


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _cache_get(key_hash: str) -> Optional[dict]:
    import time
    if key_hash in _key_cache:
        if time.time() - _cache_ts.get(key_hash, 0) < _CACHE_TTL:
            return _key_cache[key_hash]
        del _key_cache[key_hash]
    return None


def _cache_set(key_hash: str, data: dict):
    import time
    _key_cache[key_hash] = data
    _cache_ts[key_hash] = time.time()


async def verificar_api_key(
    request: Request,
    x_claria_key: str = Header(..., description="Tu API key de Claria (claria_live_xxx o claria_test_xxx)"),
) -> dict:
    """
    Dependency que verifica la API key y retorna el contexto del cliente.
    Uso: client = Depends(verificar_api_key)
    Retorna: {"user_id": ..., "plan": ..., "api_key_id": ..., "is_test": ...}
    """
    key_hash = _hash_key(x_claria_key)

    # Try cache first
    cached = _cache_get(key_hash)
    if cached:
        _log_usage(request, cached)
        return cached

    # Query Supabase
    try:
        resp = SUPABASE.table("api_keys").select(
            "id, user_id, plan, activa, expira_en, key_prefix"
        ).eq("key_hash", key_hash).single().execute()
        row = resp.data
    except Exception:
        error_invalid_key()

    if not row or not row.get("activa"):
        error_invalid_key()

    if row.get("expira_en") and datetime.fromisoformat(row["expira_en"].replace("Z", "+00:00")) < datetime.utcnow().replace(tzinfo=__import__("datetime").timezone.utc):
        error_key_expired()

    plan = row.get("plan", "free")
    client_ctx = {
        "user_id": row["user_id"],
        "plan": plan,
        "api_key_id": row["id"],
        "is_test": x_claria_key.startswith("claria_test_"),
    }

    _cache_set(key_hash, client_ctx)

    # Check rate limit
    check_rate_limit(row["id"], plan)

    # Update last used async (fire and forget)
    try:
        SUPABASE.table("api_keys").update(
            {"ultimo_uso_at": datetime.utcnow().isoformat()}
        ).eq("id", row["id"]).execute()
    except Exception:
        pass

    _log_usage(request, client_ctx)
    return client_ctx


def _log_usage(request: Request, client_ctx: dict):
    """Fire-and-forget usage log."""
    try:
        SUPABASE.table("api_usage_log").insert({
            "api_key_id": client_ctx["api_key_id"],
            "user_id": client_ctx["user_id"],
            "endpoint": str(request.url.path),
            "metodo": request.method,
            "ip_origen": request.client.host if request.client else None,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass


# ─── Key management helpers ────────────────────────────────────────────────────

def generar_api_key(modo: str = "live") -> tuple[str, str, str]:
    """
    Genera una nueva API key.
    Retorna (raw_key, key_hash, prefix)
    La raw_key se muestra UNA SOLA VEZ al usuario y luego se descarta.
    """
    raw = secrets.token_urlsafe(32)
    prefix = f"claria_{modo}_"
    full_key = prefix + raw
    key_hash = _hash_key(full_key)
    return full_key, key_hash, prefix


async def crear_api_key(user_id: str, nombre: str, plan: str, modo: str = "live") -> dict:
    """Crea una nueva API key en la base de datos. Retorna la key completa UNA SOLA VEZ."""
    full_key, key_hash, prefix = generar_api_key(modo)

    resp = SUPABASE.table("api_keys").insert({
        "user_id": user_id,
        "nombre": nombre,
        "key_hash": key_hash,
        "key_prefix": prefix,
        "plan": plan,
        "activa": True,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()

    row = resp.data[0] if resp.data else {}
    return {
        "id": row.get("id", ""),
        "nombre": nombre,
        "key": full_key,  # SOLO SE RETORNA UNA VEZ
        "prefix": prefix,
        "plan": plan,
        "created_at": row.get("created_at", ""),
        "advertencia": "Guarda esta key ahora — no la podras ver de nuevo",
    }


async def revocar_api_key(key_id: str, user_id: str):
    SUPABASE.table("api_keys").update({"activa": False}).eq("id", key_id).eq("user_id", user_id).execute()
    # Invalidate cache entries for this key
    _key_cache.clear()


async def listar_api_keys(user_id: str) -> list[dict]:
    resp = SUPABASE.table("api_keys").select(
        "id, nombre, key_prefix, plan, activa, ultimo_uso_at, expira_en, created_at"
    ).eq("user_id", user_id).order("created_at", desc=True).execute()
    return resp.data or []
