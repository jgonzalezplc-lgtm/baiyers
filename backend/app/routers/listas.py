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
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("proyectos").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    listas = []
    for p in res.data or []:
        data = _parse_lista(p)
        if data:
            n_items = len(data.get("items", []))
            listas.append({
                "id": p["id"],
                "nombre": p["nombre"],
                "created_at": p.get("created_at"),
                "monto_total": p.get("monto_total") or 0,
                "n_items": n_items,
                "n_comparados": sum(1 for it in data.get("items", []) if it.get("comparado")),
                "n_definitivos": len(data.get("definitivos", {})),
            })
    return listas


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

    proy = sb.table("proyectos").select("*").eq("id", lista_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Lista no encontrada")
    data = _parse_lista(proy.data)
    if not data:
        raise HTTPException(status_code=404, detail="El proyecto no es una lista de cotización")

    items = data.get("items", [])
    # Comparador de cada ítem en paralelo
    comparadores = await asyncio.gather(*[
        asyncio.to_thread(_comparador_de, sb, it["cotizacion_id"]) for it in items
    ])

    definitivos = data.get("definitivos", {})
    return {
        "id": proy.data["id"],
        "nombre": proy.data["nombre"],
        "created_at": proy.data.get("created_at"),
        "monto_total": proy.data.get("monto_total") or 0,
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
