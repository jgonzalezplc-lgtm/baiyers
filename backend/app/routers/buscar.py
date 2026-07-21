import asyncio
import json
import re
from typing import Optional, AsyncGenerator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["buscar"])


class BuscarRequest(BaseModel):
    cotizacion_id: str
    terminos_es: list[str]
    terminos_en: list[str]
    nombre_item: str
    # v2 — búsqueda orientada por categoría (opcionales, retrocompatible)
    categoria: Optional[str] = None
    # v2.1 — el usuario puede marcar varias categorías; se consultan las fuentes de todas
    categorias: Optional[list[str]] = None
    user_id: Optional[str] = None
    incluir_proveedores_custom: bool = True


def _fuentes_de_request(req: "BuscarRequest") -> set[str]:
    from app.services.categoria_mapper import fuentes_para_categoria
    cats = [c for c in (req.categorias or []) if c] or ([req.categoria] if req.categoria else [])
    if not cats:
        return fuentes_para_categoria(None)
    fuentes: set[str] = set()
    for c in cats:
        fuentes |= fuentes_para_categoria(c)
    return fuentes


def _parse_precio(price_str: Optional[str]) -> tuple[Optional[float], str]:
    """Detecta moneda y parsea el precio correctamente."""
    if not price_str:
        return None, "USD"

    s = str(price_str).strip()

    # Detectar moneda
    if "CLP" in s or "clp" in s.lower():
        moneda = "CLP"
    elif "€" in s or "EUR" in s:
        moneda = "EUR"
    elif "¥" in s or "CNY" in s or "RMB" in s:
        moneda = "CNY"
    elif "£" in s or "GBP" in s:
        moneda = "GBP"
    else:
        moneda = "USD"

    cleaned = re.sub(r"[^\d.,]", "", s)
    if not cleaned:
        return None, moneda

    dot_count = cleaned.count(".")
    comma_count = cleaned.count(",")

    if dot_count > 1:
        # 1.234.567 → separador de miles chileno/europeo
        cleaned = cleaned.replace(".", "")
        if "," in cleaned:
            cleaned = cleaned.replace(",", ".")
    elif comma_count > 1:
        # 1,234,567 → separador de miles anglosajón
        cleaned = cleaned.replace(",", "")
    elif dot_count == 1 and comma_count == 1:
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")        # 1,234.56
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")  # 1.234,56
    elif dot_count == 1 and comma_count == 0:
        # "12.990" → 3 dígitos post-punto = separador de miles (CLP/EUR)
        # "12.99"  → 1-2 dígitos post-punto = decimal
        parts = cleaned.split(".")
        if len(parts[1]) == 3:
            cleaned = cleaned.replace(".", "")        # 12.990 → 12990
        # else: decimal normal, dejar como está
    elif comma_count == 1 and dot_count == 0:
        parts = cleaned.split(",")
        if len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")       # 45,99 → decimal
        else:
            cleaned = cleaned.replace(",", "")        # 45,990 → miles

    try:
        val = float(cleaned)
        return val if val > 0 else None, moneda
    except Exception:
        return None, moneda


async def _serp_query(
    query: str, serp_key: str, client: httpx.AsyncClient,
    gl: str = "cl", pais_default: str = "CL"
) -> list[dict]:
    try:
        resp = await client.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_shopping", "q": query, "gl": gl, "hl": "es", "api_key": serp_key},
            timeout=10.0,
        )
        data = resp.json()
        results = []
        for item in data.get("shopping_results", [])[:8]:
            precio, moneda = _parse_precio(item.get("price"))
            if pais_default == "CL" and moneda == "USD":
                moneda = "CLP"
            elif pais_default != "CL" and moneda == "CLP":
                moneda = "USD"

            # Extraer toda la info disponible de Google Shopping
            extensions = item.get("extensions") or []
            envio_gratis = any("gratis" in str(e).lower() or "free" in str(e).lower() or "sin cargo" in str(e).lower() for e in extensions)
            delivery_info = next((e for e in extensions if "día" in str(e).lower() or "day" in str(e).lower() or "entrega" in str(e).lower() or "deliver" in str(e).lower()), None)

            # Rating
            rating = None
            num_reviews = None
            try:
                rating = float(item.get("rating") or 0) or None
                num_reviews = int(item.get("reviews") or 0) or None
            except Exception:
                pass

            results.append({
                "titulo": item.get("title", ""),
                "precio": precio,
                "moneda": moneda,
                "url": item.get("link") or item.get("product_link", ""),
                "fuente": "google",
                "pais": pais_default,
                "proveedor": item.get("source", ""),
                "thumbnail": item.get("thumbnail"),
                # Enriquecidos
                "descripcion": item.get("snippet") or None,
                "envio_gratis": envio_gratis if extensions else None,
                "plazo_entrega_estimado": delivery_info,
                "rating": rating,
                "num_reviews": num_reviews,
                "condicion": "usado" if item.get("second_hand_condition") else "nuevo",
                "extensions": extensions[:5],
            })
        return results
    except Exception as e:
        print(f"[SerpAPI gl={gl}] Error: {e}")
        return []


async def _serper_query(
    query: str, serper_key: str, client: httpx.AsyncClient,
    gl: str = "cl", pais_default: str = "CL"
) -> list[dict]:
    """Serper.dev — endpoint de Google Shopping (alternativa barata a SerpAPI)."""
    try:
        resp = await client.post(
            "https://google.serper.dev/shopping",
            headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            json={"q": query, "gl": gl, "hl": "es"},
            timeout=10.0,
        )
        data = resp.json()
        results = []
        for item in (data.get("shopping") or [])[:8]:
            precio, moneda = _parse_precio(item.get("price"))
            if pais_default == "CL" and moneda == "USD":
                moneda = "CLP"
            elif pais_default != "CL" and moneda == "CLP":
                moneda = "USD"
            rating = None
            try:
                rating = float(item.get("rating") or 0) or None
            except Exception:
                pass
            results.append({
                "titulo": item.get("title", ""),
                "precio": precio,
                "moneda": moneda,
                "url": item.get("link", ""),
                "fuente": "google",
                "pais": pais_default,
                "proveedor": item.get("source", ""),
                "thumbnail": item.get("imageUrl"),
                "descripcion": None,
                "plazo_entrega_estimado": item.get("delivery"),
                "rating": rating,
                "num_reviews": item.get("ratingCount"),
                "condicion": "nuevo",
            })
        return results
    except Exception as e:
        print(f"[Serper gl={gl}] Error: {e}")
        return []


async def _google_query(
    query: str, client: httpx.AsyncClient, gl: str = "cl", pais_default: str = "CL"
) -> list[dict]:
    """Búsqueda web/shopping en Google: usa Serper.dev si está configurado
    (más barato), sino SerpAPI. Si no hay ninguna key, devuelve []."""
    from app.config import settings
    if settings.serper_api_key:
        return await _serper_query(query, settings.serper_api_key, client, gl, pais_default)
    if settings.serp_api_key:
        return await _serp_query(query, settings.serp_api_key, client, gl, pais_default)
    return []


async def _ml_query(termino: str, client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            "https://api.mercadolibre.com/sites/MLC/search",
            params={"q": termino, "limit": 12},
            timeout=10.0,
        )
        data = resp.json()
        results = []
        for item in data.get("results", []):
            seller = item.get("seller", {})
            shipping = item.get("shipping", {})
            address = item.get("address", {})
            reputation = seller.get("seller_reputation", {})

            # Atributos técnicos → dict de specs
            specs: dict = {}
            for attr in (item.get("attributes") or []):
                name = attr.get("name")
                value = attr.get("value_name")
                if name and value:
                    specs[name] = value

            # Precios por volumen desde purchase_options si existen
            precio_volumen = None
            installments = item.get("installments")

            # Reputación del vendedor
            rep_level = reputation.get("level_id", "")  # ej: "5_green"
            rep_map = {"5_green": "Excelente", "4_light_green": "Muy bueno", "3_yellow": "Bueno", "2_orange": "Regular", "1_red": "Nuevo"}
            rep_label = rep_map.get(rep_level, rep_level.replace("_", " ") if rep_level else None)

            results.append({
                "titulo": item.get("title", ""),
                "precio": item.get("price"),
                "moneda": item.get("currency_id", "CLP"),
                "url": item.get("permalink", ""),
                "fuente": "mercadolibre",
                "pais": "CL",
                "proveedor": seller.get("nickname", "Vendedor ML"),
                "thumbnail": item.get("thumbnail"),
                # Enriquecidos
                "condicion": item.get("condition", "nuevo"),
                "stock": item.get("available_quantity"),
                "ventas_realizadas": item.get("sold_quantity"),
                "envio_gratis": shipping.get("free_shipping", False),
                "ubicacion_vendedor": f"{address.get('city_name', '')}, {address.get('state_name', '')}".strip(", ") or None,
                "garantia": item.get("warranty"),
                "reputacion_vendedor": rep_label,
                "especificaciones": specs if specs else None,
                "precio_volumen": precio_volumen,
            })
        return results
    except Exception as e:
        print(f"[MercadoLibre] Error: {e}")
        return []


def _deduplicar(resultados: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for r in resultados:
        url = r.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        out.append(r)
    return out


async def _filtrar_gemini(resultados: list[dict], nombre_item: str, gemini_key: str) -> list[dict]:
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        lista = [{"titulo": r["titulo"], "url": r["url"]} for r in resultados[:20]]
        prompt = (
            f"De estos resultados de busqueda para '{nombre_item}', "
            f"indica cuales son proveedores relevantes. "
            f"Responde SOLO en JSON valido, sin markdown:\n"
            f'[{{"titulo":"...","url":"...","relevante":true,"tipo":"distribuidor|fabricante|retail|desconocido"}}]\n\n'
            f"Resultados:\n{json.dumps(lista, ensure_ascii=False)}"
        )

        response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=20.0)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()

        filtrados = json.loads(text)
        url_map = {f["url"]: f for f in filtrados}

        TIPOS_VALIDOS = {"distribuidor", "fabricante", "retail", "desconocido"}
        for r in resultados:
            meta = url_map.get(r.get("url", ""), {})
            # Combinar con la heurística: si _marcar_relevancia ya lo marcó basura,
            # Gemini no lo resucita (ambos deben coincidir en "relevante").
            r["relevante"] = r.get("relevante", True) and meta.get("relevante", True)
            tipo = meta.get("tipo", "desconocido")
            r["tipo_proveedor"] = tipo if tipo in TIPOS_VALIDOS else "desconocido"

        return resultados
    except Exception as e:
        print(f"[Gemini filter] Error: {e}")
        for r in resultados:
            r.setdefault("relevante", True)
            r.setdefault("tipo_proveedor", "desconocido")
        return resultados


def _guardar_supabase(cotizacion_id: str, resultados: list[dict]) -> None:
    try:
        from app.services.supabase import get_supabase
        sb = get_supabase()

        # Borrar resultados anteriores en estado "encontrado" para evitar duplicados
        # al re-buscar. Preservar los que ya tienen email enviado (contactado, respondio).
        sb.table("resultados").delete().eq("cotizacion_id", cotizacion_id).eq("estado", "encontrado").execute()

        TIPOS_VALIDOS = {"distribuidor", "fabricante", "retail", "desconocido"}
        FUENTES_VALIDAS = {
            "google", "mercadolibre", "alibaba", "manual", "mouser", "digikey", "tme",
            "sodimac", "easy", "lasierra", "construmart",
            "vitel", "dartel", "ferrelectrica", "gobantes", "rhona",
            "clcsa", "wmaderas", "ferramenta", "maderas_dir",
        }
        METADATA_KEYS = {
            "titulo", "marca", "numero_parte", "descripcion", "condicion", "categoria",
            "lifecycle", "stock", "stock_disponible", "cantidad_minima", "precio_original",
            "moneda_original", "precio_volumen", "envio_gratis", "plazo_entrega_estimado",
            "ubicacion_vendedor", "rating", "num_reviews", "reputacion_vendedor",
            "ventas_realizadas", "rohs", "datasheet_url", "garantia", "especificaciones",
            "fuente_label", "extensions", "thumbnail",
        }
        # Fuentes que acepta el CHECK constraint original de la tabla. La
        # migración 015 amplía la lista; mientras no esté aplicada, las fuentes
        # nuevas se degradan a 'manual' (la real queda en metadata.fuente_label).
        FUENTES_DB_LEGACY = {"google", "mercadolibre", "alibaba", "manual"}

        rows = []
        for r in resultados:
            fuente = r["fuente"] if r.get("fuente") in FUENTES_VALIDAS else "manual"
            metadata = {k: v for k, v in r.items() if k in METADATA_KEYS and v is not None}
            metadata["fuente_label"] = r.get("fuente_label") or fuente
            row = {
                "cotizacion_id": cotizacion_id,
                "proveedor_nombre": (r.get("proveedor") or r.get("titulo", ""))[:100],
                "precio": r.get("precio"),
                "moneda": r.get("moneda", "CLP"),
                "url": r.get("url", ""),
                "pais": r.get("pais", "CL"),
                "fuente": fuente,
                "tipo_proveedor": r.get("tipo_proveedor", "desconocido") if r.get("tipo_proveedor") in TIPOS_VALIDOS else "desconocido",
                "relevante": r.get("relevante", True),
                "estado": "encontrado",
            }
            try:
                row["metadata"] = json.dumps(metadata, ensure_ascii=False, default=str)
            except Exception:
                pass
            rows.append(row)

        # Insertar en lote con reparación automática: si la BD aún no tiene la
        # columna metadata o su constraint de fuente es el antiguo (migración
        # 015 pendiente), se ajustan las filas y se reintenta. Un solo insert
        # fallido NO debe botar los 50 resultados.
        intentos = 0
        while True:
            try:
                sb.table("resultados").insert(rows).execute()
                break
            except Exception as e:
                intentos += 1
                msg = str(e)
                if intentos > 3:
                    print(f"[Supabase] Error guardando resultados: {msg}")
                    break
                if "metadata" in msg:
                    print("[Supabase] Columna metadata no existe (migración 015) — reintentando sin ella")
                    for row in rows:
                        row.pop("metadata", None)
                elif "fuente_check" in msg:
                    print("[Supabase] Constraint de fuente antiguo (migración 015) — degradando fuentes nuevas a 'manual'")
                    for row in rows:
                        if row["fuente"] not in FUENTES_DB_LEGACY:
                            row["fuente"] = "manual"
                else:
                    print(f"[Supabase] Error guardando resultados: {msg}")
                    break
    except Exception as e:
        print(f"[Supabase] Error guardando resultados: {e}")


async def _buscar_fuentes(req: BuscarRequest) -> list[dict]:
    """Consulta todas las fuentes en paralelo y devuelve resultados deduplicados
    (sin filtro Gemini ni guardado). Núcleo compartido por /buscar y /buscar/prefetch."""
    from app.config import settings
    from app.services.fuentes.mouser import buscar_mouser
    from app.services.fuentes.digikey import buscar_digikey
    from app.services.fuentes.tme import buscar_tme
    from app.services.fuentes.retail_cl import (
        buscar_sodimac, buscar_easy, buscar_lasierra, buscar_construmart,
        buscar_vitel, buscar_dartel, buscar_ferrelectrica, buscar_gobantes, buscar_rhona,
    )
    from app.services.fuentes.maderas_cl import (
        buscar_clcsa, buscar_wmaderas, buscar_ferramenta, buscar_maderas_directorio,
    )
    from app.services.categoria_mapper import proveedores_custom_para

    termino_es = req.terminos_es[0] if req.terminos_es else req.nombre_item
    termino_en = req.terminos_en[0] if req.terminos_en else req.nombre_item
    fuentes = _fuentes_de_request(req)

    # Todo en paralelo: un solo gather para minimizar latencia total
    async with httpx.AsyncClient() as client:
        tareas = [_ml_query(termino_es, client)]
        if settings.serper_api_key or settings.serp_api_key:
            tareas += [
                _google_query(f"{termino_es} proveedor Chile", client, gl="cl", pais_default="CL"),
                _google_query(f"{termino_es} precio", client, gl="cl", pais_default="CL"),
                _google_query(f"{termino_en} supplier buy", client, gl="us", pais_default="US"),
                _google_query(f"{termino_en} wholesale manufacturer", client, gl="us", pais_default="US"),
            ]
        # Fuentes específicas filtradas por categoría
        especificas = {
            "mouser": buscar_mouser(termino_en, api_key=settings.mouser_api_key),
            "digikey": buscar_digikey(termino_en, client_id=settings.digikey_client_id, client_secret=settings.digikey_client_secret),
            "tme": buscar_tme(termino_en, api_key=settings.tme_api_key, api_secret=settings.tme_api_secret),
            "sodimac": buscar_sodimac(termino_es),
            "easy": buscar_easy(termino_es),
            "lasierra": buscar_lasierra(termino_es),
            "construmart": buscar_construmart(termino_es),
            "vitel": buscar_vitel(termino_es),
            "dartel": buscar_dartel(termino_es),
            "ferrelectrica": buscar_ferrelectrica(termino_es),
            "gobantes": buscar_gobantes(termino_es),
            "rhona": buscar_rhona(termino_es),
            "clcsa": buscar_clcsa(termino_es),
            "wmaderas": buscar_wmaderas(termino_es),
            "ferramenta": buscar_ferramenta(termino_es),
            "maderas_dir": buscar_maderas_directorio(termino_es),
        }
        for nombre, coro in especificas.items():
            if nombre in fuentes:
                tareas.append(coro)
            else:
                coro.close()  # liberar la corrutina no usada

        # Proveedores custom del usuario (BD supplier_categories)
        if req.incluir_proveedores_custom and req.user_id:
            cat_principal = (req.categorias[0] if req.categorias else None) or req.categoria
            tareas.append(proveedores_custom_para(req.user_id, cat_principal, req.nombre_item))

        all_results = await asyncio.gather(*tareas, return_exceptions=True)

    todos: list[dict] = []
    for lst in all_results:
        if isinstance(lst, list):
            todos.extend(lst)
    cat = (req.categorias[0] if req.categorias else None) or req.categoria
    _marcar_relevancia(todos, req.nombre_item, cat)
    return _deduplicar(todos)


def _marcar_relevancia(resultados: list[dict], nombre_item: str, categoria: str | None) -> None:
    """Marca relevante=False en los resultados basura (derivados/accesorios).
    No pisa un relevante=False ya existente. Rápido (heurístico, sin LLM)."""
    from app.services.relevancia import es_relevante
    for r in resultados:
        if r.get("relevante") is False:
            continue
        titulo = r.get("titulo") or r.get("proveedor") or ""
        r["relevante"] = es_relevante(titulo, nombre_item, categoria)


@router.post("/buscar")
async def buscar_proveedores(req: BuscarRequest):
    from app.config import settings

    todos = await _buscar_fuentes(req)
    if not todos:
        return []

    if settings.gemini_api_key:
        todos = await _filtrar_gemini(todos, req.nombre_item, settings.gemini_api_key)

    if req.cotizacion_id and req.cotizacion_id != "demo":
        _guardar_supabase(req.cotizacion_id, todos)

    con_precio = [r for r in todos if r.get("precio") is not None]
    sin_precio = [r for r in todos if r.get("precio") is None]

    return (con_precio + sin_precio)[:50]


# ─── Prefetch en background (listas multi-ítem) ───────────────────────────────
# Al crear una lista, las búsquedas de TODOS los ítems se lanzan de inmediato en
# paralelo. Cuando el usuario llega al ítem N, sus resultados ya están en la BD
# y la vista los carga al instante en vez de buscar de cero.

_prefetch_tasks: set = set()
_prefetch_sem = asyncio.Semaphore(3)  # máx 3 ítems buscando a la vez (≈45 requests)


class PrefetchRequest(BaseModel):
    cotizacion_ids: list[str]
    user_id: Optional[str] = None


@router.post("/buscar/prefetch")
async def prefetch_busquedas(req: PrefetchRequest):
    """Encola búsquedas en background para varias cotizaciones. Responde al tiro;
    los resultados quedan guardados en la tabla `resultados` al terminar cada una."""
    from app.services.supabase import get_supabase

    async def buscar_uno(cid: str):
        async with _prefetch_sem:
            try:
                sb = get_supabase()
                cot = await asyncio.to_thread(
                    lambda: sb.table("cotizaciones").select(
                        "nombre_identificado, descripcion, terminos_busqueda_es, terminos_busqueda_en, categoria"
                    ).eq("id", cid).single().execute()
                )
                d = cot.data or {}
                breq = BuscarRequest(
                    cotizacion_id=cid,
                    terminos_es=d.get("terminos_busqueda_es") or [],
                    terminos_en=d.get("terminos_busqueda_en") or [],
                    nombre_item=d.get("nombre_identificado") or d.get("descripcion") or "",
                    categoria=d.get("categoria"),
                    user_id=req.user_id,
                )
                todos = await _buscar_fuentes(breq)
                if todos:
                    con_precio = [r for r in todos if r.get("precio") is not None]
                    sin_precio = [r for r in todos if r.get("precio") is None]
                    await asyncio.to_thread(_guardar_supabase, cid, (con_precio + sin_precio)[:50])
                print(f"[prefetch] {cid}: {len(todos)} resultados guardados")
            except Exception as e:
                print(f"[prefetch] {cid}: error {e}")

    for cid in req.cotizacion_ids:
        t = asyncio.create_task(buscar_uno(cid))
        _prefetch_tasks.add(t)
        t.add_done_callback(_prefetch_tasks.discard)

    return {"success": True, "encoladas": len(req.cotizacion_ids)}


# ─── Streaming SSE ─────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/buscar/stream")
async def buscar_stream(req: BuscarRequest):
    """
    Misma búsqueda pero con Server-Sent Events: cada fuente envía sus resultados
    en cuanto termina, sin esperar a las demás. Max 50 resultados totales.
    """
    from app.config import settings
    from app.services.fuentes.mouser import buscar_mouser
    from app.services.fuentes.digikey import buscar_digikey
    from app.services.fuentes.tme import buscar_tme
    from app.services.fuentes.retail_cl import (
        buscar_sodimac, buscar_easy, buscar_lasierra, buscar_construmart,
        buscar_vitel, buscar_dartel, buscar_ferrelectrica, buscar_gobantes, buscar_rhona,
    )
    from app.services.fuentes.maderas_cl import (
        buscar_clcsa, buscar_wmaderas, buscar_ferramenta, buscar_maderas_directorio,
    )

    from app.services.categoria_mapper import proveedores_custom_para

    termino_es = req.terminos_es[0] if req.terminos_es else req.nombre_item
    termino_en = req.terminos_en[0] if req.terminos_en else req.nombre_item
    fuentes = _fuentes_de_request(req)

    async def generate() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue()
        all_results: list[dict] = []
        seen_urls: set[str] = set()

        cat_rel = (req.categorias[0] if req.categorias else None) or req.categoria

        async def run_source(name: str, coro):
            try:
                results = await coro
                if isinstance(results, list):
                    # Matching: descartar basura (barniz para "madera", etc.) al vuelo
                    _marcar_relevancia(results, req.nombre_item, cat_rel)
                    await queue.put((name, results))
                else:
                    await queue.put((name, []))
            except Exception as e:
                print(f"[stream/{name}] Error: {e}")
                await queue.put((name, []))

        async with httpx.AsyncClient() as client:
            sources: list[tuple[str, object]] = [
                ("MercadoLibre", _ml_query(termino_es, client)),
            ]
            if settings.serper_api_key or settings.serp_api_key:
                sources += [
                    ("Google Chile", _google_query(f"{termino_es} proveedor Chile", client, gl="cl", pais_default="CL")),
                    ("Google Chile 2", _google_query(f"{termino_es} precio", client, gl="cl", pais_default="CL")),
                    ("Google EEUU", _google_query(f"{termino_en} supplier buy", client, gl="us", pais_default="US")),
                    ("Google Global", _google_query(f"{termino_en} wholesale manufacturer", client, gl="us", pais_default="US")),
                ]
            # Fuentes específicas filtradas por categoría (v2)
            especificas: list[tuple[str, str, object]] = [
                ("mouser", "Mouser", buscar_mouser(termino_en, api_key=settings.mouser_api_key)),
                ("digikey", "DigiKey", buscar_digikey(termino_en, client_id=settings.digikey_client_id, client_secret=settings.digikey_client_secret)),
                ("tme", "TME", buscar_tme(termino_en, api_key=settings.tme_api_key, api_secret=settings.tme_api_secret)),
                ("sodimac", "Sodimac", buscar_sodimac(termino_es)),
                ("easy", "Easy", buscar_easy(termino_es)),
                ("lasierra", "La Sierra", buscar_lasierra(termino_es)),
                ("construmart", "Construmart", buscar_construmart(termino_es)),
                ("vitel", "Vitel", buscar_vitel(termino_es)),
                ("dartel", "Dartel", buscar_dartel(termino_es)),
                ("ferrelectrica", "Ferrelectrica", buscar_ferrelectrica(termino_es)),
                ("gobantes", "Gobantes", buscar_gobantes(termino_es)),
                ("rhona", "Rhona", buscar_rhona(termino_es)),
                ("clcsa", "CLC Maderas", buscar_clcsa(termino_es)),
                ("wmaderas", "W Maderas", buscar_wmaderas(termino_es)),
                ("ferramenta", "Ferramenta", buscar_ferramenta(termino_es)),
                ("maderas_dir", "Aserraderos CL", buscar_maderas_directorio(termino_es)),
            ]
            for clave, label, coro in especificas:
                if clave in fuentes:
                    sources.append((label, coro))
                else:
                    coro.close()  # liberar la corrutina no usada

            if req.incluir_proveedores_custom and req.user_id:
                cat_principal = (req.categorias[0] if req.categorias else None) or req.categoria
                sources.append(("Mis proveedores", proveedores_custom_para(req.user_id, cat_principal, req.nombre_item)))

            n_sources = len(sources)
            tasks = [asyncio.create_task(run_source(name, coro)) for name, coro in sources]

            received = 0
            while received < n_sources and len(all_results) < 50:
                try:
                    name, results = await asyncio.wait_for(queue.get(), timeout=12.0)
                except asyncio.TimeoutError:
                    break

                received += 1

                # Deduplicar por URL
                fresh = []
                for r in results:
                    url = r.get("url", "")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    fresh.append(r)

                # Respetar límite de 50 — emitir uno a uno para efecto cascada
                cap = 50 - len(all_results)
                fresh = fresh[:cap]
                for item in fresh:
                    all_results.append(item)
                    yield _sse({"source": name, "result": item, "done": False, "total_so_far": len(all_results)})
                    await asyncio.sleep(0)  # cede el event loop entre cada item

            # Cancelar tasks restantes si llegamos al límite
            for t in tasks:
                if not t.done():
                    t.cancel()

        # Guardar en DB (sin Gemini para no bloquear)
        if req.cotizacion_id and req.cotizacion_id != "demo" and all_results:
            try:
                _guardar_supabase(req.cotizacion_id, all_results)
            except Exception as e:
                print(f"[stream] DB error: {e}")

        yield _sse({"done": True, "total": len(all_results)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
