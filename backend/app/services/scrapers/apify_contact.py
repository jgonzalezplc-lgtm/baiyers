"""Apify Contact Details Scraper — extrae emails de sitios web."""
import httpx
import re

APIFY_BASE = "https://api.apify.com/v2"
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


async def apify_extract_contact(url: str, api_token: str) -> str | None:
    """Crawlea una URL y extrae el primer email de contacto."""
    if not api_token or not url:
        return None
    try:
        actor_id = "apify~contact-info-scraper"
        async with httpx.AsyncClient(timeout=30.0) as client:
            run_resp = await client.post(
                f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items",
                params={"token": api_token, "timeout": 20},
                json={"startUrls": [{"url": url}], "maxDepth": 1, "maxPages": 3},
            )
            if run_resp.status_code != 201:
                return None
            items = run_resp.json()

        for item in items:
            emails = item.get("emails") or []
            for email in emails:
                if "@" in str(email):
                    return str(email).lower().strip()
            # fallback: buscar en texto raw
            text = str(item)
            found = EMAIL_RE.findall(text)
            for e in found:
                if not any(skip in e for skip in ["example", "test", "noreply", ".png", ".jpg"]):
                    return e.lower()
    except Exception as ex:
        print(f"[Apify] Error: {ex}")
    return None
