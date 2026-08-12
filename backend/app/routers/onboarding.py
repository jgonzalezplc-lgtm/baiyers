"""
Onboarding inteligente: desde el correo del usuario, investiga la empresa
(nombre, país, industria, rubro de compras probable, logo, sitio) para
acompañar la creación de la cuenta con contexto real.
"""
import asyncio
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

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


def _normaliza_razon_social(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\b(s\.?a\.?|spa|ltda\.?|limitada|e\.?i\.?r\.?l\.?)\b\.?", "", s)
    return re.sub(r"\s+", " ", s).strip()


async def _buscar_rut_boletaofactura(nombre_empresa: str) -> Optional[str]:
    """Rutificador de empresas/fundaciones chilenas: busca por razón social y
    devuelve el RUT de la coincidencia exacta, o el primer resultado como respaldo."""
    import httpx
    from bs4 import BeautifulSoup

    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    nombre = (nombre_empresa or "").strip()
    if not nombre:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": UA}, follow_redirects=True) as client:
            resp = await client.post("https://www.boletaofactura.com/buscar", data={"term": nombre})
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            filas = soup.select("tbody tr")
            if not filas:
                return None

            objetivo = _normaliza_razon_social(nombre)
            respaldo = None
            for fila in filas:
                celdas = fila.find_all("td")
                if len(celdas) < 4:
                    continue
                razon = celdas[0].get_text(strip=True)
                rut = celdas[-1].get_text(strip=True)
                if not rut:
                    continue
                if _normaliza_razon_social(razon) == objetivo:
                    return rut
                if respaldo is None:
                    respaldo = rut
            return respaldo
    except Exception as e:
        print(f"[Onboarding boletaofactura] {nombre_empresa}: {e}")
        return None


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

    # RUT: 1) lo que dijo la IA, 2) el rutificador boletaofactura.com por razón
    # social, 3) scrape del sitio real como último recurso.
    if not gem_res.get("rut"):
        empresa_nombre = gem_res.get("empresa") or nombre
        if empresa_nombre:
            try:
                gem_res["rut"] = await _buscar_rut_boletaofactura(empresa_nombre)
            except Exception:
                pass

    # Scraping de RUT/dirección del sitio real (si aún falta)
    scrape = {"rut": None, "direccion": None}
    if dom_scrape and not (gem_res.get("rut") and gem_res.get("direccion")):
        try:
            scrape = await _scrape_rut_direccion(dom_scrape)
        except Exception:
            pass

    gem_res.setdefault("sitio_web", f"https://{dom_empresa or dominio}")
    if not gem_res.get("rut"):
        gem_res["rut"] = scrape.get("rut")
    if not gem_res.get("direccion"):
        gem_res["direccion"] = scrape.get("direccion")
    return {**base, **gem_res}


# ─── Sesión de onboarding conversacional (Fases 1-2) ───────────────────────
# Reemplaza la máquina de fases con regex del frontend: el backend guarda la
# sesión, extrae campos con tolerancia a lenguaje natural y decide cuándo
# está realmente completa. Nunca confía en un `user_id` del cliente — todo
# sale de `AuthContext` (token verificado contra Supabase).

class TurnoRequest(BaseModel):
    mensaje: str


class LogoCandidatoRequest(BaseModel):
    url: str


def _sesion_o_404(session_id: str, ctx: AuthContext) -> dict:
    from app.services import onboarding_session as sesiones
    sesion = sesiones.obtener_sesion(session_id, ctx.actor_user_id)
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return sesion


@router.post("/sesion")
async def crear_sesion(ctx: AuthContext = Depends(get_auth_context)):
    from app.services import onboarding_session as sesiones
    sesion = sesiones.crear_o_reanudar_sesion(ctx.actor_user_id)
    return sesion


@router.get("/sesion/{session_id}")
async def obtener_sesion_endpoint(session_id: str, ctx: AuthContext = Depends(get_auth_context)):
    return _sesion_o_404(session_id, ctx)


@router.post("/sesion/{session_id}/turno")
async def turno(session_id: str, req: TurnoRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services import onboarding_conversational as conv
    from app.services import onboarding_session as sesiones

    sesion = _sesion_o_404(session_id, ctx)
    if sesion.get("estado") in ("completado", "abandonado"):
        raise HTTPException(status_code=400, detail="La sesión ya no está activa")

    mensaje = (req.mensaje or "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    try:
        resultado = conv.procesar_turno(sesion, mensaje)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    actualizada = sesiones.guardar_turno(
        session_id=session_id,
        user_id=ctx.actor_user_id,
        mensaje_usuario=mensaje,
        mensajes_asistente=resultado["mensajes_asistente"],
        draft_nuevo=resultado["draft"],
        preguntas_pendientes=resultado["preguntas_pendientes"],
        propuesta_workflow=resultado["propuesta_workflow"],
        estado=resultado["estado"],
    )
    return {**actualizada, "completo": resultado["completo"], "campos_rechazados": resultado["campos_rechazados"]}


@router.post("/sesion/{session_id}/confirmar")
async def confirmar_sesion(session_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Cierra la sesión y escribe el perfil organizacional canónico. Solo se
    puede confirmar si no faltan campos críticos — nunca se marca completa
    por inferencia del modelo, solo por esta acción explícita del usuario.

    Todo el cuerpo va envuelto en try/except: una excepción que no sea
    HTTPException devuelve un 500 sin headers de CORS (queda afuera del
    CORSMiddleware) y el navegador la reporta como "Failed to fetch" sin
    ningún detalle — bug real encontrado en producción. Acá se convierte
    cualquier excepción en un HTTPException con el detalle real, además de
    loguear el traceback completo para Railway."""
    from app.services import onboarding_session as sesiones
    from app.services.organizacion import resolver_organizacion

    try:
        sesion = _sesion_o_404(session_id, ctx)
        draft = sesion.get("draft") or {}
        faltantes = sesiones.campos_faltantes(draft)
        if faltantes:
            raise HTTPException(status_code=400, detail=f"Faltan campos por confirmar: {', '.join(faltantes)}")

        from app.services.supabase import get_supabase
        sb = get_supabase()
        ctx_org = resolver_organizacion(ctx.actor_user_id)
        if not ctx_org:
            raise HTTPException(status_code=403, detail="Usuario sin organización asignada")

        valores = {
            "nombre": draft["empresa"]["valor"],
            "rut": draft["rut"]["valor"],
        }
        if draft.get("direccion", {}).get("valor"):
            valores["direccion"] = draft["direccion"]["valor"]
        try:
            sb.table("organizaciones").update(valores).eq("id", ctx_org.organizacion_id).execute()
        except Exception as e:
            # Violación del índice único de RUT (23505) → conflicto manual, no
            # fusionar organizaciones automáticamente.
            if "23505" in str(e) or "duplicate key" in str(e).lower():
                raise HTTPException(status_code=409, detail="Ese RUT ya está registrado en otra organización — revisión manual requerida")
            raise

        sb.table("onboarding_sessions").update({
            "estado": "completado", "organizacion_id": ctx_org.organizacion_id,
        }).eq("id", session_id).execute()

        return {"estado": "completado", "organizacion_id": ctx_org.organizacion_id}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[Onboarding] error confirmando sesión {session_id}: {e!r}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"No pude confirmar tu perfil ({type(e).__name__}: {e}). Intenta de nuevo.")


@router.post("/sesion/{session_id}/logo/candidato")
async def confirmar_logo_candidato(session_id: str, req: LogoCandidatoRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.logo_upload import descargar_y_validar_url, subir_logo
    from app.services.organizacion import resolver_organizacion

    _sesion_o_404(session_id, ctx)
    ctx_org = resolver_organizacion(ctx.actor_user_id)
    if not ctx_org:
        raise HTTPException(status_code=403, detail="Usuario sin organización asignada")

    try:
        contenido = await descargar_y_validar_url(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    content_type = "image/png"
    for ext, tipo in (("svg", "image/svg+xml"), ("ico", "image/x-icon"), ("webp", "image/webp"), ("jpg", "image/jpeg"), ("jpeg", "image/jpeg")):
        if req.url.lower().endswith(f".{ext}"):
            content_type = tipo
            break

    try:
        logo_url = subir_logo(ctx_org.organizacion_id, content_type, contenido)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo subir el logo: {e}")

    from app.services.supabase import get_supabase
    get_supabase().table("organizaciones").update({
        "logo_url": logo_url, "logo_origen": "investigado",
    }).eq("id", ctx_org.organizacion_id).execute()

    return {"logo_url": logo_url}


@router.post("/sesion/{session_id}/logo/subir")
async def subir_logo_endpoint(session_id: str, archivo: UploadFile = File(...), ctx: AuthContext = Depends(get_auth_context)):
    from app.services.logo_upload import validar_archivo_subido, subir_logo
    from app.services.organizacion import resolver_organizacion

    _sesion_o_404(session_id, ctx)
    ctx_org = resolver_organizacion(ctx.actor_user_id)
    if not ctx_org:
        raise HTTPException(status_code=403, detail="Usuario sin organización asignada")

    contenido = await archivo.read()
    try:
        validar_archivo_subido(archivo.content_type or "", contenido)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        logo_url = subir_logo(ctx_org.organizacion_id, archivo.content_type, contenido)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo subir el logo: {e}")

    from app.services.supabase import get_supabase
    get_supabase().table("organizaciones").update({
        "logo_url": logo_url, "logo_origen": "subido",
    }).eq("id", ctx_org.organizacion_id).execute()

    return {"logo_url": logo_url}
