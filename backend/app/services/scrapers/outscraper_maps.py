"""Outscraper Google Maps — busca email/teléfono de empresas en Maps."""
import httpx


async def outscraper_google_maps(nombre_empresa: str, pais: str = "Chile", api_key: str = "") -> str | None:
    """Busca en Google Maps y retorna el email si lo encuentra."""
    if not api_key:
        return None
    try:
        query = f"{nombre_empresa} {pais}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://api.app.outscraper.com/maps/search-v3",
                params={"query": query, "limit": 1, "async": False, "fields": "name,emails,phone"},
                headers={"X-API-KEY": api_key},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()

        results = (data.get("data") or [[]])[0]
        if results:
            item = results[0] if isinstance(results, list) else results
            emails = item.get("emails") or []
            if emails:
                return emails[0].lower().strip()
    except Exception as ex:
        print(f"[Outscraper] Error: {ex}")
    return None
