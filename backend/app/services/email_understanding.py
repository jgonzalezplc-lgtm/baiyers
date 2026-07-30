"""
Email Understanding Agent (Fase 1 del agente de Gmail).

Interpreta el cuerpo de un correo de un proveedor y, dado el contexto de los
ítems que se le solicitaron en ese hilo, propone actualizaciones de campos
estructurados con un nivel de confianza. NO escribe nada en la base de datos —
sólo devuelve propuestas; quien llama decide si las guarda como
`item_field_updates` (estado='propuesta') para revisión humana.

No inventa relaciones: si el modelo no puede asociar un dato a un ítem con
confianza razonable, debe devolver `entity_id: null` y quien orquesta lo deja
fuera o lo marca para aclaración.
"""
import asyncio
import json
from typing import Optional

# Campos que el agente puede proponer. Cualquier otro valor que devuelva el
# modelo se descarta (evita que un campo inventado ensucie el audit log).
CAMPOS_VALIDOS = {
    "precio_unitario", "moneda", "iva_incluido", "descuento",
    "disponibilidad", "stock_disponible", "fecha_disponibilidad",
    "plazo_entrega", "fecha_despacho", "lugar_entrega", "costo_despacho",
    "condiciones_pago", "porcentaje_anticipo", "vigencia_oferta",
    "marca", "modelo", "sku", "descripcion_tecnica", "unidad_medida",
    "cantidad_ofrecida", "producto_alternativo", "garantia", "observaciones",
}

PROMPT_BASE = """Eres un asistente de procurement B2B en Chile. Te doy el texto de un correo
que envió un PROVEEDOR respondiendo a una solicitud de cotización, y la lista de ítems
que se le pidieron (con su entity_id interno, nombre y proveedor).

Tu tarea: extraer del correo los datos que el proveedor entregó, asociándolos al
entity_id correcto. Si el correo menciona varios productos, sepára cada dato por
ítem. Si no puedes determinar con seguridad a qué entity_id corresponde un dato,
usa entity_id=null (NO adivines ni fuerces una relación).

Campos permitidos (usa exactamente estos nombres, en snake_case):
{campos}

Para cada dato que extraigas, evalúa tu propia confianza:
- 0.85 a 1.0: el dato es explícito y la asociación al ítem es clara.
- 0.5 a 0.84: el dato parece correcto pero la asociación al ítem tiene alguna ambigüedad.
- menor a 0.5: dato ambiguo, contradictorio, o no asociable — igual repórtalo así, no lo omitas.

Ítems solicitados en este hilo:
{items}

Correo del proveedor:
\"\"\"
{cuerpo}
\"\"\"

Responde SOLO JSON válido, sin markdown, con esta forma exacta:
{{
  "propuestas": [
    {{"entity_id": "string|null", "field": "string", "new_value": "string|number|boolean",
      "currency": "CLP|USD|EUR|null", "confidence": 0.0, "nota": "breve justificación"}}
  ],
  "respondio_todo": true,
  "requiere_aclaracion": false
}}
Si el correo no aporta ningún dato útil (ej: respuesta automática, fuera de oficina,
error de entrega), responde con "propuestas": [] y explica en "nota" a nivel de la
primera propuesta— pero como no hay propuestas, deja el arreglo vacío nomás."""


def _filtrar_propuesta(p: dict) -> Optional[dict]:
    field = p.get("field")
    if field not in CAMPOS_VALIDOS:
        return None
    if p.get("new_value") in (None, ""):
        return None
    try:
        confianza = float(p.get("confidence", 0))
    except (TypeError, ValueError):
        confianza = 0.0
    return {
        "entity_id": p.get("entity_id") or None,
        "field": field,
        "new_value": p["new_value"],
        "currency": p.get("currency") or None,
        "confidence": max(0.0, min(1.0, confianza)),
        "nota": p.get("nota") or "",
    }


async def extraer_actualizaciones(cuerpo: str, items_contexto: list[dict]) -> dict:
    """items_contexto: [{"entity_id": ..., "nombre": ..., "proveedor": ...}]

    Devuelve {"propuestas": [...], "respondio_todo": bool, "requiere_aclaracion": bool}.
    Ante cualquier falla del modelo, devuelve requiere_aclaracion=True con
    propuestas vacías (no inventa datos, deja para revisión humana)."""
    from app.config import settings

    vacio_seguro = {"propuestas": [], "respondio_todo": False, "requiere_aclaracion": True}

    texto = (cuerpo or "").strip()
    if not texto or not items_contexto:
        return vacio_seguro
    if not settings.gemini_api_key:
        return vacio_seguro

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = PROMPT_BASE.format(
        campos=", ".join(sorted(CAMPOS_VALIDOS)),
        items=json.dumps(items_contexto, ensure_ascii=False),
        cuerpo=texto[:6000],
    )

    try:
        resp = await asyncio.wait_for(model.generate_content_async(prompt), timeout=25.0)
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
    except Exception as e:
        print(f"[EmailUnderstanding] error de extracción: {e}")
        return vacio_seguro

    propuestas = [p for p in (_filtrar_propuesta(p) for p in data.get("propuestas", [])) if p]
    return {
        "propuestas": propuestas,
        "respondio_todo": bool(data.get("respondio_todo")),
        "requiere_aclaracion": bool(data.get("requiere_aclaracion")),
    }


# ─── Clasificador de respuestas a una Orden de Compra ──────────────────────
# A diferencia de una cotización, acá no hay campos que extraer: el correo ya
# tiene precio/condiciones acordados. Sólo interesa distinguir si el proveedor
# está acusando recibo de la OC o avisando que despachó el pedido.

PROMPT_OC = """Eres un asistente de procurement B2B en Chile. Un proveedor respondió a un
correo que le enviamos junto con una Orden de Compra (OC) adjunta en PDF.

Clasifica el correo en UNA sola categoría:
- "acuse_recibo": confirma que recibió la OC y la va a procesar (ej: "recibido, gracias",
  "confirmado, procedemos con el despacho", "ok, quedamos en eso").
- "despacho": avisa que el pedido ya fue despachado/enviado (ej: menciona guía de despacho,
  transportista, que el pedido salió o está en camino, número de seguimiento).
- "otro": cualquier otra cosa (pregunta, rechazo, fuera de oficina, no aporta información
  clara sobre recepción o despacho).

Correo del proveedor:
\"\"\"
{cuerpo}
\"\"\"

Responde SOLO JSON válido, sin markdown, con esta forma exacta:
{{"tipo": "acuse_recibo|despacho|otro", "detalle": "string o null — ej: numero de guia/seguimiento si lo menciona"}}"""


async def clasificar_respuesta_oc(cuerpo: str) -> dict:
    """Devuelve {"tipo": "acuse_recibo"|"despacho"|"otro", "detalle": str|None}.
    Ante cualquier falla, "otro" — un mensaje ambiguo queda para revisión
    humana en vez de mover el estado de la OC solo."""
    from app.config import settings

    vacio_seguro = {"tipo": "otro", "detalle": None}

    texto = (cuerpo or "").strip()
    if not texto or not settings.gemini_api_key:
        return vacio_seguro

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    try:
        resp = await asyncio.wait_for(
            model.generate_content_async(PROMPT_OC.format(cuerpo=texto[:4000])), timeout=20.0
        )
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
    except Exception as e:
        print(f"[EmailUnderstanding] error clasificando respuesta OC: {e}")
        return vacio_seguro

    tipo = data.get("tipo")
    if tipo not in ("acuse_recibo", "despacho", "otro"):
        tipo = "otro"
    return {"tipo": tipo, "detalle": data.get("detalle") or None}
