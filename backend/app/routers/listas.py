"""
Listas de cotización: varios ítems cotizados en paralelo, agrupados.

Persistencia sin DDL: cada lista es una fila de `proyectos` cuya columna
`descripcion` guarda un JSON con esta forma:

    {
      "tipo": "lista_cotizacion",
      "items": [{"cotizacion_id": "...", "nombre": "...", "comparado": false}],
      "definitivos": {
          "<cotizacion_id>": {"proveedor": "...", "precio": 123, "moneda": "CLP",
                               "url": "...", "fuente": "...", "resultado_id": "..."}
      }
    }

El monto_total del proyecto se recalcula con los definitivos (en CLP aprox).
Cuando exista una tabla dedicada (migración futura) basta cambiar este router.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/listas", tags=["listas"])

MARCA_LISTA = "lista_cotizacion"

# El JSON de la lista se actualiza con leer-modificar-escribir: dos requests
# simultáneos (ej: "comparar y seguir" rápido entre ítems) pueden pisarse las
# marcas entre sí. Un lock por lista serializa esas escrituras.
_locks: dict[str, asyncio.Lock] = {}


def _lock_de(lista_id: str) -> asyncio.Lock:
    if lista_id not in _locks:
        _locks[lista_id] = asyncio.Lock()
    return _locks[lista_id]


def _parse_lista(proyecto: dict) -> Optional[dict]:
    """Devuelve el JSON de lista si el proyecto es una lista de cotización."""
    try:
        data = json.loads(proyecto.get("descripcion") or "")
        if isinstance(data, dict) and data.get("tipo") == MARCA_LISTA:
            return data
    except Exception:
        pass
    return None


def _guardar_lista(sb, proyecto_id: str, data: dict) -> None:
    sb.table("proyectos").update({"descripcion": json.dumps(data, ensure_ascii=False)}).eq("id", proyecto_id).execute()


def _monto_total(data: dict) -> float:
    """Total de la lista: precio CLP del definitivo × cantidad de cada ítem."""
    cantidades = {it["cotizacion_id"]: float(it.get("cantidad") or 1) for it in data.get("items", [])}
    return sum(
        float(d.get("precio_clp") or 0) * cantidades.get(cid, 1)
        for cid, d in data.get("definitivos", {}).items()
    )


class ItemListaIn(BaseModel):
    cotizacion_id: str
    nombre: str
    cantidad: float = 1


class CrearListaRequest(BaseModel):
    user_id: str
    nombre: str
    items: list[ItemListaIn]


@router.post("")
async def crear_lista(req: CrearListaRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    data = {
        "tipo": MARCA_LISTA,
        "items": [{"cotizacion_id": it.cotizacion_id, "nombre": it.nombre, "cantidad": it.cantidad or 1, "comparado": False} for it in req.items],
        "definitivos": {},
    }
    row = {
        "user_id": req.user_id,
        "nombre": req.nombre,
        "descripcion": json.dumps(data, ensure_ascii=False),
        "estado": "borrador",
        "monto_total": 0,
    }
    res = sb.table("proyectos").insert(row).execute()
    return {"id": res.data[0]["id"], **data}


@router.get("")
async def listar_listas(user_id: str):
    """Todas las cotizaciones del usuario, unificadas: cada una es una "lista"
    de 1 o más ítems. Las cotizaciones sueltas (creadas antes de unificar el
    flujo, o vía integraciones externas) se muestran como listas de 1 ítem
    hasta que el usuario las abre, momento en que se envuelven de verdad
    (ver `_resolver_o_envolver`)."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    res = sb.table("proyectos").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    listas = []
    cotizacion_ids_en_listas: set[str] = set()
    for p in res.data or []:
        data = _parse_lista(p)
        if data:
            n_items = len(data.get("items", []))
            for it in data.get("items", []):
                cotizacion_ids_en_listas.add(it["cotizacion_id"])
            listas.append({
                "id": p["id"],
                "nombre": p["nombre"],
                "created_at": p.get("created_at"),
                "monto_total": p.get("monto_total") or 0,
                "n_items": n_items,
                "n_comparados": sum(1 for it in data.get("items", []) if it.get("comparado")),
                "n_definitivos": len(data.get("definitivos", {})),
                "aprobacion_estado": (data.get("aprobacion") or {}).get("estado"),
                "es_cotizacion_simple": False,
            })

    # Cotizaciones sueltas (no envueltas todavía en ninguna lista)
    try:
        cots = sb.table("cotizaciones").select(
            "id, nombre_identificado, estado, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
    except Exception:
        cots = None
    for c in (cots.data or []) if cots else []:
        if c["id"] in cotizacion_ids_en_listas:
            continue
        listas.append({
            "id": c["id"],
            "nombre": c.get("nombre_identificado") or "Ítem sin nombre",
            "created_at": c.get("created_at"),
            "monto_total": 0,
            "n_items": 1,
            "n_comparados": 0,
            "n_definitivos": 0,
            "aprobacion_estado": None,
            "es_cotizacion_simple": True,
        })

    listas.sort(key=lambda l: l.get("created_at") or "", reverse=True)
    return listas


def _envolver_cotizacion_suelta(sb, cotizacion_id: str, user_id: str) -> Optional[dict]:
    """Si `cotizacion_id` es una cotización suelta (no una lista), la envuelve
    en una lista de 1 ítem (fila nueva en `proyectos`) y devuelve esa fila.
    Devuelve None si no existe una cotización con ese id para el usuario."""
    cot = sb.table("cotizaciones").select("id, nombre_identificado").eq("id", cotizacion_id).eq("user_id", user_id).limit(1).execute()
    fila = (cot.data or [None])[0]
    if not fila:
        return None

    data = {
        "tipo": MARCA_LISTA,
        "items": [{"cotizacion_id": fila["id"], "nombre": fila.get("nombre_identificado") or "Ítem", "cantidad": 1, "comparado": False}],
        "definitivos": {},
    }
    row = {
        "user_id": user_id,
        "nombre": fila.get("nombre_identificado") or "Cotización",
        "descripcion": json.dumps(data, ensure_ascii=False),
        "estado": "borrador",
        "monto_total": 0,
    }
    ins = sb.table("proyectos").insert(row).execute()
    return ins.data[0]


def _resolver_o_envolver(sb, lista_id: str, user_id: str) -> Optional[dict]:
    """Busca `lista_id` como proyecto (lista real). Si no existe, prueba si es
    una cotización suelta y la envuelve automáticamente en una lista nueva."""
    proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", user_id).limit(1).execute()
    fila = (proy.data or [None])[0]
    if fila and _parse_lista(fila):
        return fila
    return _envolver_cotizacion_suelta(sb, lista_id, user_id)


def _comparador_de(sb, cotizacion_id: str) -> list[dict]:
    """Resultados del comparador de una cotización (mismo criterio que la vista)."""
    base_cols = (
        "id, proveedor_nombre, proveedor_email, precio, moneda, url, pais, fuente, "
        "relevante, solicitud_enviada_at, precio_cotizado, plazo_entrega"
    )
    try:
        res = sb.table("resultados").select(base_cols + ", metadata").eq("cotizacion_id", cotizacion_id).execute()
    except Exception:
        res = sb.table("resultados").select(base_cols).eq("cotizacion_id", cotizacion_id).execute()
    filas = []
    for r in res.data or []:
        if r.get("relevante") is False and not r.get("solicitud_enviada_at"):
            continue
        meta = {}
        try:
            meta = json.loads(r["metadata"]) if r.get("metadata") else {}
        except Exception:
            pass
        filas.append({
            "resultado_id": r["id"],
            "proveedor": r.get("proveedor_nombre"),
            "fuente": meta.get("fuente_label") or r.get("fuente"),
            "precio": r.get("precio"),
            "moneda": r.get("moneda") or "CLP",
            "precio_cotizado": r.get("precio_cotizado"),
            "plazo_entrega": r.get("plazo_entrega") or meta.get("plazo_entrega_estimado"),
            "ubicacion": meta.get("ubicacion_vendedor") or ("Chile" if r.get("pais") == "CL" else r.get("pais")),
            "contacto": r.get("proveedor_email"),
            "url": r.get("url") or "",
            "descripcion": meta.get("descripcion") or meta.get("titulo"),
        })
    filas.sort(key=lambda f: (f["precio_cotizado"] or f["precio"] or 1e18))
    return filas


@router.get("/{lista_id}")
async def detalle_lista(lista_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    # Si lista_id es en realidad una cotización suelta, se envuelve al vuelo:
    # así toda cotización (1 ítem o N) pasa por la misma pantalla de detalle.
    proy_data = _resolver_o_envolver(sb, lista_id, user_id)
    if not proy_data:
        raise HTTPException(status_code=404, detail="Lista no encontrada")
    data = _parse_lista(proy_data)
    if not data:
        raise HTTPException(status_code=404, detail="El proyecto no es una lista de cotización")

    items = data.get("items", [])
    # Comparador de cada ítem en paralelo
    comparadores = await asyncio.gather(*[
        asyncio.to_thread(_comparador_de, sb, it["cotizacion_id"]) for it in items
    ])

    definitivos = data.get("definitivos", {})
    result = {
        "id": proy_data["id"],
        "nombre": proy_data["nombre"],
        "created_at": proy_data.get("created_at"),
        "monto_total": proy_data.get("monto_total") or 0,
        "items": [
            {
                **it,
                "cantidad": float(it.get("cantidad") or 1),
                "comparados": comparadores[i],
                "definitivo": definitivos.get(it["cotizacion_id"]),
            }
            for i, it in enumerate(items)
        ],
    }
    if data.get("aprobacion"):
        result["aprobacion"] = data["aprobacion"]
    if data.get("justificaciones"):
        result["justificaciones"] = data["justificaciones"]
    if data.get("compras"):
        result["compras"] = data["compras"]
    return result


class MarcarComparadoRequest(BaseModel):
    user_id: str
    cotizacion_id: str


@router.post("/{lista_id}/comparado")
async def marcar_comparado(lista_id: str, req: MarcarComparadoRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        for it in data.get("items", []):
            if it["cotizacion_id"] == req.cotizacion_id:
                it["comparado"] = True
        _guardar_lista(sb, lista_id, data)

    items = data.get("items", [])
    pendientes = [it for it in items if not it.get("comparado")]
    return {
        "success": True,
        "comparados": len(items) - len(pendientes),
        "total": len(items),
        "siguiente": pendientes[0] if pendientes else None,
    }


class DefinitivoRequest(BaseModel):
    user_id: str
    cotizacion_id: str
    resultado_id: Optional[str] = None
    proveedor: Optional[str] = None
    precio: Optional[float] = None
    moneda: str = "CLP"
    url: Optional[str] = None
    fuente: Optional[str] = None
    # precio aprox en CLP para el monto_total (el frontend ya tiene las tasas)
    precio_clp: Optional[float] = None
    quitar: bool = False


@router.post("/{lista_id}/definitivo")
async def elegir_definitivo(lista_id: str, req: DefinitivoRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        definitivos = data.setdefault("definitivos", {})
        if req.quitar:
            definitivos.pop(req.cotizacion_id, None)
        else:
            definitivos[req.cotizacion_id] = {
                "resultado_id": req.resultado_id,
                "proveedor": req.proveedor,
                "precio": req.precio,
                "moneda": req.moneda,
                "url": req.url,
                "fuente": req.fuente,
                "precio_clp": req.precio_clp if req.precio_clp is not None else req.precio,
            }

        monto_total = _monto_total(data)
        _guardar_lista(sb, lista_id, data)
        sb.table("proyectos").update({"monto_total": monto_total}).eq("id", lista_id).execute()

    return {"success": True, "definitivos": len(definitivos), "monto_total": monto_total}


class CantidadRequest(BaseModel):
    user_id: str
    cotizacion_id: str
    cantidad: float


@router.post("/{lista_id}/cantidad")
async def actualizar_cantidad(lista_id: str, req: CantidadRequest):
    """Actualiza la cantidad a comprar de un ítem de la lista."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.cantidad <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        for it in data.get("items", []):
            if it["cotizacion_id"] == req.cotizacion_id:
                it["cantidad"] = req.cantidad

        monto_total = _monto_total(data)
        _guardar_lista(sb, lista_id, data)
        sb.table("proyectos").update({"monto_total": monto_total}).eq("id", lista_id).execute()

    return {"success": True, "monto_total": monto_total}


class SolicitarAprobacionRequest(BaseModel):
    user_id: str
    aprobador_email: str
    justificaciones: dict = {}  # {cotizacion_id: "texto justificación"}
    nombre_solicitante: str = ""
    empresa: str = ""


@router.post("/{lista_id}/solicitar-aprobacion")
async def solicitar_aprobacion(lista_id: str, req: SolicitarAprobacionRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        definitivos = data.get("definitivos", {})
        items = data.get("items", [])
        if not definitivos:
            raise HTTPException(status_code=400, detail="No hay definitivos elegidos")

        data["justificaciones"] = req.justificaciones

        resumen_items = []
        for it in items:
            cid = it["cotizacion_id"]
            d = definitivos.get(cid)
            if d:
                resumen_items.append({
                    "cotizacion_id": cid,
                    "nombre": it["nombre"],
                    "cantidad": it.get("cantidad", 1),
                    "proveedor": d.get("proveedor"),
                    "precio_clp": d.get("precio_clp"),
                    "url": d.get("url"),
                    "justificacion": req.justificaciones.get(cid, ""),
                    # Snapshot completo de las opciones consideradas. El
                    # autorizador puede inspeccionarlas sin depender de que la
                    # cotización cambie después del envío.
                    "alternativas": [{
                        "resultado_id": c.get("resultado_id"),
                        "proveedor": c.get("proveedor"),
                        "precio_clp": c.get("precio_cotizado") if c.get("precio_cotizado") is not None else c.get("precio"),
                        "moneda": "CLP" if c.get("precio_cotizado") is not None else c.get("moneda", "CLP"),
                        "url": c.get("url"),
                    } for c in (it.get("comparados") or [])],
                })

        monto_total = _monto_total(data)
        resumen = {
            "lista_nombre": proy.data["nombre"],
            "solicitante": req.nombre_solicitante,
            "empresa": req.empresa,
            "items": resumen_items,
            "monto_total": monto_total,
        }

        from app.routers.aprobaciones import solicitar_aprobacion as crear_solicitud
        from app.routers.aprobaciones import SolicitudRequest
        sol = await crear_solicitud(SolicitudRequest(
            user_id=req.user_id,
            referencia=f"lista:{lista_id}",
            resumen=resumen,
            aprobador_email=req.aprobador_email,
        ))

        data["aprobacion"] = {
            "estado": "pendiente",
            "aprobador_email": req.aprobador_email,
            "token": sol["token"],
            "approval_request_id": sol["id"],
        }
        _guardar_lista(sb, lista_id, data)

    return {
        "success": True,
        "magic_link_aprobar": sol["magic_link_aprobar"],
        "magic_link_rechazar": sol["magic_link_rechazar"],
        "token": sol["token"],
        "expira_at": sol["expira_at"],
    }


class ReenviarAprobacionRequest(BaseModel):
    user_id: str


@router.post("/{lista_id}/reenviar-aprobacion")
async def reenviar_aprobacion(lista_id: str, req: ReenviarAprobacionRequest):
    """Resetea una lista rechazada para poder re-solicitar aprobación."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        aprobacion = data.get("aprobacion", {})
        if aprobacion.get("estado") not in ("rechazado", None):
            raise HTTPException(status_code=400, detail="Solo se puede re-solicitar una lista rechazada")

        data.pop("aprobacion", None)
        _guardar_lista(sb, lista_id, data)

    return {"success": True}


# ─── Compra: OC enviada o compra online ─────────────────────────────────────
# Cuando la lista está autorizada, cada ítem puede:
#   - Enviarse por OC (definitivo tiene email de proveedor)
#   - Comprarse online (solo hay link, no email); se chequea a mano o vía boleta
# El estado por ítem vive en data["compras"][cotizacion_id].

class CompraRequest(BaseModel):
    user_id: str
    cotizacion_id: str
    estado: str  # "enviada_oc" | "comprado" | "pendiente"
    oc_id: Optional[str] = None
    numero_oc: Optional[str] = None
    precio_real: Optional[float] = None  # precio efectivamente pagado (CLP)
    boleta_url: Optional[str] = None
    notas: Optional[str] = None


@router.post("/{lista_id}/compra")
async def actualizar_compra(lista_id: str, req: CompraRequest):
    """Registra el avance de la compra de un ítem: OC enviada, comprado
    online, o desmarcar (volver a pendiente)."""
    from datetime import datetime, timezone
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.estado not in ("enviada_oc", "comprado", "pendiente"):
        raise HTTPException(status_code=400, detail="estado inválido")

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        compras = data.setdefault("compras", {})
        if req.estado == "pendiente":
            compras.pop(req.cotizacion_id, None)
        else:
            entry = compras.get(req.cotizacion_id, {})
            entry["estado"] = req.estado
            if req.oc_id is not None: entry["oc_id"] = req.oc_id
            if req.numero_oc is not None: entry["numero_oc"] = req.numero_oc
            if req.precio_real is not None: entry["precio_real"] = req.precio_real
            if req.boleta_url is not None: entry["boleta_url"] = req.boleta_url
            if req.notas is not None: entry["notas"] = req.notas
            entry[f"{req.estado}_at"] = datetime.now(timezone.utc).isoformat()
            compras[req.cotizacion_id] = entry

        _guardar_lista(sb, lista_id, data)
        return {"success": True, "compras": compras}


def _normalizar(s: str) -> str:
    """Minúsculas sin tildes ni puntuación, para comparar nombres de ítems."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _matchear_item(nombre_ocr: str, items_lista: list[dict]) -> Optional[str]:
    """Busca el ítem de la lista que mejor calce con el nombre leído en la
    boleta (heurística simple: solapamiento de tokens ≥ 2 o subcadena)."""
    n_ocr = _normalizar(nombre_ocr)
    if not n_ocr:
        return None
    toks_ocr = set(n_ocr.split())
    mejor_id, mejor_score = None, 0
    for it in items_lista:
        n_it = _normalizar(it.get("nombre") or "")
        if not n_it:
            continue
        toks_it = set(n_it.split())
        overlap = len(toks_ocr & toks_it)
        # Subcadena directa cuenta como buen match
        if n_ocr in n_it or n_it in n_ocr:
            overlap = max(overlap, 2)
        if overlap > mejor_score:
            mejor_score, mejor_id = overlap, it["cotizacion_id"]
    return mejor_id if mejor_score >= 2 else None


class BoletaScanRequest(BaseModel):
    user_id: str
    imagen_base64: str
    imagen_mime: str = "image/jpeg"
    auto_marcar: bool = True  # marcar directo los ítems que la IA reconoció


@router.post("/{lista_id}/boleta-scan")
async def escanear_boleta(lista_id: str, req: BoletaScanRequest):
    """Recibe una foto de boleta/factura, la parsea con Gemini vision y (si
    `auto_marcar`) marca los ítems reconocidos como comprados con su precio
    real. Guarda la boleta en Supabase Storage (bucket `boletas`)."""
    import base64
    import json as _json
    from datetime import datetime, timezone
    from app.config import settings
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail="Gemini no configurado")

    # 1. Cargar la lista y armar el contexto de ítems para el prompt
    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        items_lista = data.get("items", [])
        pendientes = [it for it in items_lista
                      if (data.get("compras", {}).get(it["cotizacion_id"], {}).get("estado")) != "comprado"]
        nombres_pendientes = [f"- {it['nombre']} (x{int(it.get('cantidad', 1))})" for it in pendientes]

    # 2. Llamar a Gemini vision (fuera del lock, es lento)
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "Lee esta boleta/factura chilena y extrae los ítems comprados. "
            "Devuelve SOLO JSON con esta forma: "
            '{"proveedor": "...", "fecha": "YYYY-MM-DD", "total": 0, '
            '"items": [{"nombre": "...", "cantidad": 1, "precio_unitario": 0, "precio_total": 0}]}. '
            "Precios en CLP sin puntos ni símbolos. Si la lista de compra esperada es útil, "
            "trata de calzar los nombres:\n" + "\n".join(nombres_pendientes[:20])
        )
        img_bytes = base64.b64decode(req.imagen_base64)
        resp = model.generate_content([
            prompt,
            {"mime_type": req.imagen_mime, "data": img_bytes},
        ])
        raw = (resp.text or "").strip()
        # Gemini a veces devuelve ```json ... ```
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        if raw.startswith("json"):
            raw = raw[4:].lstrip()
        parsed = _json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo leer la boleta: {e}")

    items_ocr = parsed.get("items") or []

    # 3. Subir la boleta a Storage
    boleta_url = None
    try:
        ext = "jpg" if "jpeg" in req.imagen_mime or "jpg" in req.imagen_mime else "png"
        fname = f"{req.user_id}/{lista_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.{ext}"
        sb.storage.from_("boletas").upload(fname, base64.b64decode(req.imagen_base64), {
            "content-type": req.imagen_mime, "upsert": "true",
        })
        boleta_url = sb.storage.from_("boletas").get_public_url(fname)
    except Exception as e:
        print(f"[boleta-scan] no se pudo subir imagen: {e}")

    # 4. Matchear con los ítems de la lista y marcar como comprados
    matches: list[dict] = []
    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", req.user_id).single().execute()
        data = _parse_lista(proy.data) or {}
        compras = data.setdefault("compras", {})

        for it_ocr in items_ocr:
            cid = _matchear_item(it_ocr.get("nombre") or "", data.get("items", []))
            precio = it_ocr.get("precio_total") or it_ocr.get("precio_unitario")
            match = {"nombre_ocr": it_ocr.get("nombre"), "cantidad": it_ocr.get("cantidad"),
                     "precio": precio, "cotizacion_id": cid}
            matches.append(match)
            if cid and req.auto_marcar:
                entry = compras.get(cid, {})
                entry["estado"] = "comprado"
                if precio is not None: entry["precio_real"] = precio
                if boleta_url: entry["boleta_url"] = boleta_url
                entry["comprado_at"] = datetime.now(timezone.utc).isoformat()
                entry["origen"] = "boleta"
                compras[cid] = entry

        if req.auto_marcar:
            _guardar_lista(sb, lista_id, data)

    return {
        "success": True,
        "boleta_url": boleta_url,
        "proveedor": parsed.get("proveedor"),
        "fecha": parsed.get("fecha"),
        "total": parsed.get("total"),
        "items_detectados": matches,
    }


@router.get("/{lista_id}/informe")
async def informe_lista(lista_id: str, user_id: str):
    """Datos para el Informe de la lista: cada ítem con sus comparados
    (descripción scrapeada si falta), definitivo y totales."""
    import httpx
    from app.routers.cotizaciones import _extraer_descripcion_html
    from app.services.supabase import get_supabase
    sb = get_supabase()

    detalle = await detalle_lista(lista_id, user_id)

    # Scraping best-effort de descripciones faltantes (todas las de la lista)
    pendientes = [
        c for it in detalle["items"] for c in it["comparados"]
        if not c.get("descripcion") and c["url"].startswith("http") and "google.com/search" not in c["url"]
    ]
    if pendientes:
        sem = asyncio.Semaphore(6)

        async def scrape(c: dict):
            async with sem:
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=6.0) as client:
                        resp = await client.get(c["url"], headers={"User-Agent": "Mozilla/5.0 (Macintosh) Claria/1.0"})
                        if resp.status_code == 200:
                            c["descripcion"] = _extraer_descripcion_html(resp.text)
                except Exception:
                    pass

        await asyncio.gather(*(scrape(c) for c in pendientes))

    return detalle
