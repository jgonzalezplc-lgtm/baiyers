"""Pipeline de cotización en proceso: identificar → guardar → buscar.

Existe para que los consumidores server-to-server (el servidor MCP y la API
pública) dejen de pegarle por HTTP a la propia API en `localhost:8000`. Ese
patrón tenía dos problemas:

1. **Seguridad.** `POST /api/identificar` y `POST /api/buscar` no podían exigir
   sesión, porque esas llamadas internas no llevan JWT de usuario. Eran las dos
   últimas rutas sin autenticar del backend (ver `services/tenant_guard.py`).
2. **Estaba roto.** Ambos llamadores mandaban `{"item_id", "cantidad",
   "user_id"}` a `/api/buscar`, cuerpo que no corresponde a `BuscarRequest`
   (exige `cotizacion_id` y los términos) → 422. Y leían `id`/`item_id` de la
   respuesta de `/api/identificar`, que nunca devolvió ninguno de los dos: la
   identificación no crea la fila en `cotizaciones`, eso lo hace el cliente.
   Resultado: el tool `cotizar_item` y `POST /api/v1/cotizar` fallaban siempre.

Acá el flujo completo queda explícito y en proceso, reusando las mismas piezas
que ya usa `web_quote_service._run()` — que es el camino que sí funciona.
"""
import asyncio
from typing import Any, Optional


async def cotizar_descripcion(
    *,
    user_id: str,
    descripcion: str,
    cantidad: int = 1,
    marca: Optional[str] = None,
    numero_parte: Optional[str] = None,
    industria_empresa: Optional[str] = None,
    guardar: bool = True,
) -> dict[str, Any]:
    """Identifica un ítem descrito en lenguaje natural y le busca precios.

    Devuelve `{"cotizacion_id", "nombre", "categoria", "resultados"}`.
    `resultados` viene ordenado con los que tienen precio primero, igual que
    `/api/buscar`. `cotizacion_id` es None si `guardar=False`.

    Lanza `ValueError` si la identificación no logra un nombre utilizable —
    el llamador decide cómo reportarlo (error de API, texto para el LLM, etc.).
    """
    from app.config import settings
    from app.routers.buscar import (
        BuscarRequest, _buscar_fuentes, _filtrar_gemini, _guardar_supabase,
    )
    from app.routers.identificar import IdentificarRequest, identificar_item

    texto = descripcion.strip()
    if marca:
        texto = f"{marca} {texto}"
    if numero_parte:
        texto = f"{texto} (P/N: {numero_parte})"

    # `ctx=None` a propósito: acá no hay request HTTP. El actor ya viene
    # verificado por quien llama (API key de la API pública o token MCP) y se
    # pasa explícito en `user_id`.
    identificado = await identificar_item(
        IdentificarRequest(
            descripcion=texto,
            industria_empresa=industria_empresa,
            user_id=user_id,
        ),
        ctx=None,
    )

    # La identificación puede devolver varios ítems; acá se cotiza uno solo, así
    # que se toma el primero y se cae a los campos de nivel superior (que es lo
    # que devuelve cuando el prompt describe un único ítem).
    items = identificado.get("lista_items") or []
    item = items[0] if items else identificado

    nombre = (item.get("nombre_tecnico") or identificado.get("nombre_tecnico") or "").strip()
    if not nombre:
        raise ValueError("No se pudo identificar el ítem a partir de la descripción")

    categoria = item.get("categoria") or identificado.get("categoria")
    terminos_es = item.get("terminos_busqueda_es") or identificado.get("terminos_busqueda_es") or []
    terminos_en = item.get("terminos_busqueda_en") or identificado.get("terminos_busqueda_en") or []

    cotizacion_id = None
    if guardar:
        cotizacion_id = await asyncio.to_thread(
            _crear_cotizacion, user_id, texto, nombre, item, identificado, categoria,
            terminos_es, terminos_en,
        )

    request = BuscarRequest(
        cotizacion_id=cotizacion_id or "demo",
        terminos_es=terminos_es,
        terminos_en=terminos_en,
        nombre_item=nombre,
        categoria=categoria,
        user_id=user_id,
    )
    filas = await _buscar_fuentes(request)
    if filas and settings.gemini_api_key:
        filas = await _filtrar_gemini(filas, nombre, settings.gemini_api_key)

    ordenadas = (
        [f for f in filas if f.get("precio") is not None]
        + [f for f in filas if f.get("precio") is None]
    )[:50]

    if cotizacion_id and ordenadas:
        await asyncio.to_thread(_guardar_supabase, cotizacion_id, ordenadas)

    return {
        "cotizacion_id": cotizacion_id,
        "nombre": nombre,
        "categoria": categoria,
        "cantidad": cantidad,
        "resultados": ordenadas,
    }


def _crear_cotizacion(
    user_id: str, descripcion: str, nombre: str, item: dict, identificado: dict,
    categoria: Optional[str], terminos_es: list, terminos_en: list,
) -> Optional[str]:
    """Misma fila que crea el frontend en `/cotizar` antes de buscar.

    Si falla, devuelve None: la búsqueda igual puede correr y devolver precios,
    sólo que sin persistirse. Cotizar es la operación que el usuario pidió;
    perder la traza es peor que nada, pero mucho menos que fallar entero.
    """
    from app.services.supabase import get_supabase
    try:
        fila = get_supabase().table("cotizaciones").insert({
            "user_id": user_id,
            "descripcion": descripcion,
            "nombre_identificado": nombre,
            "marca": item.get("marca") or identificado.get("marca"),
            "numero_parte": item.get("numero_parte") or identificado.get("numero_parte"),
            "categoria": categoria,
            "terminos_busqueda_es": terminos_es,
            "terminos_busqueda_en": terminos_en,
            "estado": "identificado",
            "confianza_ia": identificado.get("confianza"),
        }).execute()
        return fila.data[0]["id"] if fila.data else None
    except Exception as exc:
        print(f"[cotizacion_pipeline] no se pudo persistir la cotización: {exc}")
        return None
