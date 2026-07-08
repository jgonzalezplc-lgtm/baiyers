"""
Fuentes: proveedores de madera y construcción en Chile (Sprint maderas).

Catálogo con scraping directo (plataforma detectada por sondeo real):
  - CLC SA:      WooCommerce Store API pública (/wp-json/wc/store/v1/products).
                 La tienda publica precio 0 → se entrega "a cotizar" con URL.
  - W Maderas:   Shopify — search/suggest.json (mismo patrón que La Sierra).
  - Ferramenta:  Odoo eCommerce — HTML de /shop?search= (microdata itemprop +
                 spans oe_currency_value para el precio).

Directorio RFQ (aserraderos/barracas SIN e-commerce, solo sitio brochure):
  Forestal Maihue, Sociedad Chile Maderas, SERCOMAD, Forestal W, GMT Timber.
  Entran como resultados "a cotizar" con su especialidad y contacto, para que
  el módulo RFQ les envíe solicitud de cotización por email.

Todas las funciones se auto-limitan con un gate de keywords: si la consulta no
es de madera/construcción en madera devuelven [] sin salir a la red, así estas
fuentes pueden estar activas en categorías amplias sin generar ruido.
"""
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# ─── Gate: ¿la consulta es de madera? ───────────────────────────────────────

_KEYWORDS_MADERA = {
    "madera", "pino", "tabla", "tablon", "tablón", "cuarton", "cuartón",
    "viga", "liston", "listón", "terciado", "osb", "mdf", "machimbrado",
    "roble", "coigue", "coigüe", "rauli", "raulí", "lenga", "eucalipto",
    "alerce", "laurel", "mañio", "cholguan", "cholguán", "plywood", "timber",
    "lumber", "moldura", "guardapolvo", "junquillo", "durmiente", "polin",
    "polín", "pallet", "impregnad", "cepillad", "aserrad", "dimensionad",
    "revestimiento", "piso flotante", "deck", "pergola", "pérgola",
}


def es_consulta_madera(query: str) -> bool:
    q = (query or "").lower()
    return any(kw in q for kw in _KEYWORDS_MADERA)


def _parse_precio_cl(s: str) -> float | None:
    if not s:
        return None
    cleaned = re.sub(r"[^\d]", "", str(s))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


# ─── CLC SA (WooCommerce Store API) ─────────────────────────────────────────

async def buscar_clcsa(query: str, max_results: int = 8) -> list[dict]:
    if not es_consulta_madera(query):
        return []
    try:
        url = "https://clcsa.cl/wp-json/wc/store/v1/products"
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            resp = await client.get(url, params={"search": query, "per_page": max_results})
            data = resp.json() if resp.status_code == 200 else []
            # WooCommerce busca con AND estricto: "madera pino" → 0. Reintentar
            # con la palabra más significativa (especie/tipo primero).
            if not data:
                palabras = [w for w in query.lower().split() if len(w) > 3 and w in _KEYWORDS_MADERA] \
                    or [w for w in query.split() if len(w) > 3]
                if palabras:
                    resp = await client.get(url, params={"search": palabras[0], "per_page": max_results})
                    data = resp.json() if resp.status_code == 200 else []

        out = []
        for p in data[:max_results]:
            precios = p.get("prices") or {}
            precio = _parse_precio_cl(precios.get("price"))
            # CLC publica 0 en la tienda: es precio a cotizar, no gratis
            if not precio:
                precio = None
            images = p.get("images") or []
            desc = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)

            out.append({
                "titulo": p.get("name", query),
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": p.get("permalink", ""),
                "fuente": "clcsa",
                "fuente_label": "CLC Maderas",
                "pais": "CL",
                "proveedor": "CLC SA",
                "numero_parte": p.get("sku"),
                "thumbnail": images[0].get("src") if images else None,
                "descripcion": desc[:300] or None,
                "stock_disponible": bool(p.get("is_in_stock")),
                "condicion": "nuevo",
                "tipo_proveedor": "distribuidor",
            })
        return out
    except Exception as e:
        print(f"[CLC SA] Error: {e}")
        return []


# ─── W Maderas (Shopify) ────────────────────────────────────────────────────

async def buscar_wmaderas(query: str, max_results: int = 8) -> list[dict]:
    if not es_consulta_madera(query):
        return []
    try:
        url = "https://wmaderas.cl/search/suggest.json"
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
            precio = _parse_precio_cl(str(p.get("price") or ""))
            body = BeautifulSoup(p.get("body") or "", "html.parser").get_text(" ", strip=True)
            out.append({
                "titulo": p.get("title", query),
                "precio": precio,
                "moneda": "CLP" if precio else None,
                "url": f"https://wmaderas.cl{p['url']}" if p.get("url", "").startswith("/") else p.get("url", ""),
                "fuente": "wmaderas",
                "fuente_label": "W Maderas",
                "pais": "CL",
                "proveedor": "W Maderas",
                "thumbnail": p.get("image"),
                "descripcion": body[:300] or None,
                "stock_disponible": bool(p.get("available")),
                "condicion": "nuevo",
                "tipo_proveedor": "distribuidor",
            })
        return out
    except Exception as e:
        print(f"[W Maderas] Error: {e}")
        return []


# ─── Ferramenta (Odoo eCommerce) ────────────────────────────────────────────

async def buscar_ferramenta(query: str, max_results: int = 8) -> list[dict]:
    if not es_consulta_madera(query):
        return []
    try:
        url = f"https://www.ferramenta.cl/shop?search={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=12.0, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        out = []
        # Cards Odoo: div con clase oe_product; nombre en <a itemprop="name">
        for card in soup.select("div.oe_product, form.oe_product_cart")[:max_results * 2]:
            link = card.select_one('a[itemprop="name"]') or card.select_one("h6 a, .o_wsale_products_item_title a")
            if not link:
                continue
            titulo = link.get("content") or link.get_text(strip=True)
            if not titulo or len(titulo) < 3:
                continue
            href = link.get("href", "")
            # El precio del listado Odoo es por paquete/embalaje B2B y no coincide
            # con el de la ficha del producto → se entrega "a cotizar" para no
            # contaminar el comparador con precios de unidad ambigua.
            img = card.select_one("img")

            out.append({
                "titulo": titulo,
                "precio": None,
                "moneda": None,
                "url": f"https://www.ferramenta.cl{href}" if href.startswith("/") else href,
                "fuente": "ferramenta",
                "fuente_label": "Ferramenta",
                "pais": "CL",
                "proveedor": "Ferramenta",
                "thumbnail": f"https://www.ferramenta.cl{img['src']}" if img and img.get("src", "").startswith("/") else (img.get("src") if img else None),
                "stock_disponible": True,
                "condicion": "nuevo",
                "tipo_proveedor": "distribuidor",
            })
            if len(out) >= max_results:
                break
        return out
    except Exception as e:
        print(f"[Ferramenta] Error: {e}")
        return []


# ─── Directorio RFQ: aserraderos/barracas sin e-commerce ────────────────────

PROVEEDORES_MADERA_DIR = [
    {
        "proveedor": "Forestal Maihue",
        "website": "https://forestalmaihue.cl/",
        "email": "ventas@forestalmaihue.cl",
        "region": "La Araucanía", "ciudad": "Villarrica",
        "maderas": ["coigüe", "coigue", "roble", "raulí", "rauli", "eucalipto", "nativa"],
        "especialidad": "Maderas nativas con secado controlado e impregnado industrial",
    },
    {
        "proveedor": "Sociedad Chile Maderas",
        "website": "https://sociedad-madereradechile.cl/",
        "email": "sociedadchilemaderas@gmail.com",
        "region": "Valparaíso", "ciudad": "Concón",
        "maderas": ["pino", "impregnad", "dimensionad"],
        "especialidad": "Impregnación y secado de madera dimensional de pino radiata",
    },
    {
        "proveedor": "SERCOMAD",
        "website": "https://sercomad.cl/",
        "email": "contacto@sercomad.cl",
        "region": "Metropolitana", "ciudad": "Santiago",
        "maderas": ["pino", "pallet", "dimensionad"],
        "especialidad": "Madera para construcción y pallets con tratamiento antiblu",
    },
    {
        "proveedor": "Forestal W",
        "website": "https://forestalwmaderas.cl/",
        "email": None,
        "region": "Metropolitana", "ciudad": "Santiago",
        "maderas": ["pino", "tablilla", "cepillad", "bruto"],
        "especialidad": "Pino bruto, tablillas y cepillado profesional para construcción",
    },
    {
        "proveedor": "GMT Timber",
        "website": "https://gmttimber.cl/",
        "email": None,
        "region": "Bío-Bío", "ciudad": "Coronel",
        "maderas": ["pino", "aserrad", "tablero", "moldura"],
        "especialidad": "Madera aserrada seca, tableros y molduras (nacional y exportación)",
    },
]


async def buscar_maderas_directorio(query: str, max_results: int = 5) -> list[dict]:
    """Aserraderos verificados sin catálogo online → resultados 'a cotizar' para RFQ.
    Prioriza los que declaran la especie/tipo consultado; siempre incluye 2-3 genéricos."""
    if not es_consulta_madera(query):
        return []
    q = (query or "").lower()

    def afinidad(p: dict) -> int:
        return sum(1 for m in p["maderas"] if m in q)

    ordenados = sorted(PROVEEDORES_MADERA_DIR, key=afinidad, reverse=True)
    out = []
    for p in ordenados[:max_results]:
        contacto = f" Contacto: {p['email']}." if p.get("email") else ""
        out.append({
            "titulo": f"{query} — cotizar con {p['proveedor']}",
            "precio": None,
            "moneda": None,
            "url": p["website"],
            "fuente": "maderas_dir",
            "fuente_label": p["proveedor"],
            "pais": "CL",
            "proveedor": p["proveedor"],
            "descripcion": f"{p['especialidad']}.{contacto}",
            "ubicacion_vendedor": f"{p['ciudad']}, {p['region']}",
            "stock_disponible": None,
            "condicion": "nuevo",
            "tipo_proveedor": "fabricante",
        })
    return out
