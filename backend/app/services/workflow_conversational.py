"""
Configuración conversacional del workflow de compras (Fase 2). Traduce una
descripción en lenguaje natural a un grafo de nodos/conexiones que el motor
de `workflow_engine.py` puede validar — nunca genera el grafo "a mano" con
el LLM: Gemini solo propone una lista simple de ETAPAS (más fácil de que
salga bien), y un compilador puro y determinístico arma el grafo real.

La conversación NO guarda nada — solo interpreta y devuelve una propuesta;
el usuario confirma y recién ahí se llama a POST /api/workflows (mismo flujo
que onboarding: investigar → revisar → confirmar).
"""
import json
from typing import Optional

TIPOS_ETAPA_VALIDOS = {
    "tarea_humana", "revision", "autorizacion", "homologacion",
    "emision_oc", "compra_sin_oc", "espera_documento", "accion_automatica",
}

ROLES_VALIDOS = {"cotizador", "revisor", "autorizador", "comprador"}

PROMPT_INTERPRETAR = """Eres un analista de procesos de compras B2B. Un usuario te describe, en
lenguaje informal, cómo funciona el proceso de compras de su empresa. Tu trabajo es traducirlo
a una lista ordenada de ETAPAS — no inventes un diagrama completo, solo identifica las etapas,
quién actúa en cada una, y las reglas de autorización por monto si las menciona.

Responde SOLO JSON válido, sin markdown, con esta forma exacta:
{
  "resumen": "1-3 frases en español explicando lo que entendiste, para mostrárselo al usuario",
  "etapas": [
    {
      "nombre": "nombre corto de la etapa (ej: 'Preparar comparación')",
      "tipo": "una de: tarea_humana, revision, autorizacion, homologacion, emision_oc, compra_sin_oc, espera_documento, accion_automatica",
      "roles": ["uno o más de: cotizador, revisor, autorizador, comprador"]
    }
  ],
  "reglas_autorizacion": [
    {"hasta": 500000, "desde": null, "descripcion": "quién autoriza en este tramo, en texto"},
    {"hasta": null, "desde": 500001, "descripcion": "quién autoriza en este tramo"}
  ],
  "requiere_aclaracion": false,
  "preguntas": ["máximo 3 preguntas cortas si falta información crítica (ej: quién autoriza, hasta qué monto)"]
}

Reglas:
- Si el usuario no menciona tramos de monto, "reglas_autorizacion" debe ser un arreglo vacío.
- Si falta información crítica para saber quién autoriza o en qué orden, pon
  requiere_aclaracion=true y haz máximo 3 preguntas concretas — no inventes responsables.
- Toda etapa de tipo autorizacion/revision/tarea_humana/homologacion necesita al menos 1 rol.
- No repitas al usuario lo que ya te dijo; solo pregunta lo que falta."""


def interpretar_descripcion(descripcion: str, contexto: str = "") -> dict:
    """Llama a Gemini para traducir texto libre a etapas. Nunca lanza: ante
    cualquier falla devuelve requiere_aclaracion=True pidiendo que lo intente
    de nuevo, sin inventar un workflow."""
    from app.config import settings

    vacio_seguro = {
        "resumen": "", "etapas": [], "reglas_autorizacion": [],
        "requiere_aclaracion": True,
        "preguntas": ["No pude interpretar la descripción, ¿puedes intentarlo de nuevo con más detalle?"],
    }

    texto = (descripcion or "").strip()
    if not texto or not settings.gemini_api_key:
        return vacio_seguro

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = PROMPT_INTERPRETAR + f"\n\nDescripción del usuario:\n{texto}"
    if contexto:
        prompt += f"\n\nConversación previa (preguntas ya hechas y respuestas del usuario):\n{contexto}"

    try:
        resp = model.generate_content(prompt, request_options={"timeout": 25})
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
    except Exception as e:
        print(f"[WorkflowConversational] error interpretando: {e}")
        return vacio_seguro

    etapas = [
        e for e in (data.get("etapas") or [])
        if e.get("tipo") in TIPOS_ETAPA_VALIDOS and e.get("nombre")
    ]
    for e in etapas:
        e["roles"] = [r for r in (e.get("roles") or []) if r in ROLES_VALIDOS] or ["cotizador"]

    return {
        "resumen": data.get("resumen") or "",
        "etapas": etapas,
        "reglas_autorizacion": data.get("reglas_autorizacion") or [],
        "requiere_aclaracion": bool(data.get("requiere_aclaracion")) and not etapas,
        "preguntas": (data.get("preguntas") or [])[:3],
    }


def _nodo_id(indice: int, sufijo: str = "") -> str:
    return f"n{indice}{sufijo}"


def compilar_a_grafo(etapas: list[dict], reglas_autorizacion: Optional[list[dict]] = None) -> tuple[list[dict], list[dict]]:
    """Compilador puro y determinístico: etapas simples (lista ordenada) →
    nodos/conexiones reales. Si hay ≥2 reglas por monto y la etapa es de tipo
    'autorizacion', se expande a un nodo de decisión por monto + un nodo de
    autorización por tramo. Los rechazos de autorización vuelven a la etapa
    anterior (devolución para corrección) — nunca a un tramo hermano.

    Diseño: se calcula primero el "nodo de entrada" de cada etapa (dónde
    apunta quien llega desde el paso anterior) ANTES de construir nada, para
    que cada conexión de avance apunte al destino real correcto — sin
    resolución diferida ni heurísticas de "el siguiente nodo creado"."""
    reglas = reglas_autorizacion or []

    if not etapas:
        return (
            [{"id": "inicio", "tipo": "inicio", "nombre": "Inicio"}, {"id": "fin", "tipo": "fin", "nombre": "Fin"}],
            [{"origen_nodo_id": "inicio", "destino_nodo_id": "fin"}],
        )

    def es_tramos(etapa: dict) -> bool:
        return etapa["tipo"] == "autorizacion" and len(reglas) > 1

    # Nodo de entrada de cada etapa (antes de construir nada).
    entrada = [_nodo_id(i, "_monto") if es_tramos(e) else _nodo_id(i) for i, e in enumerate(etapas)]
    # A dónde va el "avance" tras completar la etapa i (siguiente entrada, o fin).
    siguiente = entrada[1:] + ["fin"]
    # A dónde vuelve un rechazo en la etapa i (la entrada de la etapa anterior, o inicio).
    anterior_entrada = ["inicio"] + entrada[:-1]

    nodos: list[dict] = [{"id": "inicio", "tipo": "inicio", "nombre": "Inicio"}]
    conexiones: list[dict] = [{"origen_nodo_id": "inicio", "destino_nodo_id": entrada[0]}]

    for i, etapa in enumerate(etapas):
        destino_ok = siguiente[i]
        destino_rechazo = anterior_entrada[i]

        if not es_tramos(etapa):
            nid = entrada[i]
            nodo = {"id": nid, "tipo": etapa["tipo"], "nombre": etapa["nombre"], "roles": etapa["roles"]}
            if etapa["tipo"] == "autorizacion":
                nodo["resultados"] = ["aprobado", "rechazado"]
                conexiones.append({"origen_nodo_id": nid, "destino_nodo_id": destino_ok, "resultado": "aprobado"})
                conexiones.append({"origen_nodo_id": nid, "destino_nodo_id": destino_rechazo, "resultado": "rechazado"})
            else:
                conexiones.append({"origen_nodo_id": nid, "destino_nodo_id": destino_ok})
            nodos.append(nodo)
            continue

        # Autorización con tramos de monto.
        decision_id = entrada[i]
        tramos = [f"tramo_{j}" for j in range(len(reglas))]
        nodos.append({"id": decision_id, "tipo": "decision", "nombre": f"¿Monto? — {etapa['nombre']}", "resultados": tramos})

        for j, regla in enumerate(reglas):
            tramo_id = _nodo_id(i, f"_t{j}")
            condicion = {
                "campo": "monto_total",
                "operador": "<=" if regla.get("hasta") is not None else ">",
                "valor": regla.get("hasta") if regla.get("hasta") is not None else regla.get("desde"),
            }
            nodos.append({
                "id": tramo_id, "tipo": "autorizacion",
                "nombre": f"Autorización — {regla.get('descripcion') or f'tramo {j + 1}'}",
                "roles": etapa["roles"], "condicion_entrada": condicion,
                "resultados": ["aprobado", "rechazado"],
            })
            conexiones.append({"origen_nodo_id": decision_id, "destino_nodo_id": tramo_id, "resultado": tramos[j]})
            conexiones.append({"origen_nodo_id": tramo_id, "destino_nodo_id": destino_ok, "resultado": "aprobado"})
            conexiones.append({"origen_nodo_id": tramo_id, "destino_nodo_id": destino_rechazo, "resultado": "rechazado"})

    nodos.append({"id": "fin", "tipo": "fin", "nombre": "Fin"})
    return nodos, conexiones
