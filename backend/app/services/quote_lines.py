"""Construcción de líneas de cotización a partir de lo extraído de un correo.

Una línea es **una oferta concreta**: este proveedor ofrece este producto a este
precio. Un correo puede traer varias, y ése es exactamente el caso que el modelo
anterior no podía representar.

Caso real (2026-08-26): Joaquín cotizó dos productos contra un solo ítem —
E27 estándar $19.990 y E27/E40 alta potencia $25.000. Como `resultados` tiene una
fila por (cotizacion, proveedor), la segunda oferta se escribía encima de la
primera y ganaba la última del texto.

Módulo puro: agrupa y normaliza, no toca la base. La persistencia vive en
`quote_lines_service`.

**Las líneas son inmutables por diseño.** Una oferta no se corrige: se descarta y
se crea otra. Editarla en el lugar volvería a perder qué se ofreció realmente,
que es la información que hacía falta para auditar por qué se eligió un precio.
"""
from typing import Any, Optional

from app.services.email_understanding import normalizar_monto

# Campos de una propuesta que describen la oferta, no el ítem pedido.
_CAMPO_A_LINEA = {
    "precio_unitario": "precio",
    "plazo_entrega": "plazo_entrega",
    "condiciones_pago": "condiciones_pago",
    "disponibilidad": "disponibilidad",
    "stock_disponible": "disponibilidad",
    "producto_alternativo": "descripcion_normalizada",
    "descripcion_tecnica": "descripcion_normalizada",
    "marca": "marca",
    "modelo": "modelo",
    "cantidad_ofrecida": "cantidad",
    "unidad_medida": "unidad",
}

ESTADO_PROPUESTA = "propuesta"
ESTADO_VIGENTE = "vigente"
ESTADO_SELECCIONADA = "seleccionada"
ESTADO_DESCARTADA = "descartada"


def agrupar_en_lineas(
    propuestas: list[dict],
    *,
    entity_unico: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Agrupa las propuestas de un correo en líneas, por ítem.

    Devuelve `{cotizacion_o_entity_id: [linea, ...]}`.

    El criterio de separación es el **precio**: dos precios distintos para el
    mismo ítem son dos ofertas distintas, aunque vengan del mismo proveedor y del
    mismo correo. Los campos sin precio propio (plazo, condiciones de pago) se
    aplican a todas las líneas de ese ítem, porque el proveedor los enuncia una
    sola vez para toda su cotización.
    """
    por_item: dict[str, dict[str, dict[str, Any]]] = {}
    comunes: dict[str, dict[str, Any]] = {}

    for propuesta in propuestas:
        entity_id = propuesta.get("entity_id") or entity_unico
        if not entity_id:
            continue  # ambiguo y sin ítem único al que asociarlo
        destino = _CAMPO_A_LINEA.get(propuesta.get("field"))
        if not destino:
            continue
        valor = propuesta.get("new_value")

        if destino == "precio":
            monto = normalizar_monto(valor)
            if monto is None:
                continue
            clave = f"{monto:.2f}"
            linea = por_item.setdefault(entity_id, {}).setdefault(clave, {
                "precio": monto,
                "moneda": propuesta.get("currency") or "CLP",
                "confianza": propuesta.get("confidence"),
                "descripcion_normalizada": None,
            })
            # La nota del modelo suele nombrar el producto ofrecido ("precio para
            # el modelo de alta potencia"): es lo único que distingue una línea
            # de otra cuando el proveedor no repite la descripción.
            if not linea.get("descripcion_normalizada") and propuesta.get("nota"):
                linea["descripcion_normalizada"] = str(propuesta["nota"])[:300]
        else:
            comunes.setdefault(entity_id, {})[destino] = valor

    resultado: dict[str, list[dict[str, Any]]] = {}
    for entity_id, lineas in por_item.items():
        compartidos = comunes.get(entity_id, {})
        resultado[entity_id] = [
            {**compartidos, **linea, "estado": ESTADO_PROPUESTA}
            for _, linea in sorted(lineas.items(), key=lambda par: float(par[0]))
        ]

    # Ítems mencionados sin precio (ej. "kit de pernos: no tenemos"): igual
    # generan línea, para dejar registro de que el proveedor respondió por ese
    # ítem. Sin esto, un "no tenemos" sería indistinguible del silencio.
    for entity_id, compartidos in comunes.items():
        if entity_id not in resultado and compartidos.get("disponibilidad"):
            resultado[entity_id] = [{**compartidos, "precio": None,
                                     "estado": ESTADO_PROPUESTA}]
    return resultado


def es_sin_stock(linea: dict[str, Any]) -> bool:
    """¿La línea representa un 'no tenemos'?"""
    disponibilidad = str(linea.get("disponibilidad") or "").lower()
    return any(marca in disponibilidad for marca in ("no_disponible", "sin stock", "no disponible"))


def seleccionable(linea: dict[str, Any]) -> bool:
    """Sólo se puede elegir una línea con precio y no descartada.

    Es el invariante que `select_final_quote` tiene que respetar: una OC sin
    precio no es una OC.
    """
    return (
        linea.get("estado") != ESTADO_DESCARTADA
        and linea.get("precio") is not None
        and not es_sin_stock(linea)
    )


def resumir(lineas: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen de las líneas de un ítem, para el comparador y el contexto."""
    con_precio = [l for l in lineas if l.get("precio") is not None]
    precios = [float(l["precio"]) for l in con_precio]
    return {
        "total": len(lineas),
        "con_precio": len(con_precio),
        "sin_stock": sum(1 for l in lineas if es_sin_stock(l)),
        "precio_min": min(precios) if precios else None,
        "precio_max": max(precios) if precios else None,
        "seleccionada": next(
            (l.get("id") for l in lineas if l.get("estado") == ESTADO_SELECCIONADA), None
        ),
    }
