"""
Alta manual, investigación automática y ficha de proveedores (Fase 3 de
Supplier Capability Intelligence). Reutiliza el directorio existente
(`proveedores`/`proveedor_contactos`, dedupe de `proveedores_matching.py`) y
las capacidades de la Fase 1 (`supplier_capabilities`) — no crea un
directorio paralelo.

La investigación reutiliza los helpers de `onboarding.py` (RUT/dirección por
scraping, logos, país por TLD) pero con un prompt propio: onboarding perfila
al COMPRADOR (la empresa del usuario), esto perfila a un PROVEEDOR (qué
vende, no qué compra) — no hay que confundir los dos perfiles.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/proveedores", tags=["proveedores"])

CATEGORIAS_VALIDAS = {
    "electronica", "construccion", "carpinteria", "insumos_medicos", "industrial",
    "tuberias_valvulas", "mecanico", "electrico", "hidraulico", "neumatico",
    "servicio", "consumible", "otro",
}

PROMPT_INVESTIGAR_PROVEEDOR = """Eres un analista de procurement B2B en Chile/Latinoamérica. Te doy el
nombre y/o dominio de una empresa que actúa como PROVEEDOR (vende insumos, materiales o
servicios) — no es la empresa del usuario, es alguien a quien se le podría comprar.

Investiga qué vende esta empresa y responde SOLO JSON válido, sin markdown:
{
  "razon_social": "nombre comercial/oficial",
  "es_empresa_conocida": true/false,
  "pais": "país principal de operación",
  "territorio": "dónde despacha/atiende (ej: Región Metropolitana, todo Chile, LatAm)",
  "descripcion": "1-2 frases sobre qué vende o qué servicio presta",
  "industria": "sector",
  "sitio_web": "https://... (el sitio oficial)",
  "dominio_empresa": "dominio web oficial sin www",
  "rut": "RUT chileno si lo conoces con certeza (formato 99.999.999-9), sino null",
  "categorias": ["categorías que abastece, 1 a 4, de: electronica, construccion, carpinteria, insumos_medicos, industrial, tuberias_valvulas, mecanico, electrico, hidraulico, neumatico, servicio, consumible, otro"],
  "subcategorias": ["productos/líneas específicas que vende, texto libre, 0 a 6"],
  "keywords": ["palabras clave asociadas a lo que vende, 0 a 8"],
  "confianza": "alto|medio|bajo",
  "fuentes": ["de dónde sacaste esto, ej: sitio web oficial, conocimiento general"]
}
IMPORTANTE: rut SOLO si estás seguro; si dudas, pon null (el usuario lo confirma).
Si no reconoces la empresa, deduce igual desde el nombre/dominio (ej: rubro por palabras del
nombre) y pon es_empresa_conocida=false y confianza=bajo."""


class InvestigarProveedorRequest(BaseModel):
    nombre: Optional[str] = None
    dominio: Optional[str] = None
    sitio_web: Optional[str] = None


@router.post("/investigar")
async def investigar_proveedor(req: InvestigarProveedorRequest):
    """Solo investiga y devuelve sugerencias — no guarda nada. El usuario
    revisa y confirma antes de que algo se persista (POST /{id}/categorias)."""
    from app.config import settings
    from app.routers.onboarding import _dominio_de, _buscar_rut_boletaofactura, _scrape_rut_direccion, _logos_de, _TLD_PAIS, _GENERICOS

    nombre = (req.nombre or "").strip()
    dominio = _dominio_de(req.dominio or req.sitio_web or "")
    if not nombre and not dominio:
        raise HTTPException(status_code=400, detail="Falta nombre o dominio/sitio web del proveedor")

    tld = dominio.rsplit(".", 1)[-1] if "." in dominio else ""
    pais_tld = _TLD_PAIS.get(tld)
    generico = dominio in _GENERICOS
    base = {
        "dominio": dominio, "pais_tld": pais_tld,
        "logo_candidatos": _logos_de(dominio) if dominio and not generico else [],
    }

    if not settings.gemini_api_key:
        return {**base, "razon_social": nombre or None, "es_empresa_conocida": False, "confianza": "bajo",
                "categorias": [], "subcategorias": [], "keywords": [], "rut": None}

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    ctx = ""
    if nombre:
        ctx += f"\nNombre del proveedor: {nombre}"
    if dominio and not generico:
        ctx += f"\nDominio: {dominio}"
    if pais_tld:
        ctx += f"\nPaís sugerido por el TLD: {pais_tld}"

    try:
        resp = await asyncio.wait_for(model.generate_content_async(PROMPT_INVESTIGAR_PROVEEDOR + "\n" + ctx), timeout=25.0)
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        gem_res = json.loads(text.strip())
    except Exception as e:
        print(f"[Proveedores] investigar {dominio or nombre}: {e}")
        gem_res = {"razon_social": nombre or (dominio.split(".")[0].title() if dominio else None), "es_empresa_conocida": False, "confianza": "bajo"}

    gem_res["categorias"] = [c for c in (gem_res.get("categorias") or []) if c in CATEGORIAS_VALIDAS]

    dom_empresa = _dominio_de(gem_res.get("dominio_empresa") or "") if gem_res.get("dominio_empresa") else None
    dom_scrape = dominio if (dominio and not generico) else dom_empresa
    logos = list(base["logo_candidatos"])
    if dom_empresa and "." in dom_empresa:
        logos += _logos_de(dom_empresa)
    gem_res["logo_candidatos"] = logos or base["logo_candidatos"]

    if not gem_res.get("rut"):
        razon = gem_res.get("razon_social") or nombre
        if razon:
            try:
                gem_res["rut"] = await _buscar_rut_boletaofactura(razon)
            except Exception:
                pass
    if not gem_res.get("rut") and dom_scrape:
        try:
            scrape = await _scrape_rut_direccion(dom_scrape)
            gem_res["rut"] = gem_res.get("rut") or scrape.get("rut")
        except Exception:
            pass

    gem_res.setdefault("sitio_web", f"https://{dom_empresa or dominio}" if (dom_empresa or dominio) else None)
    return {**base, **gem_res}


class CrearProveedorRequest(BaseModel):
    nombre: str
    rut: Optional[str] = None
    sitio_web: Optional[str] = None
    pais: str = "CL"
    email: Optional[str] = None
    contacto_nombre: Optional[str] = None
    telefono: Optional[str] = None
    categorias: list[str] = Field(default_factory=list)
    notas_privadas: Optional[str] = None
    preferido: bool = False
    bloqueado: bool = False


@router.post("")
async def crear_proveedor(req: CrearProveedorRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Alta manual — reutiliza el mismo dedupe (RUT → email/dominio → nombre)
    que usan la importación Excel y el agente de Gmail, para no crear un
    directorio paralelo."""
    from app.services.supabase import get_supabase
    from app.services.proveedores_matching import resolver_o_crear_proveedor, resolver_o_crear_contacto
    from app.services.supplier_capability_intelligence import registrar_evento

    nombre = req.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    categorias = [c.lower().strip() for c in req.categorias if c.lower().strip() in CATEGORIAS_VALIDAS]

    sb = get_supabase()
    proveedor_id = resolver_o_crear_proveedor(sb, ctx.actor_user_id, nombre, req.email, req.rut)

    cambios: dict = {
        "nombre": nombre[:200],
        "pais": req.pais,
        "preferido": req.preferido,
        "bloqueado": req.bloqueado,
    }
    if req.sitio_web:
        cambios["sitio_web"] = req.sitio_web[:300]
    if req.telefono:
        cambios["telefono"] = req.telefono[:50]
    if req.notas_privadas:
        cambios["notas_privadas"] = req.notas_privadas[:2000]
    if req.email:
        cambios["email"] = req.email[:200]
    sb.table("proveedores").update(cambios).eq("id", proveedor_id).execute()

    if req.email:
        resolver_o_crear_contacto(sb, ctx.actor_user_id, proveedor_id, req.email, nombre=req.contacto_nombre, origen="manual")

    for categoria in categorias:
        registrar_evento(
            ctx.actor_user_id, proveedor_id, "manual_category_assigned",
            categoria_confirmada=categoria,
        )

    return sb.table("proveedores").select("*").eq("id", proveedor_id).single().execute().data


@router.get("/{proveedor_id}")
async def ficha_proveedor(proveedor_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    from app.services.supplier_capability_intelligence import listar_capacidades

    sb = get_supabase()
    ids = ctx.user_ids_organizacion
    proveedor = sb.table("proveedores").select("*").eq("id", proveedor_id).in_("user_id", ids).maybe_single().execute().data
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    contactos = sb.table("proveedor_contactos").select("*").eq("proveedor_id", proveedor_id).execute().data or []
    capacidades = listar_capacidades(ctx.actor_user_id, proveedor_id)
    ocs = sb.table("ordenes_compra").select(
        "numero_oc, estado, precio_total, moneda, created_at, confirmada_at"
    ).in_("user_id", ids).eq("proveedor_nombre", proveedor["nombre"]).order("created_at", desc=True).execute().data or []

    return {
        "proveedor": proveedor,
        "contactos": contactos,
        "capacidades": capacidades,
        "ordenes": ocs,
    }


class EditarProveedorRequest(BaseModel):
    nombre: Optional[str] = None
    rut: Optional[str] = None
    sitio_web: Optional[str] = None
    pais: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    notas_privadas: Optional[str] = None
    preferido: Optional[bool] = None
    bloqueado: Optional[bool] = None


@router.patch("/{proveedor_id}")
async def editar_proveedor(proveedor_id: str, req: EditarProveedorRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    from app.services.proveedores_matching import normalizar_rut

    sb = get_supabase()
    existente = sb.table("proveedores").select("id").eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).maybe_single().execute().data
    if not existente:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    cambios = {}
    for campo in ("nombre", "sitio_web", "pais", "email", "telefono", "notas_privadas", "preferido", "bloqueado"):
        valor = getattr(req, campo)
        if valor is not None:
            cambios[campo] = valor
    if req.rut:
        cambios["rut"] = normalizar_rut(req.rut)

    if not cambios:
        return sb.table("proveedores").select("*").eq("id", proveedor_id).single().execute().data

    sb.table("proveedores").update(cambios).eq("id", proveedor_id).execute()
    return sb.table("proveedores").select("*").eq("id", proveedor_id).single().execute().data


class ConfirmarCategoriasRequest(BaseModel):
    categorias: list[str]


@router.post("/{proveedor_id}/categorias")
async def confirmar_categorias(proveedor_id: str, req: ConfirmarCategoriasRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Confirma una o más categorías (sugeridas por /investigar o elegidas a
    mano) — cada una queda como evento auditable con confianza máxima."""
    from app.services.supabase import get_supabase
    from app.services.supplier_capability_intelligence import registrar_evento

    sb = get_supabase()
    proveedor = sb.table("proveedores").select("id").eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).maybe_single().execute().data
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    categorias = [c.lower().strip() for c in req.categorias if c.lower().strip() in CATEGORIAS_VALIDAS]
    if not categorias:
        raise HTTPException(status_code=400, detail="Ninguna categoría válida")

    resultado = [registrar_evento(ctx.actor_user_id, proveedor_id, "manual_category_assigned", categoria_confirmada=c) for c in categorias]
    return {"capacidades": resultado}


@router.delete("/{proveedor_id}/categorias/{categoria}")
async def quitar_categoria(proveedor_id: str, categoria: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    from app.services.supplier_capability_intelligence import rechazar_capacidad

    sb = get_supabase()
    proveedor = sb.table("proveedores").select("id").eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).maybe_single().execute().data
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    rechazar_capacidad(ctx.actor_user_id, proveedor_id, categoria.lower().strip())
    return {"success": True}
