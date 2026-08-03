"""Telemetría append-only para CapoDiTutti.

Nunca bloquea el flujo de compra si la migración aún no está aplicada o
Supabase está temporalmente caído. No almacena prompts, respuestas, emails,
tokens de autenticación ni otros secretos; solo metadata operacional acotada.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4


DEFAULT_PRICES: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("google", "gemini-3.5-flash-lite"): (Decimal("0.30"), Decimal("2.50")),
    ("google", "gemini-2.5-flash"): (Decimal("0.30"), Decimal("2.50")),
}

FORBIDDEN_METADATA_KEYS = {
    "prompt", "response", "respuesta", "descripcion", "email", "password",
    "token", "access_token", "refresh_token", "authorization", "api_key",
}


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def sanitizar_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Conserva solo valores escalares/listas pequeñas y elimina PII/secrets."""
    limpia: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if key.lower() in FORBIDDEN_METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            limpia[key] = value[:300] if isinstance(value, str) else value
        elif isinstance(value, list):
            limpia[key] = [v for v in value[:20] if isinstance(v, (str, int, float, bool))]
    return limpia


def estimar_costo_usd(
    provider: str, model: str, input_tokens: int, output_tokens: int,
) -> tuple[Decimal, dict[str, Any]]:
    entrada, salida = DEFAULT_PRICES.get(
        (provider.lower(), model), (Decimal("0"), Decimal("0")),
    )
    costo = (
        Decimal(max(0, input_tokens)) * entrada
        + Decimal(max(0, output_tokens)) * salida
    ) / Decimal("1000000")
    snapshot = {
        "input_usd_million": float(entrada),
        "output_usd_million": float(salida),
        "currency": "USD",
        "catalog_version": "2026-08-03",
    }
    return costo.quantize(Decimal("0.00000001")), snapshot


def _organizacion_primaria(sb: Any, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    try:
        result = sb.rpc("primary_organization_for", {"p_user_id": user_id}).execute()
        return result.data or None
    except Exception:
        return None


def registrar_evento_producto(
    event_type: str,
    *,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    status: str = "success",
    clave_idempotencia: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    try:
        sb = _sb()
        org_id = organization_id or _organizacion_primaria(sb, user_id)
        payload = {
            "organization_id": org_id,
            "user_id": user_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "correlation_id": correlation_id,
            "status": status if status in {"success", "warning", "error"} else "error",
            "clave_idempotencia": clave_idempotencia,
            "metadata": sanitizar_metadata(metadata),
        }
        result = sb.table("product_events").insert(payload).execute()
        rows = result.data or []
        return rows[0].get("id") if rows else None
    except Exception as exc:
        print(f"[ControlPlane] product_event omitido: {type(exc).__name__}")
        return None


def registrar_uso_ia(
    *,
    feature: str,
    provider: str,
    requested_model: str,
    effective_model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    product_event_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    error: Optional[Exception] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    try:
        sb = _sb()
        org_id = organization_id or _organizacion_primaria(sb, user_id)
        costo, snapshot = estimar_costo_usd(provider, effective_model, input_tokens, output_tokens)
        payload = {
            "organization_id": org_id,
            "user_id": user_id,
            "product_event_id": product_event_id,
            "correlation_id": correlation_id or str(uuid4()),
            "feature": feature,
            "provider": provider.lower(),
            "requested_model": requested_model,
            "effective_model": effective_model,
            "fallback_used": requested_model != effective_model or status == "fallback",
            "input_tokens": max(0, int(input_tokens or 0)),
            "output_tokens": max(0, int(output_tokens or 0)),
            "cached_tokens": max(0, int(cached_tokens or 0)),
            "latency_ms": max(0, int(latency_ms or 0)),
            "estimated_cost_usd": str(costo),
            "pricing_snapshot": snapshot,
            "status": status if status in {"success", "fallback", "error", "timeout"} else "error",
            "error_type": type(error).__name__ if error else None,
            "error_message": str(error)[:300] if error else None,
            "metadata": sanitizar_metadata(metadata),
        }
        result = sb.table("ai_usage_events").insert(payload).execute()
        rows = result.data or []
        return rows[0].get("id") if rows else None
    except Exception as exc:
        print(f"[ControlPlane] ai_usage omitido: {type(exc).__name__}")
        return None
