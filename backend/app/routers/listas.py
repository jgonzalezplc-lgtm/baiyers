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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context
from app.services.supabase import ejecutar_maybe_single

router = APIRouter(prefix="/api/listas", tags=["listas"])


def _ids_org(user_id: str) -> list[str]:
    """Wrapper local para import perezoso (Fase B del multi-usuario)."""
    from app.services.organizacion import ids_organizacion
    return ids_organizacion(user_id)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

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


def _fmt_clp(n: float) -> str:
    return f"${int(round(n)):,}".replace(",", ".")


class ItemListaIn(BaseModel):
    cotizacion_id: str
    nombre: str
    cantidad: float = 1
    unidad: str = "unidad"
    partida: Optional[str] = None


class CrearListaRequest(BaseModel):
    nombre: str
    items: list[ItemListaIn]


@router.post("")
async def crear_lista(req: CrearListaRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    data = {
        "tipo": MARCA_LISTA,
        "items": [{"cotizacion_id": it.cotizacion_id, "nombre": it.nombre, "cantidad": it.cantidad, "unidad": it.unidad, "partida": it.partida, "comparado": False} for it in req.items],
        "definitivos": {},
    }
    row = {
        "user_id": ctx.actor_user_id,
        "nombre": req.nombre,
        "descripcion": json.dumps(data, ensure_ascii=False),
        "estado": "borrador",
        "monto_total": 0,
    }
    res = sb.table("proyectos").insert(row).execute()
    return {"id": res.data[0]["id"], **data}


@router.get("")
async def listar_listas(ctx: AuthContext = Depends(get_auth_context)):
    """Todas las cotizaciones del usuario, unificadas: cada una es una "lista"
    de 1 o más ítems. Las cotizaciones sueltas (creadas antes de unificar el
    flujo, o vía integraciones externas) se muestran como listas de 1 ítem
    hasta que el usuario las abre, momento en que se envuelven de verdad
    (ver `_resolver_o_envolver`)."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    ids = ctx.user_ids_organizacion

    res = sb.table("proyectos").select("*").in_("user_id", ids).order("created_at", desc=True).execute()
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
                # Fase D — para el "creada por X" del frontend.
                "creado_por": p.get("user_id"),
            })

    # Cotizaciones sueltas (no envueltas todavía en ninguna lista)
    try:
        cots = sb.table("cotizaciones").select(
            "id, nombre_identificado, estado, created_at, user_id"
        ).in_("user_id", ids).order("created_at", desc=True).execute()
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
            "creado_por": c.get("user_id"),
        })

    listas.sort(key=lambda l: l.get("created_at") or "", reverse=True)
    return listas


def _envolver_cotizacion_suelta(sb, cotizacion_id: str, user_id: str) -> Optional[dict]:
    """Si `cotizacion_id` es una cotización suelta (no una lista), la envuelve
    en una lista de 1 ítem (fila nueva en `proyectos`) y devuelve esa fila.
    Devuelve None si no existe una cotización con ese id para el usuario."""
    cot = sb.table("cotizaciones").select("id, nombre_identificado").eq("id", cotizacion_id).in_("user_id", _ids_org(user_id)).limit(1).execute()
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
    proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", _ids_org(user_id)).limit(1).execute()
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


def _resultados_visibles(item: dict, resultados: list[dict]) -> list[dict]:
    """No revela búsquedas web históricas hasta que el usuario las compare.

    Los resultados `manual` son RFQs a proveedores privados o sugeridos y sí
    pertenecen al camino directo, aun cuando el ítem no haya pasado por web.
    """
    if item.get("comparado"):
        return resultados
    return [r for r in resultados if (r.get("fuente") or "").lower() == "manual"]


@router.get("/{lista_id}")
async def detalle_lista(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    user_id = ctx.actor_user_id

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
    comparadores = [
        _resultados_visibles(item, comparadores[i])
        for i, item in enumerate(items)
    ]

    definitivos = data.get("definitivos", {})
    matriz_privada = _matriz_proveedores_confianza(
        sb, user_id, items, data.get("proveedores_confianza") or {}
    )
    privados_por_item: dict[str, list[dict]] = {it["cotizacion_id"]: [] for it in items}
    for proveedor in matriz_privada["proveedores"]:
        for candidato in proveedor["items"]:
            privados_por_item[candidato["cotizacion_id"]].append({
                "id": proveedor["proveedor_id"], "nombre": proveedor["nombre"],
                "email": (proveedor.get("contacto") or {}).get("email"),
                "sitio_web": None, "telefono": None, "origen": "proveedor",
                "origen_label": "Proveedor de tu empresa", "match_label": "Match por historial",
            })
    from app.services.proveedores_sugeridos import sugeridos_para_categoria
    categorias_por_item = {it["cotizacion_id"]: it.get("categoria") for it in matriz_privada["items"]}
    selecciones_guardadas = {
        (s.get("cotizacion_id"), s.get("clave")): s
        for s in data.get("selecciones_proveedores", [])
    }
    selecciones_por_item: dict[str, list[dict]] = {}
    for seleccion in data.get("selecciones_proveedores", []):
        selecciones_por_item.setdefault(seleccion.get("cotizacion_id"), []).append(seleccion)
    for i, item in enumerate(items):
        for comparado in comparadores[i]:
            seleccion = next((s for s in selecciones_por_item.get(item["cotizacion_id"], []) if
                (s.get("email") and s["email"].lower() == (comparado.get("contacto") or "").lower()) or
                (s.get("nombre") and s["nombre"] == comparado.get("proveedor"))), None)
            comparado["origen"] = seleccion.get("origen") if seleccion else ("proveedor" if comparado.get("fuente") == "manual" else "buscado_web")
    definitivos_salida = {}
    for cid, definitivo in definitivos.items():
        definitivo_salida = {**definitivo}
        seleccion = next((s for s in selecciones_por_item.get(cid, []) if s.get("nombre") == definitivo.get("proveedor")), None)
        definitivo_salida["origen"] = seleccion.get("origen") if seleccion else ("proveedor" if definitivo.get("fuente") == "manual" else "buscado_web")
        definitivos_salida[cid] = definitivo_salida
    result = {
        "id": proy_data["id"],
        "nombre": proy_data["nombre"],
        "created_at": proy_data.get("created_at"),
        "monto_total": proy_data.get("monto_total") or 0,
        # Fase D — para el "creada por X" del frontend.
        "creado_por": proy_data.get("user_id"),
        "items": [
            {
                **it,
                "cantidad": float(it.get("cantidad") or 1),
                "comparados": comparadores[i],
                "definitivo": definitivos_salida.get(it["cotizacion_id"]),
                "proveedores_recomendados": _recomendaciones_item(
                    it, privados_por_item.get(it["cotizacion_id"], []),
                    sugeridos_para_categoria(
                        categorias_por_item.get(it["cotizacion_id"]),
                        it.get("nombre"),
                    ),
                    selecciones_guardadas,
                ),
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


def _recomendaciones_item(item: dict, privados: list[dict], sugeridos: list[dict], guardadas: dict) -> list[dict]:
    """Orden solicitado: directorio privado primero, banco Baiyer después."""
    cid = item["cotizacion_id"]
    emails_privados = {(p.get("email") or "").lower() for p in privados if p.get("email")}
    salida = privados + [p for p in sugeridos if p["email"].lower() not in emails_privados]
    for proveedor in salida:
        clave = proveedor["id"] if proveedor["origen"] == "proveedor" else proveedor["email"].lower()
        proveedor["seleccionado"] = (cid, clave) in guardadas
    return salida


class MarcarComparadoRequest(BaseModel):
    cotizacion_id: str


class SeleccionProveedorConfianza(BaseModel):
    proveedor_id: str
    contacto_id: Optional[str] = None
    cotizacion_ids: list[str]


class GuardarMatrizConfianzaRequest(BaseModel):
    selecciones: list[SeleccionProveedorConfianza]


class SeleccionarProveedorItemRequest(BaseModel):
    cotizacion_id: str
    origen: str
    proveedor_id: Optional[str] = None
    email: Optional[str] = None
    seleccionado: bool = True


@router.post("/{lista_id}/seleccionar-proveedor")
async def seleccionar_proveedor_item(lista_id: str, req: SeleccionarProveedorItemRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Selecciona un proveedor privado o del banco global para un ítem.

    Los sugeridos sólo pasan al directorio privado al ser elegidos; así el banco
    global no contamina los datos ni el aprendizaje propio del usuario.
    """
    from app.services.supabase import get_supabase
    from app.services.proveedores_matching import resolver_o_crear_contacto, resolver_o_crear_proveedor
    from app.services.proveedores_sugeridos import buscar_sugerido
    sb = get_supabase()
    async with _lock_de(lista_id):
        proy = ejecutar_maybe_single(sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
        data = _parse_lista(proy or {})
        if not data or req.cotizacion_id not in {it["cotizacion_id"] for it in data.get("items", [])}:
            raise HTTPException(status_code=404, detail="Lista o ítem no encontrado")

        proveedor_id = req.proveedor_id
        contacto_id = None
        clave = proveedor_id
        nombre = None
        email = req.email.lower().strip() if req.email else None
        if req.origen == "sugerido":
            banco = buscar_sugerido(email or "")
            if not banco:
                raise HTTPException(status_code=400, detail="Proveedor sugerido inválido")
            nombre = banco["company_name"]
            clave = banco["primary_email"].lower()
            if req.seleccionado:
                proveedor_id = resolver_o_crear_proveedor(sb, ctx.actor_user_id, nombre, banco["primary_email"])
                contacto_id = resolver_o_crear_contacto(
                    # `proveedor_contactos.origen` sólo admite manual/excel/gmail_agent.
                    # El origen de negocio "sugerido" queda en la selección de la lista.
                    sb, ctx.actor_user_id, proveedor_id, banco["primary_email"], origen="manual"
                )
                sb.table("proveedores").update({
                    "sitio_web": banco.get("website"), "telefono": banco.get("phone")
                }).eq("id", proveedor_id).execute()
        elif proveedor_id:
            proveedor = ejecutar_maybe_single(sb.table("proveedores").select("id,nombre,email").eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
            if not proveedor:
                raise HTTPException(status_code=400, detail="Proveedor privado inválido")
            nombre, email = proveedor.get("nombre"), proveedor.get("email")
            contactos = sb.table("proveedor_contactos").select("id,email").eq("proveedor_id", proveedor_id).eq("es_principal", True).limit(1).execute().data or []
            if contactos:
                contacto_id, email = contactos[0]["id"], contactos[0]["email"]
        else:
            raise HTTPException(status_code=400, detail="Selección inválida")

        selecciones = data.setdefault("selecciones_proveedores", [])
        if not selecciones:
            for previa in (data.get("proveedores_confianza") or {}).get("selecciones", []):
                for cid in previa.get("cotizacion_ids", []):
                    selecciones.append({
                        "cotizacion_id": cid, "clave": previa.get("proveedor_id"),
                        "proveedor_id": previa.get("proveedor_id"),
                        "contacto_id": previa.get("contacto_id"), "origen": "proveedor",
                    })
        selecciones[:] = [s for s in selecciones if not (s.get("cotizacion_id") == req.cotizacion_id and s.get("clave") == clave)]
        if req.seleccionado:
            selecciones.append({
                "cotizacion_id": req.cotizacion_id, "clave": clave, "proveedor_id": proveedor_id,
                "contacto_id": contacto_id, "nombre": nombre, "email": email, "origen": req.origen,
            })

        # Sincroniza con el borrador RFQ ya existente para reutilizar todo el
        # flujo de correo y respuestas por proveedor.
        agrupadas: dict[str, dict] = {}
        for s in selecciones:
            pid = s.get("proveedor_id")
            if not pid:
                continue
            fila = agrupadas.setdefault(pid, {"proveedor_id": pid, "contacto_id": s.get("contacto_id"), "cotizacion_ids": []})
            fila["cotizacion_ids"].append(s["cotizacion_id"])
        data["proveedores_confianza"] = {"revisado": True, "selecciones": list(agrupadas.values())}
        _guardar_lista(sb, lista_id, data)
    return {"success": True, "seleccionado": req.seleccionado}


def _matriz_proveedores_confianza(sb, user_id: str, items: list[dict], borrador: dict) -> dict:
    """Construye recomendaciones explicables usando sólo el directorio privado
    y supplier_capabilities. No escribe evidencia: esta pantalla es un borrador
    editable; la confirmación real ocurre al enviar la RFQ (Fase 5)."""
    cot_ids = [it["cotizacion_id"] for it in items]
    cotizaciones = {
        c["id"]: c for c in (
            sb.table("cotizaciones").select("id,nombre_identificado,categoria")
            .in_("id", cot_ids).execute().data or []
        )
    } if cot_ids else {}

    proveedores = (
        sb.table("proveedores")
        .select("id,nombre,email,score,categoria_score,bloqueado,preferido")
        .in_("user_id", _ids_org(user_id)).eq("bloqueado", False).execute().data or []
    )
    proveedor_ids = [p["id"] for p in proveedores]
    capacidades = (
        sb.table("supplier_capabilities").select(
            "proveedor_id,categoria,confianza,estado,evidencia_positiva,cotizaciones_validas,compras"
        ).in_("user_id", _ids_org(user_id)).in_("proveedor_id", proveedor_ids)
        .neq("estado", "rejected").execute().data or []
    ) if proveedor_ids else []
    contactos = (
        sb.table("proveedor_contactos").select("id,proveedor_id,nombre,email,cargo,es_principal")
        .in_("user_id", _ids_org(user_id)).in_("proveedor_id", proveedor_ids).execute().data or []
    ) if proveedor_ids else []

    contacto_por_proveedor: dict[str, dict] = {}
    for contacto in sorted(contactos, key=lambda c: not c.get("es_principal")):
        contacto_por_proveedor.setdefault(contacto["proveedor_id"], contacto)

    caps_por_clave = {(c["proveedor_id"], c["categoria"]): c for c in capacidades}
    guardadas = {
        (s.get("proveedor_id"), cid): s.get("contacto_id")
        for s in borrador.get("selecciones", []) for cid in s.get("cotizacion_ids", [])
    }
    matriz: dict[str, dict] = {}
    candidatos_por_item: dict[str, list[dict]] = {cid: [] for cid in cot_ids}

    for item in items:
        cid = item["cotizacion_id"]
        cot = cotizaciones.get(cid, {})
        categoria = cot.get("categoria") or item.get("categoria") or "otro"
        for proveedor in proveedores:
            cap = caps_por_clave.get((proveedor["id"], categoria))
            if not cap:
                continue
            confianza = float(cap.get("confianza") or 0)
            score_general = float(proveedor.get("score") or 0)
            ranking = confianza + (0.08 if proveedor.get("preferido") else 0) + min(score_general, 100) / 1000
            razones = []
            if cap.get("compras"):
                razones.append(f"{cap['compras']} compra(s) completada(s)")
            if cap.get("cotizaciones_validas"):
                razones.append(f"{cap['cotizaciones_validas']} cotización(es) válida(s)")
            if not razones and cap.get("evidencia_positiva"):
                razones.append(f"{cap['evidencia_positiva']} señal(es) positiva(s)")
            if proveedor.get("preferido"):
                razones.append("marcado como preferido")
            explicacion = "Recomendado por " + ", ".join(razones) + "." if razones else "Capacidad inferida con confianza baja."
            candidato = {
                "cotizacion_id": cid,
                "nombre": item.get("nombre") or cot.get("nombre_identificado") or "Ítem",
                "cantidad": float(item.get("cantidad") or 1),
                "unidad": item.get("unidad") or "un",
                "categoria": categoria,
                "confianza": confianza,
                "estado": cap.get("estado"),
                "ranking": round(ranking, 4),
                "explicacion": explicacion,
                "seleccionado": (proveedor["id"], cid) in guardadas,
            }
            candidatos_por_item[cid].append({**candidato, "proveedor_id": proveedor["id"]})
            entrada = matriz.setdefault(proveedor["id"], {
                "proveedor_id": proveedor["id"], "nombre": proveedor.get("nombre"),
                "score": proveedor.get("score") or 0, "preferido": bool(proveedor.get("preferido")),
                "contacto": contacto_por_proveedor.get(proveedor["id"]) or ({"id": None, "email": proveedor.get("email"), "nombre": None, "cargo": None} if proveedor.get("email") else None),
                "items": [],
            })
            entrada["items"].append(candidato)

    # Sin borrador previo, preseleccionar hasta 3 recomendaciones por ítem.
    if not borrador.get("revisado"):
        recomendados = set()
        for cid, candidatos in candidatos_por_item.items():
            for c in sorted(candidatos, key=lambda x: x["ranking"], reverse=True)[:3]:
                recomendados.add((c["proveedor_id"], cid))
        for pid, proveedor in matriz.items():
            for item in proveedor["items"]:
                item["seleccionado"] = (pid, item["cotizacion_id"]) in recomendados

    proveedores_matriz = sorted(
        matriz.values(),
        key=lambda p: max((it["ranking"] for it in p["items"]), default=0), reverse=True,
    )
    items_salida = []
    for item in items:
        cid = item["cotizacion_id"]
        cot = cotizaciones.get(cid, {})
        items_salida.append({
            "cotizacion_id": cid, "nombre": item.get("nombre") or cot.get("nombre_identificado") or "Ítem",
            "cantidad": float(item.get("cantidad") or 1), "unidad": item.get("unidad") or "un",
            "categoria": cot.get("categoria") or item.get("categoria") or "otro",
            "n_candidatos": len(candidatos_por_item[cid]),
        })
    return {"items": items_salida, "proveedores": proveedores_matriz, "revisado": bool(borrador.get("revisado"))}


@router.get("/{lista_id}/proveedores-confianza")
async def matriz_proveedores_confianza(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    proy = ejecutar_maybe_single(sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    data = _parse_lista(proy or {})
    if not data:
        raise HTTPException(status_code=404, detail="Lista no encontrada")
    return _matriz_proveedores_confianza(sb, ctx.actor_user_id, data.get("items", []), data.get("proveedores_confianza") or {})


@router.put("/{lista_id}/proveedores-confianza")
async def guardar_matriz_proveedores_confianza(lista_id: str, req: GuardarMatrizConfianzaRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    async with _lock_de(lista_id):
        proy = ejecutar_maybe_single(sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
        data = _parse_lista(proy or {})
        if not data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        ids_validos = {it["cotizacion_id"] for it in data.get("items", [])}
        proveedores_validos = {
            p["id"] for p in (sb.table("proveedores").select("id").in_("user_id", ctx.user_ids_organizacion).eq("bloqueado", False).execute().data or [])
        }
        contactos_validos = {
            (c["id"], c["proveedor_id"])
            for c in (sb.table("proveedor_contactos").select("id,proveedor_id").in_("user_id", ctx.user_ids_organizacion).execute().data or [])
        }
        selecciones = []
        for s in req.selecciones:
            if s.proveedor_id not in proveedores_validos:
                continue
            cotizaciones = sorted(set(s.cotizacion_ids) & ids_validos)
            if cotizaciones:
                contacto_id = s.contacto_id if (s.contacto_id, s.proveedor_id) in contactos_validos else None
                selecciones.append({"proveedor_id": s.proveedor_id, "contacto_id": contacto_id, "cotizacion_ids": cotizaciones})
        data["proveedores_confianza"] = {"revisado": True, "selecciones": selecciones}
        _guardar_lista(sb, lista_id, data)
    return {"success": True, "selecciones": selecciones}


@router.get("/{lista_id}/busqueda-complementaria")
async def estado_busqueda_complementaria(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Separa ítems sin cobertura de los ya asignados/cotizados. No dispara
    búsquedas: los cubiertos sólo se buscan si el usuario lo pide."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    proy = ejecutar_maybe_single(sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    data = _parse_lista(proy or {})
    if not data:
        raise HTTPException(status_code=404, detail="Lista no encontrada")
    items = data.get("items", [])
    cot_ids = [it["cotizacion_id"] for it in items]
    cots = {c["id"]: c for c in (sb.table("cotizaciones").select("id,nombre_identificado,categoria").in_("id", cot_ids).execute().data or [])} if cot_ids else {}
    selecciones = (data.get("proveedores_confianza") or {}).get("selecciones") or []
    proveedor_ids = [s["proveedor_id"] for s in selecciones]
    proveedores = {p["id"]: p["nombre"] for p in (sb.table("proveedores").select("id,nombre").in_("id", proveedor_ids).execute().data or [])} if proveedor_ids else {}
    cobertura: dict[str, list[dict]] = {cid: [] for cid in cot_ids}
    for s in selecciones:
        for cid in s.get("cotizacion_ids", []):
            if cid in cobertura:
                cobertura[cid].append({"proveedor_id": s["proveedor_id"], "nombre": proveedores.get(s["proveedor_id"], "Proveedor")})
    enviados: set[str] = set()
    try:
        batches = sb.table("rfq_batches").select("id").eq("lista_proyecto_id", lista_id).in_("user_id", ctx.user_ids_organizacion).eq("estado", "sent").execute().data or []
        if batches:
            enviados = {x["cotizacion_id"] for x in (sb.table("rfq_batch_items").select("cotizacion_id").in_("rfq_batch_id", [b["id"] for b in batches]).execute().data or [])}
    except Exception:
        pass
    salida = []
    for it in items:
        cid = it["cotizacion_id"]
        cot = cots.get(cid, {})
        salida.append({
            "cotizacion_id": cid, "nombre": it.get("nombre") or cot.get("nombre_identificado") or "Ítem",
            "cantidad": float(it.get("cantidad") or 1), "unidad": it.get("unidad") or "un",
            "categoria": cot.get("categoria") or it.get("categoria") or "otro",
            "proveedores": cobertura[cid], "n_proveedores": len(cobertura[cid]),
            "rfq_enviada": cid in enviados,
        })
    return {
        "lista_id": lista_id,
        "requieren_proveedores": [it for it in salida if it["n_proveedores"] == 0],
        "ya_cubiertos": [it for it in salida if it["n_proveedores"] > 0],
    }


@router.post("/{lista_id}/comparado")
async def marcar_comparado(lista_id: str, req: MarcarComparadoRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
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
async def elegir_definitivo(lista_id: str, req: DefinitivoRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        definitivos = data.setdefault("definitivos", {})
        if req.quitar:
            definitivos.pop(req.cotizacion_id, None)
        else:
            item_lista = next((it for it in data.get("items", []) if it.get("cotizacion_id") == req.cotizacion_id), {})
            definitivos[req.cotizacion_id] = {
                "resultado_id": req.resultado_id,
                "proveedor": req.proveedor,
                "precio": req.precio,
                "moneda": req.moneda,
                "url": req.url,
                "fuente": req.fuente,
                "precio_clp": req.precio_clp if req.precio_clp is not None else req.precio,
                # Contrato histórico: el precio de una oferta siempre es unitario
                # respecto de la unidad de medida solicitada, nunca el total de línea.
                "precio_unitario": req.precio,
                "unidad_medida": item_lista.get("unidad") or "unidad",
                # Fase D — "hecho por X": queda registrado quién de la
                # organización marcó este proveedor como definitivo, para
                # mostrarlo en el comparador y en el resumen de la lista.
                "seleccionado_por": ctx.actor_user_id,
                "seleccionado_at": _now_iso(),
            }

        monto_total = _monto_total(data)
        _guardar_lista(sb, lista_id, data)
        sb.table("proyectos").update({"monto_total": monto_total}).eq("id", lista_id).execute()

    if not req.quitar and req.resultado_id:
        try:
            from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
            registrar_evento_para_resultado(ctx.actor_user_id, req.resultado_id, "supplier_selected", {"lista_id": lista_id})
        except Exception as e:
            print(f"[Listas] evidencia definitivo: {e}")

    return {"success": True, "definitivos": len(definitivos), "monto_total": monto_total}


class CantidadRequest(BaseModel):
    cotizacion_id: str
    cantidad: float


@router.post("/{lista_id}/cantidad")
async def actualizar_cantidad(lista_id: str, req: CantidadRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Actualiza la cantidad a comprar de un ítem de la lista."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.cantidad <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
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
    aprobador_email: Optional[str] = None
    justificaciones: dict = {}  # {cotizacion_id: "texto justificación"}
    nombre_solicitante: str = ""
    empresa: str = ""


async def _crear_y_enviar_solicitudes(sb, user_id: str, lista_id: str, lista_nombre: str, resumen: dict, resolucion: dict, organizacion_id: Optional[str] = None) -> list[dict]:
    """Crea una `approval_requests` por cada responsable a notificar (Fase 4
    del Workflow Builder) y le envía su propio correo con magic link. Se usa
    tanto en la ronda inicial como cuando el workflow avanza a un tramo
    siguiente (ej: aprobación de finanzas tras la del jefe directo)."""
    from app.routers.aprobaciones import _crear_solicitud_aprobacion
    from app.routers.aprobaciones import SolicitudRequest
    from app.services.gmail_service import get_gmail_service, send_email
    from app.services.mail_template_service import render, registrar_envio

    # user_integrations es personal — cada usuario conecta su propio Gmail.
    integ = sb.table("user_integrations").select("*").eq("user_id", user_id).eq("provider", "gmail").limit(1).execute()
    integration = (integ.data or [None])[0]
    if not integration:
        raise HTTPException(status_code=400, detail="Gmail no conectado. Conéctalo en Configuración para poder enviar la solicitud de autorización.")

    item_lines = "\n".join(
        f"- {it['nombre']} ×{it.get('cantidad', 1)}: {it.get('proveedor') or '—'}"
        f" ({_fmt_clp(it['precio_clp'] * it.get('cantidad', 1)) if it.get('precio_clp') is not None else '—'})"
        + (f", {it['justificacion']}" if it.get("justificacion") else "")
        for it in resumen.get("items", [])
    )

    enviadas = []
    for responsable in resolucion["responsables_a_notificar"]:
        sol = _crear_solicitud_aprobacion(user_id, SolicitudRequest(
            referencia=f"lista:{lista_id}",
            resumen=resumen,
            aprobador_email=responsable["email"],
            workflow_instance_id=resolucion["workflow_instance_id"],
            workflow_nodo_id=resolucion["nodo_id"],
            responsable_id=responsable["id"],
        ))
        try:
            service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
            if creds.token != integration["access_token"]:
                sb.table("user_integrations").update({
                    "access_token": creds.token,
                    "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
                }).eq("user_id", user_id).eq("provider", "gmail").execute()
            renderizado = render("approval_requested", {
                "nombre_autorizador": responsable["nombre"],
                "nombre_solicitante": resumen.get("solicitante") or "Un usuario",
                "organizacion_nombre": resumen.get("empresa") or "la empresa",
                "lista_nombre": lista_nombre,
                "nodo_nombre": resolucion["nodo_nombre"],
                "monto": _fmt_clp(resumen.get("monto_total", 0)),
                "item_lines": item_lines,
                "link_autorizacion": sol["magic_link"],
                "expira_at": sol["expira_at"][:10],
            }, organizacion_id=organizacion_id)
            asunto, cuerpo = renderizado["subject"], renderizado["body"]
            send_email(service, responsable["email"], asunto, cuerpo, integration["email"])
            if organizacion_id:
                try:
                    registrar_envio(
                        organizacion_id, "approval_requested", responsable["email"],
                        f"approval_requested:{sol['id']}", estado="enviado",
                        responsable_id=responsable.get("id"),
                    )
                except Exception as e:
                    print(f"[listas] registrar_envio falló (correo ya enviado, solo auditoría): {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"No se pudo enviar el correo de autorización a {responsable['email']}: {e}")
        enviadas.append({"responsable_id": responsable["id"], "nombre": responsable["nombre"], "email": responsable["email"], "token": sol["token"]})
    return enviadas


@router.post("/{lista_id}/solicitar-aprobacion")
async def solicitar_aprobacion(lista_id: str, req: SolicitarAprobacionRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    from app.services.workflow_execution import iniciar_autorizacion_workflow
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
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

        # Fase 4 del Workflow Builder: si hay un ciclo de compras activo con
        # responsables reales asignados al rol autorizador, el motor decide
        # a quién(es) escribirle — puede ser más de una persona (paralelo o
        # secuencial) y puede depender del monto (tramos). Si no hay ciclo
        # activo o nadie fue asignado todavía, cae íntegro al flujo legado de
        # un solo `aprobador_email` escrito a mano.
        resolucion = iniciar_autorizacion_workflow(ctx.actor_user_id, lista_id, monto_total)

        if resolucion:
            enviadas = await _crear_y_enviar_solicitudes(sb, ctx.actor_user_id, lista_id, proy.data["nombre"], resumen, resolucion, organizacion_id=ctx.organization_id)
            data["aprobacion"] = {
                "estado": "pendiente",
                "modo": "workflow",
                "workflow_id": resolucion["workflow_id"],
                "workflow_instance_id": resolucion["workflow_instance_id"],
                "nodo_actual_id": resolucion["nodo_id"],
                "nodo_actual_nombre": resolucion["nodo_nombre"],
                "aprobadores_pendientes": [
                    {"responsable_id": r["id"], "nombre": r["nombre"], "email": r["email"]}
                    for r in resolucion["responsables_a_notificar"]
                ],
            }
            _guardar_lista(sb, lista_id, data)
            return {
                "success": True,
                "modo": "workflow",
                "nodo_actual_nombre": resolucion["nodo_nombre"],
                "notificados": enviadas,
            }

        if not req.aprobador_email or not req.aprobador_email.strip():
            raise HTTPException(status_code=400, detail="No hay un ciclo de autorizaciones configurado con responsables asignados: ingresa el email del autorizador.")

        from app.routers.aprobaciones import _crear_solicitud_aprobacion
        from app.routers.aprobaciones import SolicitudRequest
        sol = _crear_solicitud_aprobacion(ctx.actor_user_id, SolicitudRequest(
            referencia=f"lista:{lista_id}",
            resumen=resumen,
            aprobador_email=req.aprobador_email,
        ))

        # El correo de autorización sale por la cuenta Gmail ya conectada del
        # usuario (misma integración que se usa para cotizar a proveedores),
        # nunca abriendo el cliente de correo local — el autorizador es
        # interno, no un proveedor, así que no se engancha al agente de
        # seguimiento de respuestas (eso es solo para precios de proveedor).
        from app.services.gmail_service import get_gmail_service, send_email
        from app.services.mail_template_service import render, registrar_envio
        # user_integrations es personal — cada usuario conecta su propio Gmail.
        integ = sb.table("user_integrations").select("*").eq("user_id", ctx.actor_user_id).eq("provider", "gmail").limit(1).execute()
        integration = (integ.data or [None])[0]
        if not integration:
            raise HTTPException(status_code=400, detail="Gmail no conectado. Conéctalo en Configuración para poder enviar la solicitud de autorización.")

        try:
            service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
            if creds.token != integration["access_token"]:
                sb.table("user_integrations").update({
                    "access_token": creds.token,
                    "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
                }).eq("user_id", ctx.actor_user_id).eq("provider", "gmail").execute()

            item_lines = "\n".join(
                f"- {it['nombre']} ×{it.get('cantidad', 1)}: {it.get('proveedor') or '—'}"
                f" ({_fmt_clp(it['precio_clp'] * it.get('cantidad', 1)) if it.get('precio_clp') is not None else '—'})"
                + (f", {it['justificacion']}" if it.get("justificacion") else "")
                for it in resumen_items
            )
            # Flujo legado: no hay un responsable con nombre real asignado
            # (solo un email escrito a mano), así que se usa el email como
            # identificador del saludo — más cercano que un "Hola," genérico.
            renderizado = render("approval_requested", {
                "nombre_autorizador": req.aprobador_email,
                "nombre_solicitante": req.nombre_solicitante or "Un usuario",
                "organizacion_nombre": req.empresa or "la empresa",
                "lista_nombre": proy.data["nombre"],
                "nodo_nombre": "autorizador",
                "monto": _fmt_clp(monto_total),
                "item_lines": item_lines,
                "link_autorizacion": sol["magic_link"],
                "expira_at": sol["expira_at"][:10],
            }, organizacion_id=ctx.organization_id)
            asunto, cuerpo = renderizado["subject"], renderizado["body"]
            send_email(service, req.aprobador_email, asunto, cuerpo, integration["email"])
            try:
                registrar_envio(
                    ctx.organization_id, "approval_requested", req.aprobador_email,
                    f"approval_requested:{sol['id']}", estado="enviado",
                )
            except Exception as e:
                print(f"[listas] registrar_envio falló (correo ya enviado, solo auditoría): {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"No se pudo enviar el correo de autorización: {e}")

        data["aprobacion"] = {
            "estado": "pendiente",
            "aprobador_email": req.aprobador_email,
            "token": sol["token"],
            "approval_request_id": sol["id"],
        }
        _guardar_lista(sb, lista_id, data)

    return {
        "success": True,
        "magic_link": sol["magic_link"],
        "token": sol["token"],
        "expira_at": sol["expira_at"],
    }


class ReenviarAprobacionRequest(BaseModel):
    pass


@router.post("/{lista_id}/reenviar-aprobacion")
async def reenviar_aprobacion(lista_id: str, req: ReenviarAprobacionRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Resetea una lista rechazada para poder re-solicitar aprobación."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
        if not proy.data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        data = _parse_lista(proy.data)
        if not data:
            raise HTTPException(status_code=404, detail="No es una lista de cotización")

        aprobacion = data.get("aprobacion", {})
        if aprobacion.get("estado") not in ("rechazado", "aprobado_con_observaciones", None):
            raise HTTPException(status_code=400, detail="Solo se puede re-solicitar una lista rechazada u observada")

        data.pop("aprobacion", None)
        _guardar_lista(sb, lista_id, data)

    return {"success": True}


# ─── Compra: OC enviada o compra online ─────────────────────────────────────
# Cuando la lista está autorizada, cada ítem puede:
#   - Enviarse por OC (definitivo tiene email de proveedor)
#   - Comprarse online (solo hay link, no email); se chequea a mano o vía boleta
# El estado por ítem vive en data["compras"][cotizacion_id].

class CompraRequest(BaseModel):
    cotizacion_id: str
    estado: str  # "enviada_oc" | "comprado" | "pendiente"
    oc_id: Optional[str] = None
    numero_oc: Optional[str] = None
    precio_real: Optional[float] = None  # precio efectivamente pagado (CLP)
    boleta_url: Optional[str] = None
    notas: Optional[str] = None


@router.post("/{lista_id}/compra")
async def actualizar_compra(lista_id: str, req: CompraRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Registra el avance de la compra de un ítem: OC enviada, comprado
    online, o desmarcar (volver a pendiente)."""
    from datetime import datetime, timezone
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.estado not in ("enviada_oc", "comprado", "pendiente"):
        raise HTTPException(status_code=400, detail="estado inválido")

    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
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

    if req.estado == "comprado":
        definitivo = (data.get("definitivos") or {}).get(req.cotizacion_id) or {}
        if definitivo.get("resultado_id"):
            try:
                from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
                registrar_evento_para_resultado(
                    ctx.actor_user_id, definitivo["resultado_id"], "purchase_completed",
                    {"lista_id": lista_id, "precio_real": req.precio_real, "origen": "lista_compra"},
                )
            except Exception as e:
                print(f"[Listas] evidencia compra: {e}")
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
    imagen_base64: str
    imagen_mime: str = "image/jpeg"
    auto_marcar: bool = True  # marcar directo los ítems que la IA reconoció


@router.post("/{lista_id}/boleta-scan")
async def escanear_boleta(lista_id: str, req: BoletaScanRequest, ctx: AuthContext = Depends(get_auth_context)):
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
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
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
        fname = f"{ctx.actor_user_id}/{lista_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.{ext}"
        sb.storage.from_("boletas").upload(fname, base64.b64decode(req.imagen_base64), {
            "content-type": req.imagen_mime, "upsert": "true",
        })
        boleta_url = sb.storage.from_("boletas").get_public_url(fname)
    except Exception as e:
        print(f"[boleta-scan] no se pudo subir imagen: {e}")

    # 4. Matchear con los ítems de la lista y marcar como comprados
    matches: list[dict] = []
    async with _lock_de(lista_id):
        proy = sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).single().execute()
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

    if req.auto_marcar:
        for match in matches:
            cid = match.get("cotizacion_id")
            definitivo = (data.get("definitivos") or {}).get(cid) if cid else None
            if definitivo and definitivo.get("resultado_id"):
                try:
                    from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
                    registrar_evento_para_resultado(
                        ctx.actor_user_id, definitivo["resultado_id"], "purchase_completed",
                        {"lista_id": lista_id, "precio_real": match.get("precio"), "origen": "boleta"},
                    )
                except Exception as e:
                    print(f"[Boleta] evidencia compra: {e}")

    return {
        "success": True,
        "boleta_url": boleta_url,
        "proveedor": parsed.get("proveedor"),
        "fecha": parsed.get("fecha"),
        "total": parsed.get("total"),
        "items_detectados": matches,
    }


@router.get("/{lista_id}/informe")
async def informe_lista(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Datos para el Informe de la lista: cada ítem con sus comparados
    (descripción scrapeada si falta), definitivo y totales."""
    import httpx
    from app.routers.cotizaciones import _extraer_descripcion_html
    from app.services.supabase import get_supabase
    sb = get_supabase()

    detalle = await detalle_lista(lista_id, ctx)

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
