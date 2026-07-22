"""
Onboarding inteligente: desde el correo del usuario, investiga la empresa
(nombre, país, industria, rubro de compras probable, logo, sitio) para
acompañar la creación de la cuenta con contexto real.
"""
import asyncio
import json
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# TLD → país (para orientar la búsqueda por dominio)
_TLD_PAIS = {
    "cl": "Chile", "ar": "Argentina", "pe": "Perú", "co": "Colombia",
    "mx": "México", "br": "Brasil", "uy": "Uruguay", "ec": "Ecuador",
    "bo": "Bolivia", "py": "Paraguay", "es": "España", "us": "Estados Unidos",
}
# Dominios de correo genéricos (no son la empresa)
_GENERICOS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "live.com", "protonmail.com"}

PROMPT = """Eres un analista de empresas B2B en Latinoamérica. Te doy el dominio de correo
y/o el NOMBRE de la empresa de una persona. Investiga QUÉ empresa/institución es (usa tu
conocimiento; incluye empresas, universidades y organismos públicos) y responde SOLO
JSON válido, sin markdown:
{
  "empresa": "nombre comercial/oficial",
  "es_empresa_conocida": true/false,
  "pais": "país principal de operación",
  "industria": "sector (ej: energía, minería, construcción, retail, salud, educación, manufactura, gobierno)",
  "descripcion": "1-2 frases sobre a qué se dedica",
  "presencia": "dónde opera (ej: Chile y 5 países de LatAm)",
  "sitio_web": "https://... (el sitio oficial)",
  "dominio_empresa": "dominio web oficial sin www (ej: usach.cl), para el logo",
  "rut": "RUT chileno si lo conoces con certeza (formato 99.999.999-9), sino null",
  "direccion": "dirección de la casa matriz si la conoces, sino null",
  "categorias_compra_probables": ["categorías de insumos/productos que suele comprar, 2 a 5, de: electronica, construccion, carpinteria, industrial, electrico, hidraulico, neumatico, tuberias_valvulas, mecanico, insumos_medicos, consumible, servicio"],
  "confianza": "alto|medio|bajo"
}
IMPORTANTE: rut y direccion SOLO si estás seguro; si dudas, pon null (el usuario los confirmará).
Si no reconoces la empresa, pon es_empresa_conocida=false y confianza=bajo, pero igual deduce lo que puedas."""


class InvestigarRequest(BaseModel):
    email: Optional[str] = None
    dominio: Optional[str] = None
    nombre_empresa: Optional[str] = None   # para correos genéricos: investiga por nombre


def _dominio_de(email_o_dominio: str) -> str:
    s = (email_o_dominio or "").strip().lower()
    if "@" in s:
        s = s.split("@", 1)[1]
    return re.sub(r"^www\.", "", s)


# RUT chileno con puntos (empresas suelen listarlo en el footer/contacto)
_RUT_RE = re.compile(r"\b(\d{1,2}\.\d{3}\.\d{3}-[\dkK])\b")


async def _scrape_rut_direccion(dominio: str) -> dict:
    """Scrapea el sitio de la empresa (home + /contacto) buscando RUT y dirección."""
    import httpx
    from bs4 import BeautifulSoup

    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    rut = direccion = None
    try:
        async with httpx.AsyncClient(timeout=7.0, headers={"User-Agent": UA}, follow_redirects=True) as client:
            for ruta in ("", "/contacto", "/contactenos", "/nosotros"):
                try:
                    resp = await client.get(f"https://{dominio}{ruta}")
                    if resp.status_code != 200:
                        continue
                    html = resp.text
                except Exception:
                    continue

                if not rut:
                    m = _RUT_RE.search(html)
                    if m:
                        rut = m.group(1)

                # Dirección: solo si parece dirección real (calle + número)
                if not direccion:
                    soup = BeautifulSoup(html, "html.parser")
                    texto = soup.get_text(" ", strip=True)
                    md = re.search(
                        r"(?:direcci[oó]n)\s*:?\s*((?:Av\.?|Avenida|Calle|Camino|Pasaje)?\s*[A-Za-zÁÉÍÓÚáéíóúÑñ .]{5,40}\s+\d{2,5}[A-Za-z0-9 ,#°-]{0,30})",
                        texto, re.I,
                    )
                    if md:
                        direccion = re.sub(r"\s+", " ", md.group(1)).strip(" .,")

                if rut and direccion:
                    break
    except Exception as e:
        print(f"[Onboarding scrape] {dominio}: {e}")
    return {"rut": rut, "direccion": direccion}


def _logos_de(dominio: str) -> list[str]:
    return [
        f"https://logo.clearbit.com/{dominio}",
        f"https://www.google.com/s2/favicons?domain={dominio}&sz=128",
    ]


@router.post("/investigar-empresa")
async def investigar_empresa(req: InvestigarRequest):
    from app.config import settings

    dominio = _dominio_de(req.dominio or req.email or "")
    nombre = (req.nombre_empresa or "").strip()
    tld = dominio.rsplit(".", 1)[-1] if "." in dominio else ""
    pais_tld = _TLD_PAIS.get(tld)
    generico = dominio in _GENERICOS

    # Se puede investigar si hay un dominio corporativo O un nombre de empresa
    if (not dominio or "." not in dominio) and not nombre:
        raise HTTPException(status_code=400, detail="Falta dominio o nombre de empresa")

    base = {"dominio": dominio, "pais_tld": pais_tld, "generico": generico,
            "logo_candidatos": _logos_de(dominio) if not generico else []}

    # Correo genérico y sin nombre → pedir el nombre (el frontend re-investiga con él)
    if (generico or not dominio or "." not in dominio) and not nombre:
        return {**base, "empresa": None, "es_empresa_conocida": False, "confianza": "bajo",
                "rut": None, "direccion": None}

    if not settings.gemini_api_key:
        return {**base, "empresa": nombre or None, "es_empresa_conocida": False, "confianza": "bajo"}

    async def _gemini() -> dict:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        ctx = ""
        if nombre:
            ctx += f"\nNombre de la empresa: {nombre}"
        if dominio and not generico:
            ctx += f"\nDominio de correo corporativo: {dominio}"
        if pais_tld:
            ctx += f"\nPaís sugerido por el TLD: {pais_tld}"
        resp = await asyncio.wait_for(model.generate_content_async(PROMPT + "\n" + ctx), timeout=25.0)
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    # Dominio a scrapear para RUT/dirección: el corporativo, o el que deduzca la IA
    dom_scrape = dominio if (dominio and not generico) else None
    try:
        gem_res = await _gemini()
    except Exception as e:
        print(f"[Onboarding] {dominio or nombre}: {e}")
        gem_res = {"empresa": nombre or dominio.split(".")[0].title(), "es_empresa_conocida": False, "confianza": "bajo"}

    # Logo: del dominio real de la empresa (lo mejor), luego el corporativo del correo
    dom_empresa = _dominio_de(gem_res.get("dominio_empresa") or "") if gem_res.get("dominio_empresa") else None
    logos: list[str] = []
    if dom_empresa and "." in dom_empresa:
        logos += _logos_de(dom_empresa)
        if not dom_scrape:
            dom_scrape = dom_empresa
    if not generico and dominio:
        logos += _logos_de(dominio)
    gem_res["logo_candidatos"] = logos or base["logo_candidatos"]

    # Scraping de RUT/dirección del sitio real (si la IA no los dio)
    scrape = {"rut": None, "direccion": None}
    if dom_scrape and not (gem_res.get("rut") and gem_res.get("direccion")):
        try:
            scrape = await _scrape_rut_direccion(dom_scrape)
        except Exception:
            pass

    gem_res.setdefault("sitio_web", f"https://{dom_empresa or dominio}")
    # La IA gana para rut/dirección si los tiene; sino el scrape
    if not gem_res.get("rut"):
        gem_res["rut"] = scrape.get("rut")
    if not gem_res.get("direccion"):
        gem_res["direccion"] = scrape.get("direccion")
    return {**base, **gem_res}
