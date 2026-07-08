"""Errores estandar para la API publica de Claria."""
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class ClariaAPIError(Exception):
    def __init__(self, codigo: str, mensaje: str, status_code: int = 400, extra: dict = None):
        self.codigo = codigo
        self.mensaje = mensaje
        self.status_code = status_code
        self.extra = extra or {}

    def to_response(self) -> JSONResponse:
        body = {"error": {"codigo": self.codigo, "mensaje": self.mensaje, **self.extra}}
        return JSONResponse(status_code=self.status_code, content=body)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def error_invalid_key():
    raise ClariaAPIError("INVALID_API_KEY", "La API key es invalida o no existe", 401)

def error_key_expired():
    raise ClariaAPIError("API_KEY_EXPIRED", "La API key ha expirado. Genera una nueva en /developers", 401)

def error_rate_limit(limite: int, por: str = "minuto"):
    raise ClariaAPIError(
        "RATE_LIMIT_EXCEEDED",
        f"Excediste el limite de {limite} requests/{por}. Espera un momento.",
        429,
        {"limite": limite, "por": por, "retry_after_segundos": 60},
    )

def error_plan_limit(recurso: str, plan: str, limite: int, usadas: int):
    # First day of next month
    hoy = datetime.utcnow()
    if hoy.month == 12:
        reinicia = datetime(hoy.year + 1, 1, 1)
    else:
        reinicia = datetime(hoy.year, hoy.month + 1, 1)

    raise ClariaAPIError(
        "PLAN_LIMIT_EXCEEDED",
        f"Excediste el limite de {limite} {recurso}/mes de tu plan {plan.title()}",
        402,
        {
            "plan_actual": plan,
            "limite": limite,
            "usadas": usadas,
            "reinicia_en": reinicia.isoformat() + "Z",
            "upgrade_url": "https://claria.cc/pricing",
        },
    )

def error_item_not_identified(item: str):
    raise ClariaAPIError(
        "ITEM_NOT_IDENTIFIED",
        f"No se pudo identificar el item: '{item}'. Intenta con mas detalle o numero de parte.",
        400,
        {"item_enviado": item, "sugerencia": "Incluye marca, modelo o numero de parte para mejor identificacion"},
    )

def error_not_found(recurso: str, id: str):
    raise ClariaAPIError("NOT_FOUND", f"{recurso} '{id}' no encontrado", 404)

def error_batch_not_available(plan: str):
    raise ClariaAPIError(
        "BATCH_NOT_AVAILABLE",
        f"Cotizacion batch no disponible en plan {plan.title()}. Requiere plan Business o Enterprise.",
        402,
        {"plan_actual": plan, "upgrade_url": "https://claria.cc/pricing"},
    )

def error_oc_already_confirmed(oc_id: str):
    raise ClariaAPIError("OC_ALREADY_CONFIRMED", f"La OC {oc_id} ya fue confirmada y no puede modificarse", 409)

def error_webhooks_limit(plan: str, limite: int):
    raise ClariaAPIError(
        "WEBHOOKS_LIMIT",
        f"Plan {plan.title()} permite maximo {limite} webhooks. Actualiza tu plan para agregar mas.",
        402,
        {"plan_actual": plan, "limite": limite, "upgrade_url": "https://claria.cc/pricing"},
    )
