"""
Fuentes: retail/ferretería en Chile — scraping de APIs públicas (sin necesidad de API key).
Cada tienda expone su catálogo de forma distinta:
  - Sodimac:     Next.js SSR, datos embebidos en <script id="__NEXT_DATA__">
  - Easy:        VTEX — API REST pública de catálogo
  - La Sierra:   Shopify — endpoint público search/suggest.json
  - Construmart: Magento GraphQL — el índice de búsqueda no trae precio/stock
                 reales (siempre 0 / OUT_OF_STOCK), se entrega igual con
                 precio "a cotizar".
  - Dartel:      VTEX — misma API que Easy, cuenta "dartelcl"
  - Vitel:       Magento GraphQL en dominio vitelenergia.com (precio y stock sí
                 disponibles, a diferencia de Construmart)
  - Ferrelectrica: Bsale (plataforma chilena de e-commerce) — HTML server-rendered
  - Gobantes:    PrestaShop — HTML server-rendered
  - Rhona:       CMS propio — endpoint JSON interno (gl-ajax.php) usado por el
                 autocompletado de búsqueda
"""
import json
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
HEADERS = {"User-Agent": UA}


def _parse_precio_cl(s: str) -> float | None:
    """Convierte '159.990' (formato chileno, punto = miles) a 159990.0"""
    if not s:
        return None
    cleaned = re.sub(r"[^\d]", "", str(s))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


# ─── Sodimac ────────────────────────────────────────────────────────────────

async def buscar_sodimac(query: str, max_results: int = 8) -> list[dict]:
    try:
        url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text

        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
        if not m:
            return []
        data = json.loads(m.group(1))
        results = (data.get("props", {}).get("pageProps", {}) or {}).get("results") or []

        out = []
        for item in results[:max_results]:
            precios = item.get("prices") or []
            precio = None
            for p in precios:
                if p.get("type") == "eventPrice" and p.get("price"):
                    precio = _parse_precio_cl(p["price"][0])
                    break
            if precio is None:
                for p in precios:
                    if p.get("price"):
                        precio = _parse_precio_cl(p["price"][0])
                        break

            media = item.get("mediaUrls") or []
            out.append({
                "titulo": item.get("displayName", query),
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": item.get("url", ""),
                "fuente": "sodimac",
                "fuente_label": "Sodimac",
                "pais": "CL",
                "proveedor": "Sodimac",
                "marca": item.get("brand"),
                "thumbnail": media[0] if media else None,
                "stock_disponible": True,
                "rating": float(item.get("rating")) if item.get("rating") else None,
                "num_reviews": int(item.get("totalReviews")) if item.get("totalReviews") else None,
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Sodimac] Error: {e}")
        return []


# ─── Easy (VTEX) ────────────────────────────────────────────────────────────

async def buscar_easy(query: str, max_results: int = 8) -> list[dict]:
    try:
        url = "https://easycl.vtexcommercestable.com.br/api/catalog_system/pub/products/search"
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.get(url, params={"ft": query})
            if resp.status_code not in (200, 206):
                return []
            data = resp.json()

        out = []
        for p in data[:max_results]:
            items = p.get("items") or []
            if not items:
                continue
            sellers = items[0].get("sellers") or []
            if not sellers:
                continue
            co = sellers[0].get("commertialOffer") or {}
            precio = co.get("Price")
            stock = co.get("AvailableQuantity")
            images = items[0].get("images") or []

            link_text = p.get("linkText", "")
            out.append({
                "titulo": p.get("productName", query),
                "precio": float(precio) if precio else None,
                "moneda": "CLP" if precio else None,
                "url": f"https://www.easy.cl/{link_text}/p" if link_text else p.get("link", ""),
                "fuente": "easy",
                "fuente_label": "Easy",
                "pais": "CL",
                "proveedor": "Easy",
                "marca": p.get("brand"),
                "thumbnail": images[0].get("imageUrl") if images else None,
                "stock": stock,
                "stock_disponible": (stock or 0) > 0,
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Easy] Error: {e}")
        return []


# ─── Ferretería La Sierra (Shopify) ────────────────────────────────────────

async def buscar_lasierra(query: str, max_results: int = 8) -> list[dict]:
    try:
        url = "https://www.lasierra.cl/search/suggest.json"
        params = {
            "q": query,
            "resources[type]": "product",
            "resources[limit]": str(max_results),
        }
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()

        productos = ((data.get("resources") or {}).get("results") or {}).get("products") or []
        out = []
        for p in productos[:max_results]:
            precio = p.get("price")
            out.append({
                "titulo": p.get("title", query),
                "precio": float(precio) if precio else None,
                "moneda": "CLP" if precio else None,
                "url": f"https://www.lasierra.cl{p['url']}" if p.get("url", "").startswith("/") else p.get("url", ""),
                "fuente": "lasierra",
                "fuente_label": "La Sierra",
                "pais": "CL",
                "proveedor": "Ferretería La Sierra",
                "marca": p.get("vendor"),
                "thumbnail": p.get("image"),
                "stock_disponible": bool(p.get("available")),
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[La Sierra] Error: {e}")
        return []


# ─── Construmart (Magento GraphQL — precio no siempre disponible) ─────────

async def buscar_construmart(query: str, max_results: int = 8) -> list[dict]:
    try:
        gql = {
            "query": (
                "{products(search:\"%s\", pageSize:%d){items{"
                "name sku url_key "
                "price_range{minimum_price{final_price{value currency}}} "
                "stock_status "
                "image{url}"
                "}}}" % (query.replace('"', ""), max_results)
            )
        }
        async with httpx.AsyncClient(timeout=10.0, headers={**HEADERS, "Content-Type": "application/json"}) as client:
            resp = await client.post("https://www.construmart.cl/graphql", json=gql)
            if resp.status_code != 200:
                return []
            data = resp.json()

        items = ((data.get("data") or {}).get("products") or {}).get("items") or []
        out = []
        for p in items[:max_results]:
            precio_val = (((p.get("price_range") or {}).get("minimum_price") or {}).get("final_price") or {}).get("value")
            precio = float(precio_val) if precio_val else None
            out.append({
                "titulo": p.get("name", query),
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": f"https://www.construmart.cl/{p.get('url_key', '')}" if p.get("url_key") else "",
                "fuente": "construmart",
                "fuente_label": "Construmart",
                "pais": "CL",
                "proveedor": "Construmart",
                "thumbnail": (p.get("image") or {}).get("url"),
                "stock_disponible": p.get("stock_status") == "IN_STOCK",
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Construmart] Error: {e}")
        return []


async def _buscar_magento_graphql(
    query: str, graphql_url: str, base_url: str,
    fuente: str, fuente_label: str, proveedor: str,
    max_results: int = 8,
) -> list[dict]:
    """Helper genérico Magento GraphQL — usado por Vitel (y disponible para otras tiendas Magento)."""
    try:
        gql = {
            "query": (
                "{products(search:\"%s\", pageSize:%d){items{"
                "name sku url_key "
                "price_range{minimum_price{final_price{value currency}}} "
                "stock_status "
                "image{url}"
                "}}}" % (query.replace('"', ""), max_results)
            )
        }
        async with httpx.AsyncClient(timeout=10.0, headers={**HEADERS, "Content-Type": "application/json"}) as client:
            resp = await client.post(graphql_url, json=gql)
            if resp.status_code != 200:
                return []
            data = resp.json()

        items = ((data.get("data") or {}).get("products") or {}).get("items") or []
        out = []
        for p in items[:max_results]:
            precio_val = (((p.get("price_range") or {}).get("minimum_price") or {}).get("final_price") or {}).get("value")
            precio = float(precio_val) if precio_val else None
            url_key = p.get("url_key", "")
            out.append({
                "titulo": p.get("name", query),
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": f"{base_url}/{url_key}.html" if url_key else "",
                "fuente": fuente,
                "fuente_label": fuente_label,
                "pais": "CL",
                "proveedor": proveedor,
                "thumbnail": (p.get("image") or {}).get("url"),
                "stock_disponible": p.get("stock_status") == "IN_STOCK",
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[{fuente_label}] Error: {e}")
        return []


# ─── Vitel (Magento GraphQL — dominio vitelenergia.com) ───────────────────

async def buscar_vitel(query: str, max_results: int = 8) -> list[dict]:
    return await _buscar_magento_graphql(
        query,
        graphql_url="https://vitelenergia.com/graphql",
        base_url="https://vitelenergia.com",
        fuente="vitel",
        fuente_label="Vitel",
        proveedor="Vitel",
        max_results=max_results,
    )


# ─── Dartel (VTEX) ──────────────────────────────────────────────────────────

async def buscar_dartel(query: str, max_results: int = 8) -> list[dict]:
    try:
        url = "https://dartelcl.vtexcommercestable.com.br/api/catalog_system/pub/products/search"
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.get(url, params={"ft": query})
            if resp.status_code not in (200, 206):
                return []
            data = resp.json()

        out = []
        for p in data[:max_results]:
            items = p.get("items") or []
            if not items:
                continue
            sellers = items[0].get("sellers") or []
            if not sellers:
                continue
            co = sellers[0].get("commertialOffer") or {}
            precio = co.get("Price")
            stock = co.get("AvailableQuantity")
            images = items[0].get("images") or []

            link_text = p.get("linkText", "")
            out.append({
                "titulo": p.get("productName", query),
                "precio": float(precio) if precio else None,
                "moneda": "CLP" if precio else None,
                "url": f"https://www.dartel.cl/{link_text}/p" if link_text else p.get("link", ""),
                "fuente": "dartel",
                "fuente_label": "Dartel",
                "pais": "CL",
                "proveedor": "Dartel",
                "marca": p.get("brand"),
                "thumbnail": images[0].get("imageUrl") if images else None,
                "stock": stock,
                "stock_disponible": (stock or 0) > 0,
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Dartel] Error: {e}")
        return []


# ─── Ferrelectrica (Bsale) ──────────────────────────────────────────────────

async def buscar_ferrelectrica(query: str, max_results: int = 8) -> list[dict]:
    try:
        url = f"https://www.ferrelectrica.cl/search?search_text={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        out = []
        for card in soup.select("div.bs-collection__product")[:max_results]:
            link = card.select_one("a.bs-collection__product-info") or card.select_one("a")
            if not link:
                continue
            titulo_el = card.select_one(".bs-collection__product-title")
            marca_el = card.select_one(".bs-collection__product-brand")
            precio_el = card.select_one(".bs-collection__product-final-price")
            img_el = card.select_one("img")

            if titulo_el:
                titulo_el = titulo_el.__copy__()
                for notice in titulo_el.select(".bs-collection__product-notice"):
                    notice.decompose()
                titulo = titulo_el.get_text(strip=True)
            else:
                titulo = link.get("title") or query
            precio = _parse_precio_cl(precio_el.get_text()) if precio_el else None
            href = link.get("href", "")
            url_completa = href if href.startswith("http") else f"https://www.ferrelectrica.cl{href}"

            out.append({
                "titulo": titulo,
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": url_completa,
                "fuente": "ferrelectrica",
                "fuente_label": "Ferrelectrica",
                "pais": "CL",
                "proveedor": "Ferrelectrica",
                "marca": marca_el.get_text(strip=True) if marca_el else None,
                "thumbnail": img_el.get("src") if img_el else None,
                "stock_disponible": "agotado" not in card.get_text().lower(),
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Ferrelectrica] Error: {e}")
        return []


# ─── Gobantes (PrestaShop) ──────────────────────────────────────────────────

async def buscar_gobantes(query: str, max_results: int = 8) -> list[dict]:
    try:
        url = f"https://gobantes.cl/busqueda?s={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        out = []
        for card in soup.select("article.product-miniature")[:max_results]:
            link = card.select_one("a.product-thumbnail")
            titulo_el = card.select_one(".product-title a")
            precio_el = card.select_one("span.price")
            img_el = card.select_one("img")

            if not titulo_el:
                continue
            titulo = titulo_el.get_text(strip=True)
            precio_attr = precio_el.get("content") if precio_el else None
            precio = float(precio_attr) if precio_attr else (_parse_precio_cl(precio_el.get_text()) if precio_el else None)
            href = (link or titulo_el).get("href", "")

            out.append({
                "titulo": titulo,
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": href,
                "fuente": "gobantes",
                "fuente_label": "Gobantes",
                "pais": "CL",
                "proveedor": "Gobantes",
                "thumbnail": img_el.get("src") if img_el else None,
                "stock_disponible": "out_of_stock" not in (card.get("class") or []) and "out_of_stock" not in str(card.select_one(".product-flag")),
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Gobantes] Error: {e}")
        return []


# ─── Rhona (endpoint JSON interno del buscador) ────────────────────────────

async def buscar_rhona(query: str, max_results: int = 8) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.post(
                "https://rhona.cl/global/gl-ajax.php",
                data={"accion": "algo", "dato": query},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()

        if not isinstance(data, list):
            return []

        out = []
        for p in data[:max_results]:
            precio = p.get("precio_oferta") or p.get("precio")
            precio = float(precio) if precio else None
            stock = p.get("stock")
            try:
                stock = int(stock) if stock is not None else None
            except Exception:
                stock = None

            out.append({
                "titulo": p.get("nombre", query),
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": p.get("url", ""),
                "fuente": "rhona",
                "fuente_label": "Rhona",
                "pais": "CL",
                "proveedor": "Rhona",
                "marca": p.get("marca"),
                "numero_parte": p.get("sku"),
                "thumbnail": p.get("imagen"),
                "descripcion": p.get("descrip"),
                "stock": stock,
                "stock_disponible": (stock or 0) > 0 if stock is not None else None,
                "condicion": "nuevo",
            })
        return out
    except Exception as e:
        print(f"[Rhona] Error: {e}")
        return []
