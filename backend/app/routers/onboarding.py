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
corporativo de una persona. Investiga QUÉ empresa es (usa tu conocimiento) y responde SOLO
JSON válido, sin markdown:
{
  "empresa": "nombre comercial de la empresa",
  "es_empresa_conocida": true/false,
  "pais": "país principal de operación",
  "industria": "sector económico (ej: energía, minería, construcción, retail, salud, manufactura)",
  "descripcion": "1-2 frases sobre qué hace la empresa",
  "presencia": "dónde opera (ej: Chile y 5 países de LatAm)",
  "sitio_web": "https://... (el sitio oficial, deducido del dominio)",
  "rut": "RUT chileno de la empresa si lo conoces con certeza (formato 99.999.999-9), sino null",
  "direccion": "dirección de la casa matriz si la conoces, sino null",
  "categorias_compra_probables": ["categorías de insumos/productos que esta empresa suele comprar, 2 a 5, de: electronica, construccion, carpinteria, industrial, electrico, hidraulico, neumatico, tuberias_valvulas, mecanico, insumos_medicos, consumible, servicio"],
  "confianza": "alto|medio|bajo"
}
IMPORTANTE: rut y direccion SOLO si estás seguro; si dudas, pon null (el usuario los confirmará).
Si el dominio es genérico o no reconoces la empresa, pon es_empresa_conocida=false y confianza=bajo,
pero igual deduce lo que puedas del nombre del dominio."""


class InvestigarRequest(BaseModel):
    email: Optional[str] = None
    dominio: Optional[str] = None


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


@router.post("/investigar-empresa")
async def investigar_empresa(req: InvestigarRequest):
    from app.config import settings

    dominio = _dominio_de(req.dominio or req.email or "")
    if not dominio or "." not in dominio:
        raise HTTPException(status_code=400, detail="Dominio inválido")

    tld = dominio.rsplit(".", 1)[-1]
    pais_tld = _TLD_PAIS.get(tld)
    generico = dominio in _GENERICOS

    base = {
        "dominio": dominio,
        "pais_tld": pais_tld,
        "generico": generico,
        # Logos candidatos (el usuario confirma/elige); Clearbit + favicon Google
        "logo_candidatos": [
            f"https://logo.clearbit.com/{dominio}",
            f"https://www.google.com/s2/favicons?domain={dominio}&sz=128",
        ],
    }

    if generico or not settings.gemini_api_key:
        return {**base, "empresa": None, "es_empresa_conocida": False, "confianza": "bajo",
                "rut": None, "direccion": None}

    async def _gemini() -> dict:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = PROMPT + f"\n\nDominio de correo: {dominio}" + (f"\nPaís sugerido por el TLD: {pais_tld}" if pais_tld else "")
        resp = await asyncio.wait_for(model.generate_content_async(prompt), timeout=25.0)
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    # Investigación IA + scraping del sitio (RUT/dirección) en paralelo
    gem_res, scrape = await asyncio.gather(_gemini(), _scrape_rut_direccion(dominio), return_exceptions=True)

    if isinstance(gem_res, Exception):
        print(f"[Onboarding] {dominio}: {gem_res}")
        gem_res = {"empresa": dominio.split(".")[0].title(), "es_empresa_conocida": False, "confianza": "bajo"}
    if isinstance(scrape, Exception):
        scrape = {"rut": None, "direccion": None}

    gem_res.setdefault("sitio_web", f"https://{dominio}")
    return {**base, **gem_res, **scrape}
