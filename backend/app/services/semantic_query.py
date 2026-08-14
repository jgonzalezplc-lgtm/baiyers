"""Consultas estructuradas read-only sobre entidades Baiyer permitidas."""
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext


@dataclass(frozen=True)
class EntitySpec:
    table: str
    fields: frozenset[str]
    ownership: str = "user_id"
    default_order: str = "created_at"


ENTITY_SPECS = {
    "lists": EntitySpec("proyectos", frozenset({"id", "nombre", "estado", "monto_total", "created_at", "updated_at"})),
    "quotes": EntitySpec("cotizaciones", frozenset({"id", "descripcion", "nombre_identificado", "marca", "numero_parte", "categoria", "estado", "confianza_ia", "created_at", "updated_at"})),
    "suppliers": EntitySpec("proveedores", frozenset({"id", "nombre", "rut", "email", "telefono", "sitio_web", "rubro", "ciudad", "score", "preferido", "created_at", "updated_at"})),
    "purchase_orders": EntitySpec("ordenes_compra", frozenset({"id", "numero_oc", "estado", "precio_total", "moneda", "proveedor_nombre", "proveedor_email", "created_at", "confirmada_at", "despacho_at", "recibido_conforme_at"})),
    "invoices": EntitySpec("facturas", frozenset({"id", "proveedor_nombre", "numero_factura", "fecha_factura", "fecha_vencimiento", "monto_neto", "iva", "monto_total", "moneda", "estado", "oc_id", "fecha_pago", "created_at"})),
}
OPERATORS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "in", "ilike"})


def describe_schema() -> dict:
    return {name: sorted(spec.fields) for name, spec in ENTITY_SPECS.items()}


def query_data(sb, actor: ApplicationActorContext, request: dict[str, Any]) -> list[dict]:
    entity = request.get("entity")
    spec = ENTITY_SPECS.get(entity)
    if not spec:
        raise HTTPException(status_code=422, detail="Entidad no permitida")
    fields = request.get("fields") or sorted(spec.fields)
    if not fields or any(field not in spec.fields for field in fields):
        raise HTTPException(status_code=422, detail="La consulta contiene campos no permitidos")
    limit = int(request.get("limit", 50))
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit debe estar entre 1 y 200")
    query = sb.table(spec.table).select(",".join(fields)).in_(spec.ownership, list(actor.organization_user_ids))
    for item in request.get("filters") or []:
        field, operator, value = item.get("field"), item.get("operator"), item.get("value")
        if field not in spec.fields or operator not in OPERATORS:
            raise HTTPException(status_code=422, detail="Filtro no permitido")
        if operator == "in":
            if not isinstance(value, list) or len(value) > 100:
                raise HTTPException(status_code=422, detail="El operador in requiere una lista de hasta 100 valores")
            query = query.in_(field, value)
        else:
            query = getattr(query, operator)(field, value)
    order = request.get("order") or {"field": spec.default_order, "direction": "desc"}
    if order["field"] not in spec.fields or order.get("direction", "desc") not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Orden no permitido")
    result = query.order(order["field"], desc=order.get("direction", "desc") == "desc").limit(limit).execute()
    return result.data or []
