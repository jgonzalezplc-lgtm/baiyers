"""Hunter.io — búsqueda de emails por dominio (25 gratis/mes)."""
import httpx
import re


def _extraer_dominio(url: str) -> str | None:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else None


async def hunter_domain_search(dominio: str, api_key: str) -> str | None:
    """Busca el email más confiable para un dominio vía Hunter.io."""
    if not api_key or not dominio:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": dominio, "api_key": api_key, "limit": 5},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()

        emails = (data.get("data") or {}).get("emails") or []
        if emails:
            # Ordenar por score de confianza
            emails.sort(key=lambda e: e.get("confidence", 0), reverse=True)
            return emails[0].get("value", "").lower().strip() or None
    except Exception as ex:
        print(f"[Hunter.io] Error: {ex}")
    return None
