"""Servicios compartidos para la entidad operativa de listas de cotización."""
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext

MARCA_LISTA = "lista_cotizacion"


@dataclass(frozen=True)
class ListItemInput:
    cotizacion_id: str
    nombre: str
    cantidad: float = 1
    unidad: str = "unidad"
    partida: Optional[str] = None


def parse_list_project(project: dict) -> Optional[dict]:
    try:
        data = json.loads(project.get("descripcion") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("tipo") == MARCA_LISTA else None


def build_list_payload(items: Iterable[ListItemInput]) -> dict:
    normalized = []
    seen: set[str] = set()
    for item in items:
        if not item.cotizacion_id or item.cotizacion_id in seen:
            raise HTTPException(status_code=422, detail="Cada cotización debe ser válida y única dentro de la lista")
        if not item.nombre.strip():
            raise HTTPException(status_code=422, detail="Cada ítem debe tener nombre")
        if item.cantidad <= 0:
            raise HTTPException(status_code=422, detail="La cantidad debe ser mayor a 0")
        seen.add(item.cotizacion_id)
        row = asdict(item)
        row["nombre"] = item.nombre.strip()
        row["comparado"] = False
        normalized.append(row)
    if not normalized:
        raise HTTPException(status_code=422, detail="La lista debe contener al menos un ítem")
    return {"tipo": MARCA_LISTA, "items": normalized, "definitivos": {}}


def _validate_quote_ownership(sb, actor: ApplicationActorContext, quote_ids: set[str]) -> None:
    if not quote_ids:
        return
    result = (
        sb.table("cotizaciones").select("id").in_("id", list(quote_ids))
        .in_("user_id", list(actor.organization_user_ids)).execute()
    )
    found = {str(row["id"]) for row in (result.data or [])}
    if found != quote_ids:
        raise HTTPException(status_code=404, detail="Una o más cotizaciones no pertenecen a la organización")


def create_list(sb, actor: ApplicationActorContext, name: str, items: Iterable[ListItemInput]) -> dict:
    if not name.strip():
        raise HTTPException(status_code=422, detail="La lista debe tener nombre")
    data = build_list_payload(items)
    _validate_quote_ownership(sb, actor, {item["cotizacion_id"] for item in data["items"]})
    result = sb.table("proyectos").insert({
        "user_id": actor.actor_user_id,
        "nombre": name.strip(),
        "descripcion": json.dumps(data, ensure_ascii=False),
        "estado": "borrador",
        "monto_total": 0,
    }).execute()
    if not result.data:
        raise RuntimeError("Supabase no devolvió la lista creada")
    return {"id": result.data[0]["id"], **data}


def list_lists(sb, actor: ApplicationActorContext) -> list[dict]:
    ids = list(actor.organization_user_ids)
    projects = sb.table("proyectos").select("*").in_("user_id", ids).order("created_at", desc=True).execute()
    output: list[dict] = []
    included_quotes: set[str] = set()
    for project in projects.data or []:
        data = parse_list_project(project)
        if not data:
            continue
        items = data.get("items", [])
        included_quotes.update(i.get("cotizacion_id") for i in items if i.get("cotizacion_id"))
        output.append({
            "id": project["id"],
            "nombre": project["nombre"],
            "created_at": project.get("created_at"),
            "monto_total": project.get("monto_total") or 0,
            "n_items": len(items),
            "n_comparados": sum(1 for item in items if item.get("comparado")),
            "n_definitivos": len(data.get("definitivos", {})),
            "aprobacion_estado": (data.get("aprobacion") or {}).get("estado"),
            "es_cotizacion_simple": False,
            "creado_por": project.get("user_id"),
        })
    try:
        quotes = sb.table("cotizaciones").select(
            "id, nombre_identificado, estado, created_at, user_id"
        ).in_("user_id", ids).order("created_at", desc=True).execute()
    except Exception:
        quotes = None
    for quote in (quotes.data or []) if quotes else []:
        if quote["id"] in included_quotes:
            continue
        output.append({
            "id": quote["id"],
            "nombre": quote.get("nombre_identificado") or "Ítem sin nombre",
            "created_at": quote.get("created_at"),
            "monto_total": 0,
            "n_items": 1,
            "n_comparados": 0,
            "n_definitivos": 0,
            "aprobacion_estado": None,
            "es_cotizacion_simple": True,
            "creado_por": quote.get("user_id"),
        })
    output.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return output


def get_list(sb, actor: ApplicationActorContext, list_id: str) -> dict:
    result = (
        sb.table("proyectos").select("*").eq("id", list_id)
        .in_("user_id", list(actor.organization_user_ids)).limit(1).execute()
    )
    project = (result.data or [None])[0]
    data = parse_list_project(project or {})
    if not project or not data:
        raise HTTPException(status_code=404, detail="Lista no encontrada")
    return {
        "id": project["id"], "nombre": project.get("nombre"),
        "estado": project.get("estado"), "monto_total": project.get("monto_total") or 0,
        "created_at": project.get("created_at"), "creado_por": project.get("user_id"),
        **data,
    }


def _save_list(sb, actor: ApplicationActorContext, list_id: str, data: dict, **changes: Any) -> dict:
    payload = {"descripcion": json.dumps(data, ensure_ascii=False), **changes}
    result = (
        sb.table("proyectos").update(payload).eq("id", list_id)
        .in_("user_id", list(actor.organization_user_ids)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Lista no encontrada")
    return get_list(sb, actor, list_id)


def rename_list(sb, actor: ApplicationActorContext, list_id: str, name: str) -> dict:
    if not name.strip():
        raise HTTPException(status_code=422, detail="El nombre de la lista es requerido")
    current = get_list(sb, actor, list_id)
    data = {key: current[key] for key in ("tipo", "items", "definitivos") if key in current}
    return _save_list(sb, actor, list_id, data, nombre=name.strip())


def add_list_items(sb, actor: ApplicationActorContext, list_id: str, items: Iterable[ListItemInput]) -> dict:
    current = get_list(sb, actor, list_id)
    additions = build_list_payload(items)["items"]
    _validate_quote_ownership(sb, actor, {item["cotizacion_id"] for item in additions})
    existing_ids = {item.get("cotizacion_id") for item in current["items"]}
    if any(item["cotizacion_id"] in existing_ids for item in additions):
        raise HTTPException(status_code=409, detail="La cotización ya pertenece a la lista")
    data = {"tipo": MARCA_LISTA, "items": [*current["items"], *additions], "definitivos": current.get("definitivos", {})}
    return _save_list(sb, actor, list_id, data)


def update_list_item(
    sb, actor: ApplicationActorContext, list_id: str, cotizacion_id: str,
    *, name: Optional[str] = None, quantity: Optional[float] = None,
    unit: Optional[str] = None, section: Optional[str] = None,
) -> dict:
    current = get_list(sb, actor, list_id)
    found = False
    items = []
    for original in current["items"]:
        item = dict(original)
        if item.get("cotizacion_id") == cotizacion_id:
            found = True
            if name is not None:
                if not name.strip(): raise HTTPException(status_code=422, detail="El nombre no puede estar vacío")
                item["nombre"] = name.strip()
            if quantity is not None:
                if quantity <= 0: raise HTTPException(status_code=422, detail="La cantidad debe ser mayor a 0")
                item["cantidad"] = quantity
            if unit is not None: item["unidad"] = unit.strip() or "unidad"
            if section is not None: item["partida"] = section.strip() or None
        items.append(item)
    if not found:
        raise HTTPException(status_code=404, detail="Ítem no encontrado en la lista")
    data = {"tipo": MARCA_LISTA, "items": items, "definitivos": current.get("definitivos", {})}
    return _save_list(sb, actor, list_id, data)


def remove_list_item(sb, actor: ApplicationActorContext, list_id: str, cotizacion_id: str) -> dict:
    current = get_list(sb, actor, list_id)
    items = [item for item in current["items"] if item.get("cotizacion_id") != cotizacion_id]
    if len(items) == len(current["items"]):
        raise HTTPException(status_code=404, detail="Ítem no encontrado en la lista")
    if not items:
        raise HTTPException(status_code=409, detail="No se puede dejar una lista sin ítems")
    definitivos = dict(current.get("definitivos", {}))
    definitivos.pop(cotizacion_id, None)
    return _save_list(sb, actor, list_id, {"tipo": MARCA_LISTA, "items": items, "definitivos": definitivos})


def create_list_from_identified_items(
    sb,
    actor: ApplicationActorContext,
    *,
    name: str,
    source_description: Optional[str],
    items: list[dict[str, Any]],
    idempotency_key: str,
) -> dict:
    """Invoca la función SQL transaccional agregada por migración 038."""
    if not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key es requerido")
    if not items:
        raise HTTPException(status_code=422, detail="Se requiere al menos un ítem identificado")
    response = sb.rpc("baiyer_create_list_from_items", {
        "p_actor_user_id": actor.actor_user_id,
        "p_organization_id": actor.organization_id,
        "p_name": name.strip(),
        "p_source_description": source_description,
        "p_items": items,
        "p_idempotency_key": idempotency_key.strip(),
    }).execute()
    data = response.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        raise RuntimeError("La función atómica no devolvió resultado")
    return data
