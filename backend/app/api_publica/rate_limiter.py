"""Rate limiting y limites de plan para la API publica."""
from collections import defaultdict
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

from app.api_publica.error_handler import error_rate_limit, error_plan_limit


@dataclass
class PlanConfig:
    cotizaciones_mes: int        # -1 = ilimitado
    ocs_mes: int
    batch: bool
    webhooks: int                # -1 = ilimitado
    rate_por_minuto: int


PLANES: dict[str, PlanConfig] = {
    "free": PlanConfig(
        cotizaciones_mes=3,
        ocs_mes=0,
        batch=False,
        webhooks=0,
        rate_por_minuto=5,
    ),
    "starter": PlanConfig(
        cotizaciones_mes=20,
        ocs_mes=0,
        batch=False,
        webhooks=0,
        rate_por_minuto=10,
    ),
    "pro": PlanConfig(
        cotizaciones_mes=100,
        ocs_mes=100,
        batch=False,
        webhooks=2,
        rate_por_minuto=30,
    ),
    "business": PlanConfig(
        cotizaciones_mes=1000,
        ocs_mes=1000,
        batch=True,
        webhooks=10,
        rate_por_minuto=100,
    ),
    "enterprise": PlanConfig(
        cotizaciones_mes=-1,
        ocs_mes=-1,
        batch=True,
        webhooks=-1,
        rate_por_minuto=500,
    ),
}


def get_plan_config(plan: str) -> PlanConfig:
    return PLANES.get(plan, PLANES["free"])


# ─── In-memory rate limiter (use Redis in production) ──────────────────────────

class _Window:
    """Sliding window counter."""
    def __init__(self):
        self.requests: list[datetime] = []

    def count_recent(self, seconds: int) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        self.requests = [t for t in self.requests if t > cutoff]
        return len(self.requests)

    def add(self):
        self.requests.append(datetime.utcnow())


_windows: dict[str, _Window] = defaultdict(_Window)


def check_rate_limit(api_key_id: str, plan: str):
    """Raise 429 if request rate exceeded."""
    config = get_plan_config(plan)
    window = _windows[api_key_id]
    count = window.count_recent(60)
    if count >= config.rate_por_minuto:
        error_rate_limit(config.rate_por_minuto)
    window.add()


# ─── Monthly usage counters (backed by DB in practice) ────────────────────────

# {user_id: {recurso: count, mes: "YYYY-MM"}}
_monthly_usage: dict[str, dict] = defaultdict(lambda: {"cotizaciones": 0, "ocs": 0, "mes": ""})


def _get_current_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def get_monthly_usage(user_id: str) -> dict:
    usage = _monthly_usage[user_id]
    if usage["mes"] != _get_current_month():
        _monthly_usage[user_id] = {"cotizaciones": 0, "ocs": 0, "mes": _get_current_month()}
    return _monthly_usage[user_id]


def check_and_increment(user_id: str, plan: str, recurso: str):
    """Check monthly plan limit and increment counter. Raises 402 if exceeded."""
    config = get_plan_config(plan)
    limite = getattr(config, f"{recurso}_mes")
    if limite == -1:
        return  # ilimitado

    usage = get_monthly_usage(user_id)
    current = usage.get(recurso, 0)

    if current >= limite:
        error_plan_limit(recurso, plan, limite, current)

    _monthly_usage[user_id][recurso] = current + 1


def usage_summary(user_id: str, plan: str) -> dict:
    """Return usage summary for dashboard display."""
    config = get_plan_config(plan)
    usage = get_monthly_usage(user_id)
    return {
        "cotizaciones": {
            "usadas": usage.get("cotizaciones", 0),
            "limite": config.cotizaciones_mes,
            "ilimitado": config.cotizaciones_mes == -1,
        },
        "ocs": {
            "usadas": usage.get("ocs", 0),
            "limite": config.ocs_mes,
            "ilimitado": config.ocs_mes == -1,
        },
        "batch_disponible": config.batch,
        "webhooks_limite": config.webhooks,
        "rate_por_minuto": config.rate_por_minuto,
    }
