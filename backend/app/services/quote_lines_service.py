"""Persistencia de líneas de cotización.

Separado de `quote_lines` (núcleo puro) por la misma razón que el resto del repo:
la lógica de agrupar y decidir se prueba sin base de datos.

**Convive con `resultados`, no lo reemplaza.** `resultados` sigue siendo la fila
por proveedor que usan búsqueda web, RFQ, comparador, homologación y OC. Las
líneas agregan lo que ese modelo no puede expresar: varias ofertas del mismo
proveedor para el mismo ítem.

Toda función tolera que la tabla no exista todavía (migración 049 sin aplicar):
devuelve vacío en vez de lanzar, y el flujo anterior sigue funcionando.
"""
from typing import Any, Optional

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.quote_lines import (
    ESTADO_DESCARTADA, ESTADO_SELECCIONADA, agrupar_en_lineas, seleccionable,
)

_COLUMNAS = (
    "id,cotizacion_id,resultado_id,proveedor_nombre,proveedor_email,"
    "descripcion_normalizada,precio,moneda,cantidad,unidad,plazo_entrega,"
    "condiciones_pago,disponibilidad,origen,source_message_id,confianza,estado,created_at"
)


def _tabla_ausente(error: Exception) -> bool:
    detalle = str(error).lower()
    return "quote_lines" in detalle and (
        "does not exist" in detalle or "not find" in detalle or "pgrst" in detalle
    )


def registrar_desde_correo(
    sb, *, user_id: str, propuestas: list[dict], entity_a_cotizacion: dict[str, str],
    proveedor_nombre: Optional[str], proveedor_email: Optional[str],
    mensaje_id: Optional[str], entity_unico: Optional[str] = None,
) -> list[dict]:
    """Crea una línea por cada oferta distinta encontrada en un correo.

    `entity_a_cotizacion` mapea el `entity_id` de la extracción (un `resultado`)
    a su `cotizacion_id`. Sin ese mapa la línea no sabría a qué ítem pertenece.

    Idempotente por el índice único de la 049 (mensaje + ítem + descripción): un
    correo re-sincronizado no duplica lo que ya creó.
    """
    agrupadas = agrupar_en_lineas(propuestas, entity_unico=entity_unico)
    if not agrupadas:
        return []

    filas = []
    for entity_id, lineas in agrupadas.items():
        cotizacion_id = entity_a_cotizacion.get(entity_id)
        if not cotizacion_id:
            continue
        for linea in lineas:
            filas.append({
                "user_id": user_id,
                "cotizacion_id": cotizacion_id,
                "resultado_id": entity_id,
                "proveedor_nombre": proveedor_nombre,
                "proveedor_email": proveedor_email,
                "source_message_id": mensaje_id,
                "origen": "correo",
                **{k: v for k, v in linea.items() if k in {
                    "precio", "moneda", "cantidad", "unidad", "plazo_entrega",
                    "condiciones_pago", "disponibilidad", "descripcion_normalizada",
                    "confianza", "estado",
                }},
            })
    if not filas:
        return []

    try:
        return sb.table("quote_lines").upsert(
            filas, on_conflict="source_message_id,cotizacion_id,descripcion_normalizada",
            ignore_duplicates=True,
        ).execute().data or []
    except Exception as e:
        if _tabla_ausente(e):
            print("[QuoteLines] tabla ausente (049 sin aplicar); se omite el registro")
            return []
        # No se propaga: perder las líneas es malo, pero perder la sincronización
        # entera del correo es peor. El flujo por `resultados` sigue vigente.
        print(f"[QuoteLines] no se pudieron registrar: {type(e).__name__}: {e}")
        return []


def listar_por_item(sb, actor: ApplicationActorContext, cotizacion_id: str) -> list[dict]:
    try:
        return sb.table("quote_lines").select(_COLUMNAS).eq(
            "cotizacion_id", cotizacion_id
        ).in_("user_id", list(actor.organization_user_ids)).neq(
            "estado", ESTADO_DESCARTADA
        ).order("precio").execute().data or []
    except Exception as e:
        if not _tabla_ausente(e):
            print(f"[QuoteLines] no se pudieron listar: {type(e).__name__}: {e}")
        return []


def obtener(sb, actor: ApplicationActorContext, quote_line_id: str) -> dict:
    try:
        filas = sb.table("quote_lines").select(_COLUMNAS).eq(
            "id", quote_line_id
        ).in_("user_id", list(actor.organization_user_ids)).limit(1).execute().data or []
    except Exception as e:
        if _tabla_ausente(e):
            raise HTTPException(status_code=409, detail=(
                "Las líneas de cotización requieren aplicar la migración 049."
            ))
        raise
    if not filas:
        # 404 y no 403: un 403 confirmaría que el id existe en otra organización.
        raise HTTPException(status_code=404, detail="Línea de cotización no encontrada")
    return filas[0]


def seleccionar(sb, actor: ApplicationActorContext, quote_line_id: str) -> dict:
    """Marca una línea como definitiva de su ítem y libera la anterior.

    Reemplazar es explícito: la línea previa vuelve a `vigente`, no se borra.
    Perder qué se había elegido antes haría imposible auditar un cambio de
    decisión sobre una compra.
    """
    linea = obtener(sb, actor, quote_line_id)
    if not seleccionable(linea):
        raise HTTPException(status_code=409, detail={
            "error": "linea_no_seleccionable",
            "mensaje": (
                "Sin precio o sin stock: no se puede elegir como definitiva."
                if linea.get("precio") is None
                else "La línea fue descartada."
            ),
            "quote_line_id": quote_line_id,
        })

    sb.table("quote_lines").update({"estado": "vigente"}).eq(
        "cotizacion_id", linea["cotizacion_id"]
    ).eq("estado", ESTADO_SELECCIONADA).execute()
    actualizada = sb.table("quote_lines").update(
        {"estado": ESTADO_SELECCIONADA}
    ).eq("id", quote_line_id).execute().data or [linea]
    return actualizada[0]


def descartar(sb, actor: ApplicationActorContext, quote_line_id: str) -> dict:
    """Saca una línea de consideración sin borrarla: la oferta existió."""
    obtener(sb, actor, quote_line_id)
    filas = sb.table("quote_lines").update(
        {"estado": ESTADO_DESCARTADA}
    ).eq("id", quote_line_id).execute().data or []
    return filas[0] if filas else {"id": quote_line_id, "estado": ESTADO_DESCARTADA}


def resumen_por_item(sb, actor: ApplicationActorContext, cotizacion_id: str) -> dict[str, Any]:
    from app.services.quote_lines import resumir
    return resumir(listar_por_item(sb, actor, cotizacion_id))
