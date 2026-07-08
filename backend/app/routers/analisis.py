"""
Análisis comparativo de cotizaciones con Claude (Fase 3, Smart Procurement).

POST /api/analizar-cotizaciones recibe la lista de opciones (resultados de
búsqueda + respuestas de proveedores) y devuelve una matriz comparativa
multi-criterio con recomendación ganadora y razonamientos por opción.

Criterios: precio total, stock/confiabilidad, plazo + riesgo, ubicación
geográfica (local preferido si diferencia < 15%), y score de confianza del
proveedor basado en historial (procurement_ledger).
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["analisis"])


class OpcionCotizacion(BaseModel):
    proveedor_nombre: str
    fuente: Optional[str] = None
    pais: Optional[str] = "CL"
    precio: Optional[float] = None
    moneda: Optional[str] = "CLP"
    precio_cotizado: Optional[float] = None
    stock: Optional[int] = None
    stock_disponible: Optional[bool] = None
    plazo_entrega_estimado: Optional[str] = None
    plazo_entrega_dias: Optional[int] = None
    condiciones: Optional[str] = None
    url: Optional[str] = None
    envio_gratis: Optional[bool] = None
    rating: Optional[float] = None


class AnalizarRequest(BaseModel):
    user_id: str
    item_nombre: str
    cantidad: int = 1
    opciones: list[OpcionCotizacion]


SCHEMA_ANALISIS = {
    "type": "object",
    "properties": {
        "matriz_comparativa": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "proveedor": {"type": "string"},
                    "precio_total_estimado_clp": {"type": ["number", "null"]},
                    "desglose_costos": {
                        "type": "object",
                        "properties": {
                            "producto": {"type": ["number", "null"]},
                            "transporte_estimado": {"type": ["number", "null"]},
                            "aranceles_estimados": {"type": ["number", "null"]},
                            "margen_riesgo": {"type": ["number", "null"]},
                        },
                        "required": ["producto", "transporte_estimado", "aranceles_estimados", "margen_riesgo"],
                        "additionalProperties": False,
                    },
                    "score_precio": {"type": "integer"},
                    "score_disponibilidad": {"type": "integer"},
                    "score_plazo": {"type": "integer"},
                    "score_confianza": {"type": "integer"},
                    "score_total": {"type": "integer"},
                    "riesgos": {"type": "array", "items": {"type": "string"}},
                    "es_local": {"type": "boolean"},
                },
                "required": [
                    "proveedor", "precio_total_estimado_clp", "desglose_costos",
                    "score_precio", "score_disponibilidad", "score_plazo",
                    "score_confianza", "score_total", "riesgos", "es_local",
                ],
                "additionalProperties": False,
            },
        },
        "recomendacion_ganadora": {
            "type": "object",
            "properties": {
                "proveedor": {"type": "string"},
                "por_que": {"type": "string"},
            },
            "required": ["proveedor", "por_que"],
            "additionalProperties": False,
        },
        "razonamientos_por_opcion": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "opcion": {"type": "string"},
                    "por_que_no": {"type": "string"},
                },
                "required": ["opcion", "por_que_no"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["matriz_comparativa", "recomendacion_ganadora", "razonamientos_por_opcion"],
    "additionalProperties": False,
}

PROMPT_SISTEMA = """Eres un analista de procurement senior para PYMEs chilenas.
Analiza las opciones de compra con criterio multi-dimensional:

1. PRECIO TOTAL: precio del producto + transporte estimado + aranceles si es importado
   (importaciones a Chile: ~6% arancel general si no hay TLC, IVA 19% sobre CIF; desde
   USA/China/UE hay TLC vigente, arancel 0% en la mayoría de las partidas).
2. DISPONIBILIDAD: stock confirmado > stock declarado > sin información. Penaliza datos ausentes.
3. PLAZO Y RIESGO: entrega local (1-5 días) vs importación (15-45 días). Considera riesgo
   logístico y geopolítico para orígenes lejanos.
4. UBICACIÓN: prefiere proveedor local (Chile) si la diferencia de precio total es menor al 15%.
5. CONFIANZA: usa el historial de compras entregado (n_compras previas con cada proveedor).

Scores de 0 a 100 por criterio. score_total es el promedio ponderado:
precio 35%, disponibilidad 20%, plazo 20%, confianza 25%.
Sé concreto en los razonamientos: cita números, no generalidades."""


def _historial_confianza(sb, user_id: str, proveedores: list[str]) -> dict[str, int]:
    """n_compras previas por proveedor desde el ledger. Nunca lanza."""
    try:
        res = (
            sb.table("procurement_ledger").select("proveedor_nombre")
            .eq("user_id", user_id).in_("proveedor_nombre", proveedores).execute()
        )
        conteo: dict[str, int] = {}
        for r in (res.data or []):
            conteo[r["proveedor_nombre"]] = conteo.get(r["proveedor_nombre"], 0) + 1
        return conteo
    except Exception:
        return {}


@router.post("/analizar-cotizaciones")
async def analizar_cotizaciones(req: AnalizarRequest):
    from app.config import settings

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY no configurada en .env")
    if not req.opciones:
        raise HTTPException(status_code=400, detail="Se requiere al menos una opción")

    # Historial de compras para score de confianza
    from app.services.supabase import get_supabase
    sb = get_supabase()
    historial = _historial_confianza(sb, req.user_id, [o.proveedor_nombre for o in req.opciones])

    opciones_data = []
    for o in req.opciones:
        d = o.model_dump()
        d["n_compras_previas"] = historial.get(o.proveedor_nombre, 0)
        opciones_data.append(d)

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-opus-4-8",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=PROMPT_SISTEMA,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA_ANALISIS}},
            messages=[{
                "role": "user",
                "content": (
                    f"Ítem a comprar: {req.item_nombre} (cantidad: {req.cantidad})\n\n"
                    f"Opciones disponibles:\n{json.dumps(opciones_data, ensure_ascii=False, indent=2, default=str)}"
                ),
            }],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error con Claude API: {e}")

    if response.stop_reason == "refusal":
        raise HTTPException(status_code=502, detail="Claude no pudo procesar el análisis")

    texto = next((b.text for b in response.content if b.type == "text"), None)
    if not texto:
        raise HTTPException(status_code=502, detail="Respuesta vacía de Claude")

    try:
        analisis = json.loads(texto)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Claude no retornó JSON válido")

    return {
        "item": req.item_nombre,
        "cantidad": req.cantidad,
        "n_opciones": len(req.opciones),
        "historial_usado": historial,
        **analisis,
    }
