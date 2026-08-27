"""Tokens OAuth opacos, revocables y ligados al recurso MCP."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from mcp.server.auth.provider import AccessToken

from app.config import settings
from app.services.supabase import ejecutar_maybe_single, get_supabase


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(48)}"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def registrar_conexion(
    user_id: str,
    client_id: str,
    scopes: list[str],
    access_token: str,
) -> None:
    """Guarda el resumen visible de una conexión OAuth MCP.

    El registro es derivado de un token válido, por lo que también se actualiza
    al usar una sesión emitida antes de que existiera ``mcp_connections``.
    Nunca se almacena el token en claro.
    """
    ahora = _iso(datetime.now(timezone.utc))
    get_supabase().table("mcp_connections").upsert({
        "user_id": user_id,
        "client_id": client_id,
        "scopes": scopes,
        "token_hash": token_hash(access_token)[:16],
        "connected_at": ahora,
        "last_used_at": ahora,
    }, on_conflict="user_id,client_id").execute()


def issue_token_pair(user_id: str, organization_id: str, client_id: str, scopes: list[str], resource: str) -> dict:
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    access_raw, refresh_raw = new_token("baiyer_at"), new_token("baiyer_rt")
    family_id = str(uuid4())
    access_exp = now + timedelta(minutes=settings.mcp_access_token_minutes)
    refresh_exp = now + timedelta(days=settings.mcp_refresh_token_days)
    common = {
        "user_id": user_id, "organization_id": organization_id,
        "client_id": client_id, "scopes": scopes, "resource": resource,
        "family_id": family_id,
    }
    sb.table("mcp_oauth_tokens").insert([
        {**common, "token_hash": token_hash(access_raw), "token_type": "access", "expires_at": _iso(access_exp)},
        {**common, "token_hash": token_hash(refresh_raw), "token_type": "refresh", "expires_at": _iso(refresh_exp)},
    ]).execute()
    return {
        "access_token": access_raw, "refresh_token": refresh_raw,
        "token_type": "Bearer", "expires_in": settings.mcp_access_token_minutes * 60,
        "scope": " ".join(scopes),
    }


def load_token(raw: str, token_type: str = "access") -> Optional[dict]:
    sb = get_supabase()
    response = ejecutar_maybe_single(
        sb.table("mcp_oauth_tokens").select("*")
        .eq("token_hash", token_hash(raw)).eq("token_type", token_type)
        .is_("revoked_at", "null").gt("expires_at", _iso(datetime.now(timezone.utc)))
        .maybe_single()
    )
    return response.data


def rotate_refresh_token(raw: str) -> Optional[dict]:
    old_hash = token_hash(raw)
    new_access, new_refresh = new_token("baiyer_at"), new_token("baiyer_rt")
    now = datetime.now(timezone.utc)
    response = get_supabase().rpc("mcp_rotate_refresh_token", {
        "p_old_hash": old_hash,
        "p_new_refresh_hash": token_hash(new_refresh),
        "p_new_access_hash": token_hash(new_access),
        "p_access_expires_at": _iso(now + timedelta(minutes=settings.mcp_access_token_minutes)),
        "p_refresh_expires_at": _iso(now + timedelta(days=settings.mcp_refresh_token_days)),
    }).execute()
    if not response.data:
        return None
    data = response.data
    return {
        "access_token": new_access, "refresh_token": new_refresh,
        "token_type": "Bearer", "expires_in": settings.mcp_access_token_minutes * 60,
        "scope": " ".join(data.get("scopes") or []),
    }


def revoke_token(raw: str) -> bool:
    response = get_supabase().rpc("mcp_revoke_token_family", {"p_token_hash": token_hash(raw)}).execute()
    return bool(response.data)


def revoke_token_family_por_cliente(user_id: str, client_id: str) -> int:
    """Revoca todos los tokens vivos de ese cliente para ese usuario.

    Lo usa el botón "Desconectar" de `/integraciones`, que sólo conoce el
    `client_id` — no el token en crudo, que nunca sale del cliente MCP. Marca
    `revoked_at` en vez de borrar: el historial de qué estuvo conectado y
    cuándo se cortó es justamente lo auditable.
    """
    sb = get_supabase()
    ahora = _iso(datetime.now(timezone.utc))
    response = (
        sb.table("mcp_oauth_tokens").update({"revoked_at": ahora})
        .eq("user_id", user_id).eq("client_id", client_id)
        .is_("revoked_at", "null").execute()
    )
    return len(response.data or [])


class BaiyerTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        row = load_token(token, "access")
        if not row or row.get("resource") != settings.mcp_resource_url:
            return None
        try:
            ahora = _iso(datetime.now(timezone.utc))
            get_supabase().table("mcp_oauth_tokens").update({
                "last_used_at": ahora
            }).eq("id", row["id"]).execute()
            registrar_conexion(row["user_id"], row["client_id"], row.get("scopes") or [], token)
        except Exception:
            # El acceso MCP no debe caerse si falla sólo el resumen de UI.
            pass
        expires_at = int(datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")).timestamp())
        return AccessToken(
            token=token, client_id=row["client_id"], scopes=row.get("scopes") or [],
            expires_at=expires_at, resource=row["resource"], subject=row["user_id"],
            claims={"organization_id": row["organization_id"]},
        )
