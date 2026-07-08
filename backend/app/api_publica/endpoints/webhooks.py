"""API publica — Webhooks con retry logic y firma HMAC."""
import hashlib
import hmac
import json
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel, HttpUrl

from app.api_publica.auth import verificar_api_key
from app.api_publica.rate_limiter import get_plan_config
from app.api_publica.error_handler import error_not_found, error_webhooks_limit
from supabase import create_client
from app.config import settings

router = APIRouter()
SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)

EVENTOS_VALIDOS = {
    "oc.confirmada",
    "cotizacion.completada",
    "factura.recibida",
    "proveedor.respondio",
    "test.ping",
}

# Retry delays in seconds: inmediato, 5min, 30min, 2h, 24h
RETRY_DELAYS = [0, 300, 1800, 7200, 86400]


class WebhookConfig(BaseModel):
    url: str
    eventos: list[str]
    secret: Optional[str] = None


# ─── Firma HMAC ───────────────────────────────────────────────────────────────

def _firmar_payload(payload: dict, secret: str, timestamp: int) -> str:
    """Genera firma HMAC-SHA256 del payload."""
    msg = f"{timestamp}.{json.dumps(payload, separators=(',', ':'), sort_keys=True)}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


# ─── Envio con retry ──────────────────────────────────────────────────────────

async def _enviar_webhook(webhook_id: str, url: str, evento: str, payload: dict, secret_hash: Optional[str], intento: int = 1):
    """Envia un webhook con retry exponencial."""
    timestamp = int(datetime.utcnow().timestamp())

    headers = {
        "Content-Type": "application/json",
        "X-Claria-Event": evento,
        "X-Claria-Timestamp": str(timestamp),
        "User-Agent": "Claria-Webhook/1.0",
    }

    if secret_hash:
        firma = _firmar_payload(payload, secret_hash, timestamp)
        headers["X-Claria-Signature"] = f"sha256={firma}"

    status_code = None
    exitoso = False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            status_code = resp.status_code
            exitoso = 200 <= status_code < 300
    except Exception as e:
        status_code = 0

    # Log intent
    try:
        SUPABASE.table("webhook_logs").insert({
            "webhook_id": webhook_id,
            "evento": evento,
            "payload": json.dumps(payload),
            "status_code": status_code,
            "intentos": intento,
            "exitoso": exitoso,
            "enviado_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass

    # Update webhook last used
    try:
        SUPABASE.table("webhooks").update({
            "ultimo_envio_at": datetime.utcnow().isoformat(),
            "ultimo_status": status_code,
        }).eq("id", webhook_id).execute()
    except Exception:
        pass

    # Schedule retry if failed and more attempts remain
    if not exitoso and intento < len(RETRY_DELAYS):
        delay = RETRY_DELAYS[intento]
        if delay > 0:
            asyncio.create_task(_retry_after(delay, webhook_id, url, evento, payload, secret_hash, intento + 1))

    return exitoso


async def _retry_after(delay: int, *args):
    await asyncio.sleep(delay)
    await _enviar_webhook(*args)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/webhooks/configurar", summary="Configurar webhook", status_code=201)
async def configurar_webhook(
    body: WebhookConfig,
    client_ctx: dict = Depends(verificar_api_key),
):
    """
    Registra una URL para recibir eventos de Claria.
    El ERP puede suscribirse a: oc.confirmada, cotizacion.completada, factura.recibida, proveedor.respondio.
    """
    user_id = client_ctx["user_id"]
    plan = client_ctx["plan"]
    config = get_plan_config(plan)

    # Check plan limit
    try:
        existing = SUPABASE.table("webhooks").select("id").eq("user_id", user_id).eq("activo", True).execute()
        count = len(existing.data or [])
    except Exception:
        count = 0

    if config.webhooks != -1 and count >= config.webhooks:
        error_webhooks_limit(plan, config.webhooks)

    # Validate events
    invalid = [e for e in body.eventos if e not in EVENTOS_VALIDOS]
    if invalid:
        from fastapi import HTTPException
        raise HTTPException(400, f"Eventos invalidos: {invalid}. Validos: {list(EVENTOS_VALIDOS)}")

    secret_hash = _hash_secret(body.secret) if body.secret else None

    resp = SUPABASE.table("webhooks").insert({
        "user_id": user_id,
        "url": str(body.url),
        "eventos": body.eventos,
        "secret_hash": secret_hash,
        "activo": True,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()

    row = resp.data[0] if resp.data else {}
    return {
        "id": row.get("id", ""),
        "url": str(body.url),
        "eventos": body.eventos,
        "activo": True,
        "mensaje": f"Webhook configurado para {len(body.eventos)} eventos",
        "firma": "Activa — usa X-Claria-Signature para verificar" if body.secret else "Sin firma (recomendamos agregar un secret)",
        "creado_en": row.get("created_at", ""),
    }


@router.get("/webhooks", summary="Listar webhooks")
async def listar_webhooks(client_ctx: dict = Depends(verificar_api_key)):
    """Lista todos los webhooks configurados del cliente."""
    user_id = client_ctx["user_id"]

    try:
        resp = SUPABASE.table("webhooks").select(
            "id, url, eventos, activo, ultimo_envio_at, ultimo_status, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        webhooks = resp.data or []
    except Exception:
        webhooks = []

    # Get recent log count per webhook
    for wh in webhooks:
        try:
            logs_resp = SUPABASE.table("webhook_logs").select("id, exitoso").eq("webhook_id", wh["id"]).order("enviado_at", desc=True).limit(10).execute()
            wh["ultimos_logs"] = logs_resp.data or []
        except Exception:
            wh["ultimos_logs"] = []

    return {"webhooks": webhooks}


@router.delete("/webhooks/{webhook_id}", summary="Eliminar webhook")
async def eliminar_webhook(
    webhook_id: str,
    client_ctx: dict = Depends(verificar_api_key),
):
    user_id = client_ctx["user_id"]

    try:
        resp = SUPABASE.table("webhooks").select("id").eq("id", webhook_id).eq("user_id", user_id).single().execute()
        if not resp.data:
            error_not_found("Webhook", webhook_id)
    except Exception:
        error_not_found("Webhook", webhook_id)

    SUPABASE.table("webhooks").update({"activo": False}).eq("id", webhook_id).execute()
    return {"eliminado": True, "webhook_id": webhook_id}


@router.post("/webhooks/{webhook_id}/test", summary="Probar webhook")
async def probar_webhook(
    webhook_id: str,
    background_tasks: BackgroundTasks,
    client_ctx: dict = Depends(verificar_api_key),
):
    """Envia un evento de prueba al webhook especificado."""
    user_id = client_ctx["user_id"]

    try:
        resp = SUPABASE.table("webhooks").select("*").eq("id", webhook_id).eq("user_id", user_id).single().execute()
        wh = resp.data
    except Exception:
        wh = None

    if not wh:
        error_not_found("Webhook", webhook_id)

    payload = {
        "evento": "test.ping",
        "webhook_id": webhook_id,
        "mensaje": "Claria webhook de prueba",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    background_tasks.add_task(
        _enviar_webhook,
        webhook_id,
        wh["url"],
        "test.ping",
        payload,
        wh.get("secret_hash"),
        1,
    )

    return {
        "enviando": True,
        "url": wh["url"],
        "evento": "test.ping",
        "mensaje": "Evento de prueba enviado en background. Revisa el log en /api/v1/webhooks.",
    }


# ─── Funcion publica para disparar webhooks internamente ─────────────────────

async def disparar_evento(user_id: str, evento: str, payload: dict):
    """
    Llamada desde otros routers cuando ocurre un evento.
    Ej: disparar_evento(user_id, "oc.confirmada", {"oc_id": ..., ...})
    """
    try:
        resp = SUPABASE.table("webhooks").select("*").eq("user_id", user_id).eq("activo", True).execute()
        webhooks = resp.data or []
    except Exception:
        return

    for wh in webhooks:
        if evento in (wh.get("eventos") or []):
            asyncio.create_task(
                _enviar_webhook(wh["id"], wh["url"], evento, payload, wh.get("secret_hash"), 1)
            )
