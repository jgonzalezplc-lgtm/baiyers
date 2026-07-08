import asyncio
import base64
import json
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["identificar"])

PROMPT = """Eres un experto en repuestos y materiales industriales, mecanicos, electricos y de servicios,
en procurement B2B y en planificacion de proyectos de construccion y mantenimiento. El usuario puede enviarte:
- Una foto o descripcion de UN item ("rodamiento 6205")
- Un prompt conversacional ("necesito 3 cotizaciones de motores trifasicos de 5 HP para bombas de agua")
- Una LISTA de items en una sola entrada ("tornillos M6x20 galvanizados, tuercas M6, arandelas M6")
- Un PROYECTO u OBJETIVO sin items explicitos ("quiero construir una cabaña", "voy a instalar riego
  automatico", "necesito armar un taller de soldadura"). En este caso TU eres el experto: descompone
  el proyecto en su lista de materiales/equipos concretos y cotizables (los 6 a 12 mas esenciales),
  con cantidades razonables para un proyecto tipico de ese tamaño. Ejemplo: "construir una cabaña" →
  madera de pino dimensionada, ventanas de aluminio, planchas OSB, cemento, techo zinc alum,
  clavos/tornillos, aislante, puerta exterior.

Interpreta la intencion, extrae CADA item por separado, y responde SOLO en JSON valido, sin markdown, sin texto adicional:
{
  "nombre_tecnico": "nombre tecnico del item principal (el primero si hay varios)",
  "marca": "marca si es visible o mencionada, sino null",
  "numero_parte": "numero de parte si es visible o mencionado, sino null",
  "categoria": "electronica|construccion|insumos_medicos|industrial|tuberias_valvulas|mecanico|electrico|hidraulico|neumatico|servicio|consumible|otro",
  "terminos_busqueda_es": ["termino1", "termino2", "termino3", "termino4", "termino5"],
  "terminos_busqueda_en": ["term1", "term2", "term3", "term4", "term5"],
  "confianza": "alto|medio|bajo",
  "n_cotizaciones_solicitadas": 3,
  "es_proyecto": false,
  "nombre_lista_sugerido": "nombre corto para la lista de cotizacion, o null si es un solo item",
  "lista_items": [
    {
      "nombre_tecnico": "nombre tecnico del item",
      "marca": "marca o null",
      "numero_parte": "numero de parte o null",
      "categoria": "una de las categorias de arriba",
      "cantidad": 1,
      "unidad": "und|kg|m|lt|caja|otro",
      "terminos_busqueda_es": ["termino1", "termino2", "termino3"],
      "terminos_busqueda_en": ["term1", "term2", "term3"]
    }
  ]
}

Reglas:
- lista_items SIEMPRE presente, con al menos 1 elemento. Si el usuario pidio varios items, un elemento por item.
- Si el usuario indica cantidad ("50 tornillos"), reflejala en "cantidad".
- n_cotizaciones_solicitadas: cuantas cotizaciones/proveedores pidio el usuario (default 3 si no lo dice).
- es_proyecto: true SOLO cuando el usuario describio un objetivo y tu generaste la lista de materiales.
- nombre_lista_sugerido: para proyectos, el proyecto ("Construcción cabaña"); para listas explicitas un
  resumen corto ("Herramientas taller"); null si es 1 solo item.
- En proyectos: items CONCRETOS y buscables en retail/distribuidores (nada de "materiales varios"),
  cada uno con su categoria correcta y terminos de busqueda de comprador experto.
- Los campos de nivel superior (nombre_tecnico, terminos_busqueda_es, etc.) corresponden al PRIMER item, para retrocompatibilidad."""


class IdentificarRequest(BaseModel):
    descripcion: Optional[str] = None
    imagen_base64: Optional[str] = None
    imagen_mime: Optional[str] = "image/jpeg"
    imagen_url: Optional[str] = None


def _limpiar_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        partes = text.split("```")
        for p in partes:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                return p
    return text


@router.post("/identificar")
async def identificar_item(req: IdentificarRequest):
    from app.config import settings
    import google.generativeai as genai

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no configurada en .env")

    if not req.descripcion and not req.imagen_base64 and not req.imagen_url:
        raise HTTPException(status_code=400, detail="Se requiere descripcion o imagen")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    parts = []

    if req.imagen_base64:
        image_bytes = base64.b64decode(req.imagen_base64)
        parts.append({"mime_type": req.imagen_mime or "image/jpeg", "data": image_bytes})
    elif req.imagen_url:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(req.imagen_url)
        parts.append({"mime_type": "image/jpeg", "data": resp.content})

    prompt = PROMPT
    if req.descripcion:
        prompt += f"\n\nDescripcion adicional del usuario: {req.descripcion}"
    parts.append(prompt)

    try:
        response = await asyncio.wait_for(
            model.generate_content_async(parts),
            timeout=30.0,
        )
        text = _limpiar_json(response.text)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Gemini tardó demasiado. Intenta de nuevo.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error con Gemini: {str(e)}")

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Gemini no retorno JSON valido")

    # Normalizar: lista_items siempre presente (retrocompatibilidad con clientes viejos
    # y garantía para clientes nuevos aunque el modelo la omita)
    if not result.get("lista_items"):
        result["lista_items"] = [{
            "nombre_tecnico": result.get("nombre_tecnico"),
            "marca": result.get("marca"),
            "numero_parte": result.get("numero_parte"),
            "categoria": result.get("categoria"),
            "cantidad": 1,
            "unidad": "und",
            "terminos_busqueda_es": result.get("terminos_busqueda_es", []),
            "terminos_busqueda_en": result.get("terminos_busqueda_en", []),
        }]
    if not result.get("n_cotizaciones_solicitadas"):
        result["n_cotizaciones_solicitadas"] = 3

    return result


# ─── Refinar búsqueda con contexto del usuario ────────────────────────────────

PROMPT_REFINAR = """Eres un experto en procurement B2B. Un usuario buscó un producto y los
resultados fueron malos (accesorios, derivados u otros productos). Te da contexto adicional
de lo que REALMENTE necesita. Tu trabajo: generar términos de búsqueda depurados que
encuentren EL PRODUCTO MISMO, no sus accesorios ni derivados.

Ejemplo: buscó "madera de pino" y salieron esmaltes y protectores "de madera de pino".
Con el contexto "quiero un trozo de madera para construir" los términos correctos serían
"tabla pino cepillado", "madera pino dimensionada", "pino bruto construcción", etc.

Responde SOLO en JSON válido, sin markdown:
{
  "nombre_tecnico": "nombre técnico preciso del producto que busca",
  "categoria": "electronica|construccion|insumos_medicos|industrial|tuberias_valvulas|mecanico|electrico|hidraulico|neumatico|servicio|consumible|otro",
  "terminos_busqueda_es": ["término específico 1", "2", "3", "4", "5"],
  "terminos_busqueda_en": ["specific term 1", "2", "3", "4", "5"],
  "palabras_requeridas": ["palabras que DEBEN aparecer en el título de un resultado válido (stems simples, minúsculas)"],
  "palabras_excluidas": ["palabras que delatan un resultado inválido: accesorios, derivados, otros productos (minúsculas)"]
}

Reglas:
- Los términos deben ser como los escribiría un comprador experto en el retail/distribuidor correcto.
- palabras_excluidas: piensa qué productos basura salieron o saldrían (ej: esmalte, barniz, protector, cerco, kit, funda, repuesto de otra cosa) y lístalos.
- palabras_requeridas: 1 a 3 palabras núcleo del producto (sin artículos)."""


class RefinarRequest(BaseModel):
    nombre_item: str
    contexto: str
    categoria_actual: Optional[str] = None
    terminos_actuales: Optional[list[str]] = None


@router.post("/refinar-busqueda")
async def refinar_busqueda(req: RefinarRequest):
    from app.config import settings
    import google.generativeai as genai

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no configurada en .env")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = (
        PROMPT_REFINAR
        + f"\n\nBúsqueda original: {req.nombre_item}"
        + (f"\nTérminos que dieron malos resultados: {', '.join(req.terminos_actuales)}" if req.terminos_actuales else "")
        + (f"\nCategoría actual: {req.categoria_actual}" if req.categoria_actual else "")
        + f"\nContexto del usuario sobre lo que realmente necesita: {req.contexto}"
    )

    try:
        response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=30.0)
        result = json.loads(_limpiar_json(response.text))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Gemini tardó demasiado. Intenta de nuevo.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Gemini no retornó JSON válido")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error con Gemini: {str(e)}")

    result.setdefault("terminos_busqueda_es", [req.nombre_item])
    result.setdefault("terminos_busqueda_en", [])
    result.setdefault("palabras_requeridas", [])
    result.setdefault("palabras_excluidas", [])
    result.setdefault("nombre_tecnico", req.nombre_item)
    return result
