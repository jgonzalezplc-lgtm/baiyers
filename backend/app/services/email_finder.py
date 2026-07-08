"""Cascada de búsqueda de email de proveedores."""
from __future__ import annotations
import re

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _extraer_dominio(url: str) -> str | None:
    m = re.search(r"https?://(?:www\.)?([^/?#]+)", url or "")
    return m.group(1) if m else None


async def encontrar_email_proveedor(
    proveedor_nombre: str,
    url: str = "",
    email_existente: str = "",
) -> dict:
    """
    Cascada de 5 pasos para encontrar el email del proveedor.
    Retorna { email, confianza: 'alta'|'media'|'baja', fuente }
    """
    from app.config import settings

    # ── PASO 1: email ya viene en los resultados ──────────────────────────────
    if email_existente and "@" in email_existente:
        return {"email": email_existente, "confianza": "alta", "fuente": "resultado"}

    dominio = _extraer_dominio(url)

    # ── PASO 2: Apify Contact Scraper ─────────────────────────────────────────
    if url and settings.apify_api_token:
        try:
            from app.services.scrapers.apify_contact import apify_extract_contact
            email = await apify_extract_contact(url, settings.apify_api_token)
            if email:
                return {"email": email, "confianza": "alta", "fuente": "apify"}
        except Exception as e:
            print(f"[EmailFinder] Apify failed: {e}")

    # ── PASO 3: Outscraper Google Maps ────────────────────────────────────────
    if settings.outscraper_api_key:
        try:
            from app.services.scrapers.outscraper_maps import outscraper_google_maps
            email = await outscraper_google_maps(proveedor_nombre, "Chile", settings.outscraper_api_key)
            if email:
                return {"email": email, "confianza": "media", "fuente": "outscraper"}
        except Exception as e:
            print(f"[EmailFinder] Outscraper failed: {e}")

    # ── PASO 4: Hunter.io por dominio ─────────────────────────────────────────
    if dominio and settings.hunter_api_key:
        try:
            from app.services.scrapers.hunter_io import hunter_domain_search
            email = await hunter_domain_search(dominio, settings.hunter_api_key)
            if email:
                return {"email": email, "confianza": "media", "fuente": "hunter"}
        except Exception as e:
            print(f"[EmailFinder] Hunter failed: {e}")

    # ── PASO 5: Gemini adivina el email ───────────────────────────────────────
    if settings.gemini_api_key and dominio:
        try:
            import asyncio
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            prompt = (
                f"Para la empresa '{proveedor_nombre}' con dominio '{dominio}', "
                f"genera el email de contacto más probable (ventas o contacto). "
                f"Responde SOLO el email, sin explicación. Ej: ventas@empresa.com"
            )
            resp = await asyncio.wait_for(model.generate_content_async(prompt), timeout=10.0)
            email_guess = resp.text.strip().lower()
            if EMAIL_RE.match(email_guess):
                return {"email": email_guess, "confianza": "baja", "fuente": "gemini", "requiere_confirmacion": True}
        except Exception as e:
            print(f"[EmailFinder] Gemini guess failed: {e}")

    return {"email": None, "confianza": None, "fuente": None}
