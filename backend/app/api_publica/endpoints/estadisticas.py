"""API publica — Estadisticas y analitica."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api_publica.auth import verificar_api_key
from supabase import create_client
from app.config import settings

router = APIRouter()
SUPABASE = create_client(settings.supabase_url, settings.supabase_service_key)


def _periodo_a_fechas(periodo: str) -> tuple[str, str]:
    """Convierte string de periodo a fechas ISO."""
    hoy = datetime.utcnow()
    if periodo == "ultimo_mes":
        desde = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)
        hasta = hoy.replace(day=1) - timedelta(seconds=1)
    elif periodo == "mes_actual":
        desde = hoy.replace(day=1)
        hasta = hoy
    elif periodo == "ultimo_trimestre":
        desde = hoy - timedelta(days=90)
        hasta = hoy
    elif periodo == "ultimo_año":
        desde = hoy - timedelta(days=365)
        hasta = hoy
    else:  # default: mes actual
        desde = hoy.replace(day=1)
        hasta = hoy
    return desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")


@router.get("/estadisticas/gastos", summary="Estadisticas de gastos")
async def estadisticas_gastos(
    periodo: str = Query("mes_actual", description="ultimo_mes|mes_actual|ultimo_trimestre|ultimo_año"),
    agrupacion: str = Query("por_mes", description="por_categoria|por_proveedor|por_mes"),
    client_ctx: dict = Depends(verificar_api_key),
):
    """Retorna estadisticas detalladas de gasto en procurement."""
    user_id = client_ctx["user_id"]
    desde, hasta = _periodo_a_fechas(periodo)

    try:
        ocs_resp = SUPABASE.table("ordenes_compra").select(
            "total_clp, estado, created_at, proveedor_id"
        ).eq("user_id", user_id).gte("created_at", desde).lte("created_at", hasta + "T23:59:59").execute()
        ocs = ocs_resp.data or []
    except Exception:
        ocs = []

    total = sum(o.get("total_clp", 0) for o in ocs if o.get("estado") != "cancelada")
    confirmadas = sum(1 for o in ocs if o.get("estado") == "confirmada")

    # Group by month
    por_mes: dict[str, int] = {}
    for oc in ocs:
        if oc.get("estado") == "cancelada":
            continue
        mes = oc.get("created_at", "")[:7]
        por_mes[mes] = por_mes.get(mes, 0) + oc.get("total_clp", 0)

    return {
        "periodo": periodo,
        "desde": desde,
        "hasta": hasta,
        "gasto_total_clp": total,
        "ocs_emitidas": len(ocs),
        "ocs_confirmadas": confirmadas,
        "gasto_por_mes": [
            {"mes": k, "gasto_clp": v}
            for k, v in sorted(por_mes.items())
        ],
        "moneda": "CLP",
        "generado_en": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/estadisticas/proveedores", summary="Metricas por proveedor")
async def estadisticas_proveedores(
    limit: int = Query(10, ge=1, le=50),
    client_ctx: dict = Depends(verificar_api_key),
):
    """Proveedores con mas transacciones y mejores scores."""
    user_id = client_ctx["user_id"]

    try:
        resp = SUPABASE.table("proveedores").select(
            "id, nombre, score, total_cotizaciones, email, ciudad"
        ).eq("user_id", user_id).order("score", desc=True).limit(limit).execute()
        proveedores = resp.data or []
    except Exception:
        proveedores = []

    return {
        "top_proveedores": proveedores,
        "total": len(proveedores),
        "generado_en": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/estadisticas/uso_api", summary="Uso de la API este mes")
async def estadisticas_uso(
    client_ctx: dict = Depends(verificar_api_key),
):
    """Retorna el uso de la API del cliente este mes."""
    from app.api_publica.rate_limiter import usage_summary
    user_id = client_ctx["user_id"]
    plan = client_ctx["plan"]

    summary = usage_summary(user_id, plan)

    return {
        "plan": plan,
        "mes": datetime.utcnow().strftime("%Y-%m"),
        **summary,
        "generado_en": datetime.utcnow().isoformat() + "Z",
    }
