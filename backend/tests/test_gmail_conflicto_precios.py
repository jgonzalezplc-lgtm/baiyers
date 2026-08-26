"""Un precio ambiguo debe frenar el flujo, no resolverse solo.

Caso real (2026-08-26, hilo 64f2e851): Joaquín cotizó DOS productos en un mismo
correo — E27 estándar $19.990 y E27/E40 alta potencia $25.000 — contra un único
ítem de la lista. Ambas propuestas caían en el mismo entity_id+field y se
aplicaban una tras otra, así que ganaba la última por su orden en el texto. El
borrador de OC quedó en $25.000 cuando lo cotizado y elegido era $19.990, y lo
único que lo frenó fue que una persona notó la diferencia antes de emitirla.
"""
from app.routers.gmail import _campos_en_conflicto, _mismo_monto

ITEM = "ea41d2ff-e08d-4b1a-ad84-e5b033ddca2c"


def _p(field, valor, entity_id=ITEM):
    return {"entity_id": entity_id, "field": field, "new_value": valor}


# ─── Detección de conflicto ──────────────────────────────────────────────────

def test_dos_precios_para_el_mismo_item_es_conflicto():
    """El caso exacto del correo de Joaquín."""
    conflictos = _campos_en_conflicto(
        [_p("precio_unitario", 19990.0), _p("precio_unitario", 25000.0)], None
    )
    assert conflictos == {(ITEM, "precio_unitario")}


def test_un_solo_precio_no_es_conflicto():
    assert _campos_en_conflicto([_p("precio_unitario", 19990.0)], None) == set()


def test_el_mismo_precio_repetido_no_es_conflicto():
    """El proveedor que repite el precio en el cuerpo y en la firma no debe
    frenar nada: los valores coinciden."""
    conflictos = _campos_en_conflicto(
        [_p("precio_unitario", 19990.0), _p("precio_unitario", 19990.0)], None
    )
    assert conflictos == set()


def test_campos_distintos_del_mismo_item_no_chocan():
    conflictos = _campos_en_conflicto(
        [_p("precio_unitario", 19990.0), _p("plazo_entrega", "48h")], None
    )
    assert conflictos == set()


def test_mismo_precio_para_items_distintos_no_choca():
    """Dos ítems que cuestan lo mismo son perfectamente normales."""
    conflictos = _campos_en_conflicto(
        [_p("precio_unitario", 8000.0), _p("precio_unitario", 8000.0, entity_id="otro")], None
    )
    assert conflictos == set()


def test_propuestas_sin_entity_caen_al_item_unico():
    """Si la conversación es de un solo ítem, las propuestas sin asociar se
    resuelven contra él — y ahí también pueden chocar entre sí."""
    conflictos = _campos_en_conflicto(
        [_p("precio_unitario", 19990.0, entity_id=None),
         _p("precio_unitario", 25000.0, entity_id=None)],
        entity_unico=ITEM,
    )
    assert conflictos == {(ITEM, "precio_unitario")}


def test_sin_entity_ni_item_unico_se_ignora():
    """No hay a qué asociarlas, así que no se inventa un conflicto."""
    conflictos = _campos_en_conflicto(
        [_p("precio_unitario", 19990.0, entity_id=None),
         _p("precio_unitario", 25000.0, entity_id=None)],
        entity_unico=None,
    )
    assert conflictos == set()


def test_conflicto_en_campo_de_texto():
    conflictos = _campos_en_conflicto(
        [_p("plazo_entrega", "48h"), _p("plazo_entrega", "5 días hábiles")], None
    )
    assert conflictos == {(ITEM, "plazo_entrega")}


# ─── Comparación de montos ───────────────────────────────────────────────────

def test_mismo_monto_tolera_tipos_distintos():
    """La columna devuelve float y la extracción puede traer str: releer el
    mismo precio no puede verse como un cambio."""
    assert _mismo_monto(19990.0, "19990") is True
    assert _mismo_monto("19.990", 19990.0) is True
    assert _mismo_monto(19990, 19990.0) is True


def test_mismo_monto_detecta_diferencia_real():
    assert _mismo_monto(19990.0, 25000.0) is False


def test_mismo_monto_cae_a_texto_si_no_hay_numero():
    assert _mismo_monto("a convenir", "a convenir") is True
    assert _mismo_monto("a convenir", "por definir") is False
