"""Una oferta = una línea. El correo con dos productos deja de pisarse.

Caso real (2026-08-26, hilo de la ampolleta): Joaquín cotizó E27 estándar
$19.990 y E27/E40 alta potencia $25.000 en el mismo correo, contra un único ítem
de la lista. Como `resultados` tiene una fila por (cotizacion, proveedor), la
segunda oferta se escribía encima de la primera y ganaba la última del texto:
el borrador de OC quedó en $25.000 cuando lo elegido era $19.990.
"""
import pytest

from app.services.quote_lines import (
    ESTADO_DESCARTADA, ESTADO_PROPUESTA, ESTADO_SELECCIONADA,
    agrupar_en_lineas, es_sin_stock, resumir, seleccionable,
)

ITEM = "ea41d2ff-e08d-4b1a-ad84-e5b033ddca2c"


def p(field, valor, *, entity_id=ITEM, currency=None, nota="", confidence=1.0):
    return {"entity_id": entity_id, "field": field, "new_value": valor,
            "currency": currency, "nota": nota, "confidence": confidence}


# ─── El caso que motivó la tabla ─────────────────────────────────────────────

def test_dos_precios_producen_dos_lineas():
    lineas = agrupar_en_lineas([
        p("precio_unitario", 19990.0, currency="CLP", nota="E27 estándar"),
        p("precio_unitario", 25000.0, currency="CLP", nota="E27/E40 alta potencia"),
    ])[ITEM]
    assert [l["precio"] for l in lineas] == [19990.0, 25000.0]
    assert len(lineas) == 2, "ninguna pisa a la otra"


def test_las_lineas_conservan_que_producto_era_cada_una():
    """Sin esto, dos precios sueltos son indistinguibles al elegir."""
    lineas = agrupar_en_lineas([
        p("precio_unitario", 19990.0, nota="E27 estándar"),
        p("precio_unitario", 25000.0, nota="E27/E40 alta potencia"),
    ])[ITEM]
    descripciones = [l["descripcion_normalizada"] for l in lineas]
    assert "estándar" in descripciones[0]
    assert "alta potencia" in descripciones[1]


def test_quedan_ordenadas_por_precio():
    lineas = agrupar_en_lineas([
        p("precio_unitario", 25000.0), p("precio_unitario", 19990.0),
    ])[ITEM]
    assert [l["precio"] for l in lineas] == [19990.0, 25000.0]


def test_el_mismo_precio_repetido_es_una_sola_linea():
    """Un proveedor que repite el precio en el cuerpo y en la firma no ofrece dos veces."""
    assert len(agrupar_en_lineas([
        p("precio_unitario", 19990.0), p("precio_unitario", 19990.0),
    ])[ITEM]) == 1


# ─── Campos comunes a toda la cotización ─────────────────────────────────────

def test_plazo_y_pago_se_aplican_a_todas_las_lineas():
    """El proveedor los enuncia una vez para toda su cotización."""
    lineas = agrupar_en_lineas([
        p("precio_unitario", 19990.0), p("precio_unitario", 25000.0),
        p("plazo_entrega", "48h desde la OC"), p("condiciones_pago", "transferencia"),
    ])[ITEM]
    assert all(l["plazo_entrega"] == "48h desde la OC" for l in lineas)
    assert all(l["condiciones_pago"] == "transferencia" for l in lineas)


def test_normaliza_montos_chilenos():
    lineas = agrupar_en_lineas([p("precio_unitario", "150.000")])[ITEM]
    assert lineas[0]["precio"] == 150000.0


def test_un_precio_no_numerico_no_crea_linea():
    assert agrupar_en_lineas([p("precio_unitario", "a convenir")]) == {}


# ─── Sin stock ───────────────────────────────────────────────────────────────

def test_sin_stock_genera_linea_sin_precio():
    """El 'kit de pernos: no tenemos'. Sin línea, sería indistinguible del silencio."""
    lineas = agrupar_en_lineas([p("disponibilidad", "no_disponible")])[ITEM]
    assert len(lineas) == 1
    assert lineas[0]["precio"] is None
    assert es_sin_stock(lineas[0])


def test_una_linea_sin_stock_no_es_seleccionable():
    assert seleccionable({"precio": None, "disponibilidad": "no_disponible"}) is False


# ─── Varios ítems en un correo ───────────────────────────────────────────────

def test_separa_por_item():
    lineas = agrupar_en_lineas([
        p("precio_unitario", 19990.0, entity_id="item-a"),
        p("precio_unitario", 8000.0, entity_id="item-b"),
    ])
    assert set(lineas) == {"item-a", "item-b"}
    assert lineas["item-a"][0]["precio"] == 19990.0


def test_propuestas_sin_entity_caen_al_item_unico():
    lineas = agrupar_en_lineas(
        [p("precio_unitario", 19990.0, entity_id=None)], entity_unico=ITEM,
    )
    assert lineas[ITEM][0]["precio"] == 19990.0


def test_sin_entity_ni_item_unico_se_descarta():
    assert agrupar_en_lineas([p("precio_unitario", 19990.0, entity_id=None)]) == {}


# ─── Selección ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("linea,esperado", [
    ({"precio": 19990.0, "estado": ESTADO_PROPUESTA}, True),
    ({"precio": None, "estado": ESTADO_PROPUESTA}, False),
    ({"precio": 19990.0, "estado": ESTADO_DESCARTADA}, False),
    ({"precio": 19990.0, "disponibilidad": "no_disponible"}, False),
])
def test_reglas_de_seleccion(linea, esperado):
    assert seleccionable(linea) is esperado


def test_nacen_como_propuesta_no_como_vigente():
    """Una extracción automática no es una oferta confirmada."""
    lineas = agrupar_en_lineas([p("precio_unitario", 19990.0)])[ITEM]
    assert lineas[0]["estado"] == ESTADO_PROPUESTA


# ─── Resumen ─────────────────────────────────────────────────────────────────

def test_resumen_da_el_rango_de_precios():
    r = resumir([
        {"precio": 19990.0}, {"precio": 25000.0},
        {"precio": None, "disponibilidad": "no_disponible"},
    ])
    assert r == {"total": 3, "con_precio": 2, "sin_stock": 1,
                 "precio_min": 19990.0, "precio_max": 25000.0, "seleccionada": None}


def test_resumen_identifica_la_seleccionada():
    r = resumir([{"id": "ql-1", "precio": 19990.0, "estado": ESTADO_SELECCIONADA}])
    assert r["seleccionada"] == "ql-1"


def test_resumen_de_lista_vacia_no_rompe():
    assert resumir([])["precio_min"] is None
