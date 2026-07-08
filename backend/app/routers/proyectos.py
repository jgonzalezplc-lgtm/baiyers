import asyncio
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

router = APIRouter(prefix="/api/proyectos", tags=["proyectos"])

# Progreso en memoria (válido para dev single-server)
_progreso: dict[str, dict] = {}


class ProyectoRequest(BaseModel):
    user_id: str
    nombre: str
    cliente: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_inicio: Optional[str] = None


class ItemProyectoIn(BaseModel):
    item: str
    descripcion: Optional[str] = None
    cantidad: float = 1
    unidad: str = "unidad"
    categoria: Optional[str] = None
    orden: Optional[int] = None


class ProveedorItemRequest(BaseModel):
    proveedor_id: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    precio_unitario: float
    plazo_entrega_dias: Optional[int] = None


# ── LISTAR ────────────────────────────────────────────────────────────────────

@router.get("")
async def listar_proyectos(user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("proyectos").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data


# ── CREAR ─────────────────────────────────────────────────────────────────────

@router.post("")
async def crear_proyecto(req: ProyectoRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    row = {
        "user_id": req.user_id,
        "nombre": req.nombre,
        "cliente": req.cliente,
        "descripcion": req.descripcion,
        "fecha_inicio": req.fecha_inicio or date.today().isoformat(),
        "estado": "borrador",
        "monto_total": 0,
    }
    res = sb.table("proyectos").insert(row).execute()
    return res.data[0]


# ── DETALLE ───────────────────────────────────────────────────────────────────

@router.get("/{proyecto_id}")
async def detalle_proyecto(proyecto_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    proy = sb.table("proyectos").select("*").eq("id", proyecto_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    items = sb.table("items_proyecto").select("*, proveedores(nombre, email, score, categoria_score)").eq("proyecto_id", proyecto_id).order("orden").execute()
    return {**proy.data, "items": items.data}


# ── AGREGAR ÍTEMS ─────────────────────────────────────────────────────────────

@router.post("/{proyecto_id}/items")
async def agregar_items(proyecto_id: str, user_id: str, items: list[ItemProyectoIn]):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    # Verificar ownership
    proy = sb.table("proyectos").select("id").eq("id", proyecto_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    rows = [
        {
            "proyecto_id": proyecto_id,
            "item": it.item,
            "descripcion": it.descripcion,
            "cantidad": it.cantidad,
            "unidad": it.unidad,
            "categoria": it.categoria,
            "orden": it.orden or i,
            "estado": "pendiente",
        }
        for i, it in enumerate(items)
    ]
    res = sb.table("items_proyecto").insert(rows).execute()
    return res.data


# ── COTIZACIÓN MASIVA ─────────────────────────────────────────────────────────

_sem = asyncio.Semaphore(5)  # máx 5 ítems cotizando en paralelo


async def _cotizar_item(item: dict, user_id: str, proyecto_id: str) -> None:
    """Cotiza un ítem y guarda resultados en cotizaciones_proyecto."""
    from app.services.supabase import get_supabase
    from app.routers.buscar import _ml_query, _serp_query
    from app.config import settings
    import httpx

    sb = get_supabase()
    item_id = item["id"]
    nombre_item = item.get("item", "")

    async with _sem:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                tasks = [_ml_query(nombre_item, client)]
                if settings.serp_api_key:
                    tasks.append(_serp_query(f"{nombre_item} proveedor Chile", settings.serp_api_key, client, gl="cl", pais_default="CL"))
                listas = await asyncio.gather(*tasks, return_exceptions=True)

            resultados = []
            for lst in listas:
                if isinstance(lst, list):
                    resultados.extend(lst)

            # Guardar en cotizaciones_proyecto
            rows = []
            for r in resultados[:5]:
                if r.get("precio"):
                    rows.append({
                        "item_proyecto_id": item_id,
                        "proveedor_nombre": (r.get("proveedor") or r.get("titulo", ""))[:200],
                        "precio_unitario": r["precio"],
                        "plazo_entrega_dias": 7,
                        "url": r.get("url", ""),
                        "fuente": r.get("fuente", ""),
                    })

            if rows:
                sb.table("cotizaciones_proyecto").insert(rows).execute()
                mejor = min(rows, key=lambda x: x["precio_unitario"])
                precio_total = mejor["precio_unitario"] * item.get("cantidad", 1)
                sb.table("items_proyecto").update({
                    "precio_unitario": mejor["precio_unitario"],
                    "precio_total": precio_total,
                    "plazo_entrega_dias": mejor["plazo_entrega_dias"],
                    "estado": "cotizado",
                }).eq("id", item_id).execute()

        except Exception as e:
            print(f"[Proyectos] Error cotizando {nombre_item}: {e}")
        finally:
            _progreso[proyecto_id]["completados"] = _progreso[proyecto_id].get("completados", 0) + 1


async def _run_cotizacion(proyecto_id: str, user_id: str, items: list[dict]):
    """Corre la cotización masiva en background."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    _progreso[proyecto_id] = {"total": len(items), "completados": 0, "terminado": False}
    sb.table("proyectos").update({"estado": "cotizando"}).eq("id", proyecto_id).execute()

    await asyncio.gather(*[_cotizar_item(item, user_id, proyecto_id) for item in items])

    # Recalcular monto total
    items_res = sb.table("items_proyecto").select("precio_total").eq("proyecto_id", proyecto_id).execute()
    monto_total = sum(float(i.get("precio_total") or 0) for i in items_res.data)
    sb.table("proyectos").update({"estado": "borrador", "monto_total": monto_total}).eq("id", proyecto_id).execute()

    _progreso[proyecto_id]["terminado"] = True


@router.post("/{proyecto_id}/cotizar")
async def cotizar_proyecto(proyecto_id: str, user_id: str, background_tasks: BackgroundTasks):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    proy = sb.table("proyectos").select("id").eq("id", proyecto_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    items = sb.table("items_proyecto").select("*").eq("proyecto_id", proyecto_id).execute()
    if not items.data:
        raise HTTPException(status_code=400, detail="El proyecto no tiene ítems")

    background_tasks.add_task(_run_cotizacion, proyecto_id, user_id, items.data)
    return {"iniciado": True, "total_items": len(items.data)}


@router.get("/{proyecto_id}/cotizar/progreso")
async def progreso_cotizacion(proyecto_id: str):
    prog = _progreso.get(proyecto_id, {"total": 0, "completados": 0, "terminado": False})
    return prog


# ── ACTUALIZAR PROVEEDOR DE ÍTEM ──────────────────────────────────────────────

@router.put("/{proyecto_id}/items/{item_id}/proveedor")
async def actualizar_proveedor_item(proyecto_id: str, item_id: str, user_id: str, req: ProveedorItemRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    item_res = sb.table("items_proyecto").select("cantidad").eq("id", item_id).single().execute()
    if not item_res.data:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")

    cantidad = float(item_res.data.get("cantidad") or 1)
    precio_total = req.precio_unitario * cantidad

    sb.table("items_proyecto").update({
        "proveedor_seleccionado_id": req.proveedor_id,
        "precio_unitario": req.precio_unitario,
        "precio_total": precio_total,
        "plazo_entrega_dias": req.plazo_entrega_dias,
        "estado": "cotizado",
    }).eq("id", item_id).execute()

    # Recalcular monto total del proyecto
    items = sb.table("items_proyecto").select("precio_total").eq("proyecto_id", proyecto_id).execute()
    monto_total = sum(float(i.get("precio_total") or 0) for i in items.data)
    sb.table("proyectos").update({"monto_total": monto_total}).eq("id", proyecto_id).execute()

    return {"precio_total_item": precio_total, "monto_total_proyecto": monto_total}


# ── COTIZACIONES DE UN ÍTEM ────────────────────────────────────────────────────

@router.get("/{proyecto_id}/items/{item_id}/cotizaciones")
async def cotizaciones_item(proyecto_id: str, item_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("cotizaciones_proyecto").select("*").eq("item_proyecto_id", item_id).order("precio_unitario").execute()
    return res.data


# ── GANTT ─────────────────────────────────────────────────────────────────────

@router.get("/{proyecto_id}/gantt")
async def gantt(proyecto_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    proy = sb.table("proyectos").select("fecha_inicio, nombre").eq("id", proyecto_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    fecha_inicio_str = proy.data.get("fecha_inicio") or date.today().isoformat()
    fecha_inicio = date.fromisoformat(str(fecha_inicio_str))

    items = sb.table("items_proyecto").select("*, proveedores(nombre)").eq("proyecto_id", proyecto_id).order("orden").execute()

    gantt_items = []
    max_plazo = max((item.get("plazo_entrega_dias") or 14 for item in items.data), default=30)
    total_dias = max_plazo + 7

    for item in items.data:
        plazo = item.get("plazo_entrega_dias") or 14
        fi = fecha_inicio
        ff = fi + timedelta(days=plazo)
        gantt_items.append({
            "id": item["id"],
            "item": item["item"],
            "categoria": item.get("categoria"),
            "proveedor": (item.get("proveedores") or {}).get("nombre"),
            "precio_total": item.get("precio_total"),
            "fecha_inicio": fi.isoformat(),
            "fecha_fin": ff.isoformat(),
            "plazo_dias": plazo,
            "estado": item.get("estado", "pendiente"),
            "offset_dias": 0,
            "total_dias": total_dias,
        })

    return gantt_items


# ── GANTT DINÁMICO: 3 ESCENARIOS (Fase 5, Smart Procurement) ─────────────────

DIAS_COTIZACION = 2      # tiempo típico de cotización
DIAS_APROBACION = 1      # configurable por empresa a futuro


@router.get("/{proyecto_id}/gantt/escenarios")
async def gantt_escenarios(proyecto_id: str, user_id: str):
    """Calcula 3 escenarios de cronograma según qué cotización se elige por ítem:
    - minimo_costo:   proveedor más barato aunque sea lento
    - entrega_rapida: menor plazo aunque cueste más
    - equilibrio:     mejor ratio (precio normalizado + plazo normalizado)
    Cada ítem incluye todas sus cotizaciones para que el frontend pueda
    recalcular el Gantt al cambiar de proveedor interactivamente.
    """
    from app.services.supabase import get_supabase
    sb = get_supabase()

    proy = sb.table("proyectos").select("fecha_inicio, nombre").eq("id", proyecto_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    fecha_inicio = date.fromisoformat(str(proy.data.get("fecha_inicio") or date.today().isoformat()))
    items = sb.table("items_proyecto").select("*").eq("proyecto_id", proyecto_id).order("orden").execute()

    resultado_items = []
    for it in (items.data or []):
        cots = (
            sb.table("cotizaciones_proyecto").select(
                "id, proveedor_nombre, precio_unitario, plazo_entrega_dias"
            ).eq("item_proyecto_id", it["id"]).execute()
        ).data or []

        opciones = []
        for c in cots:
            precio = float(c.get("precio_unitario") or 0)
            plazo = int(c.get("plazo_entrega_dias") or 14)
            opciones.append({
                "cotizacion_id": c["id"],
                "proveedor": c.get("proveedor_nombre"),
                "precio_unitario": precio,
                "plazo_dias": plazo,
                "plazo_total_dias": DIAS_COTIZACION + DIAS_APROBACION + plazo,
            })

        if not opciones:
            # sin cotizaciones: ítem con plazo por defecto
            opciones = [{
                "cotizacion_id": None, "proveedor": None,
                "precio_unitario": float(it.get("precio_unitario") or 0),
                "plazo_dias": int(it.get("plazo_entrega_dias") or 14),
                "plazo_total_dias": DIAS_COTIZACION + DIAS_APROBACION + int(it.get("plazo_entrega_dias") or 14),
            }]

        precios = [o["precio_unitario"] for o in opciones if o["precio_unitario"] > 0]
        plazos = [o["plazo_dias"] for o in opciones]
        p_min, p_max = (min(precios), max(precios)) if precios else (0, 0)
        d_min, d_max = min(plazos), max(plazos)

        def norm(v, lo, hi):
            return 0.0 if hi == lo else (v - lo) / (hi - lo)

        seleccion = {
            "minimo_costo": min(opciones, key=lambda o: (o["precio_unitario"] if o["precio_unitario"] > 0 else float("inf"), o["plazo_dias"])),
            "entrega_rapida": min(opciones, key=lambda o: (o["plazo_dias"], o["precio_unitario"])),
            "equilibrio": min(opciones, key=lambda o: norm(o["precio_unitario"], p_min, p_max) * 0.5 + norm(o["plazo_dias"], d_min, d_max) * 0.5),
        }

        cantidad = float(it.get("cantidad") or 1)
        resultado_items.append({
            "item_id": it["id"],
            "item": it["item"],
            "cantidad": cantidad,
            "opciones": opciones,
            "seleccion_por_escenario": {
                k: {**v, "precio_total": v["precio_unitario"] * cantidad} for k, v in seleccion.items()
            },
        })

    escenarios = {}
    for esc in ("minimo_costo", "entrega_rapida", "equilibrio"):
        costo = sum(i["seleccion_por_escenario"][esc]["precio_total"] for i in resultado_items)
        dur = max((i["seleccion_por_escenario"][esc]["plazo_total_dias"] for i in resultado_items), default=0)
        escenarios[esc] = {
            "costo_total": costo,
            "duracion_dias": dur,
            "fecha_fin_estimada": (fecha_inicio + timedelta(days=dur)).isoformat(),
        }

    return {
        "proyecto": proy.data.get("nombre"),
        "fecha_inicio": fecha_inicio.isoformat(),
        "dias_cotizacion": DIAS_COTIZACION,
        "dias_aprobacion": DIAS_APROBACION,
        "escenarios": escenarios,
        "items": resultado_items,
    }


# ── LIQUIDEZ ──────────────────────────────────────────────────────────────────

@router.get("/{proyecto_id}/liquidez")
async def liquidez(proyecto_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    proy = sb.table("proyectos").select("fecha_inicio, monto_total").eq("id", proyecto_id).eq("user_id", user_id).single().execute()
    if not proy.data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    fecha_inicio_str = proy.data.get("fecha_inicio") or date.today().isoformat()
    fecha_inicio = date.fromisoformat(str(fecha_inicio_str))
    monto_total = float(proy.data.get("monto_total") or 0)

    items = sb.table("items_proyecto").select("precio_total, plazo_entrega_dias, item").eq("proyecto_id", proyecto_id).execute()

    semanas: dict[str, dict] = {}
    for item in items.data:
        plazo = item.get("plazo_entrega_dias") or 14
        fecha_pago = fecha_inicio + timedelta(days=plazo)
        lunes = fecha_pago - timedelta(days=fecha_pago.weekday())
        domingo = lunes + timedelta(days=6)
        key = lunes.isoformat()
        monto = float(item.get("precio_total") or 0)
        if key not in semanas:
            semanas[key] = {"semana": lunes.strftime("S%V"), "fecha_inicio": lunes.isoformat(), "fecha_fin": domingo.isoformat(), "monto": 0, "items": []}
        semanas[key]["monto"] += monto
        semanas[key]["items"].append(item.get("item", ""))

    # Nivel alerta
    umbral = monto_total * 0.4 if monto_total > 0 else float("inf")
    result = []
    for key in sorted(semanas.keys()):
        s = semanas[key]
        s["nivel"] = "rojo" if s["monto"] > umbral else ("amarillo" if s["monto"] > umbral * 0.6 else "verde")
        s["alerta"] = s["monto"] > umbral
        result.append(s)

    return result


# ── LISTAR ÍTEMS CON COTIZACIONES ─────────────────────────────────────────────

@router.get("/{proyecto_id}/items")
async def listar_items(proyecto_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    items = sb.table("items_proyecto").select("*").eq("proyecto_id", proyecto_id).order("orden").execute()
    result = []
    for it in items.data:
        cots = sb.table("cotizaciones_proyecto").select("*").eq("item_proyecto_id", it["id"]).order("precio_unitario").execute()
        result.append({**it, "cotizaciones": cots.data})
    return result


# ── SELECCIONAR COTIZACIÓN PARA ÍTEM ──────────────────────────────────────────

class SeleccionarRequest(BaseModel):
    cotizacion_id: str


@router.post("/{proyecto_id}/items/{item_id}/seleccionar")
async def seleccionar_cotizacion(proyecto_id: str, item_id: str, req: SeleccionarRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    cot = sb.table("cotizaciones_proyecto").select("*").eq("id", req.cotizacion_id).single().execute()
    if not cot.data:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    c = cot.data
    item_res = sb.table("items_proyecto").select("cantidad").eq("id", item_id).single().execute()
    cantidad = float((item_res.data or {}).get("cantidad") or 1)
    precio_total = c["precio_unitario"] * cantidad

    sb.table("items_proyecto").update({
        "precio_unitario": c["precio_unitario"],
        "precio_total": precio_total,
        "plazo_entrega_dias": c.get("plazo_entrega_dias"),
        "estado": "cotizado",
    }).eq("id", item_id).execute()

    # Recalcular monto total del proyecto
    all_items = sb.table("items_proyecto").select("precio_total").eq("proyecto_id", proyecto_id).execute()
    monto_total = sum(float(i.get("precio_total") or 0) for i in all_items.data)
    sb.table("proyectos").update({"monto_total": monto_total}).eq("id", proyecto_id).execute()

    return {"ok": True, "precio_total": precio_total, "monto_total_proyecto": monto_total}


# ── EMITIR OCS ────────────────────────────────────────────────────────────────

@router.post("/{proyecto_id}/emitir-ocs")
async def emitir_ocs(proyecto_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    items = sb.table("items_proyecto").select("*").eq("proyecto_id", proyecto_id).neq("precio_unitario", None).execute()
    if not items.data:
        raise HTTPException(status_code=400, detail="No hay ítems cotizados")

    proy = sb.table("proyectos").select("nombre, cliente").eq("id", proyecto_id).single().execute()
    proy_nombre = (proy.data or {}).get("nombre", "Proyecto")
    proy_cliente = (proy.data or {}).get("cliente")

    # Agrupar por proveedor
    por_proveedor: dict[str, list] = {}
    for it in items.data:
        prov_nombre = it.get("proveedor_nombre") or "Proveedor genérico"
        por_proveedor.setdefault(prov_nombre, []).append(it)

    ocs_creadas = []
    for prov_nombre, its in por_proveedor.items():
        monto = sum(float(i.get("precio_total") or 0) for i in its)
        descripcion = "; ".join(f"{i['item']} x{i['cantidad']}" for i in its)
        row = {
            "user_id": user_id,
            "proveedor_nombre": prov_nombre,
            "descripcion": f"OC Proyecto: {proy_nombre} — {descripcion}",
            "monto_total": monto,
            "estado": "borrador",
            "cliente": proy_cliente,
            "proyecto_id": proyecto_id,
        }
        res = sb.table("ordenes_compra").insert(row).execute()
        if res.data:
            ocs_creadas.append(res.data[0]["id"])

    return {"ocs_creadas": len(ocs_creadas), "ids": ocs_creadas}


# ── PARSEAR CUBICACIÓN EXCEL ──────────────────────────────────────────────────

from fastapi import File, UploadFile
import io as _io


@router.post("/parsear-cubicacion")
async def parsear_cubicacion(file: UploadFile = File(...)):
    """Usa Gemini para parsear un Excel de cubicación y extraer ítems."""
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=503, detail="pandas no instalado")

    from app.config import settings
    import json

    content = await file.read()
    filename = file.filename or ""

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(_io.BytesIO(content), dtype=str)
        else:
            df = pd.read_excel(_io.BytesIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error leyendo archivo: {e}")

    df = df.where(pd.notnull(df), None)
    filas = df.head(100).to_dict(orient="records")

    if settings.gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")

            prompt = f"""Analiza estas filas de una cubicación/lista de materiales de construcción o ingeniería.
Extrae cada ítem en JSON (SOLO array JSON sin markdown):
[{{"item": "nombre corto del material", "descripcion": "descripcion completa o null", "cantidad": number, "unidad": "m2/m3/kg/unidad/etc", "categoria": "categoria del material"}}]

Ignora filas vacías, títulos y subtotales. Solo materiales concretos con cantidad.

Filas:
{json.dumps(filas[:80], ensure_ascii=False)}"""

            resp = await asyncio.wait_for(model.generate_content_async(prompt), timeout=30.0)
            text = resp.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:].strip()
            items = json.loads(text)
            return {"items": items, "total": len(items)}
        except Exception as e:
            print(f"[Proyectos] Gemini parse error: {e}")

    # Fallback: primera columna = item, segunda = cantidad
    items = []
    for fila in filas:
        vals = [v for v in fila.values() if v is not None]
        if len(vals) >= 2:
            items.append({"item": str(vals[0]), "descripcion": None, "cantidad": 1, "unidad": "unidad", "categoria": None})

    return {"items": items, "total": len(items)}
