"""El agente no debe pedirle al proveedor datos que ya le dio.

Caso real (2026-08-26, hilo 64f2e851), con los tiempos exactos:

    15:23:39  ← Joaquín: "Confirmo... $19.990"
    15:23:45  → Baiyer:  "nos falta la disponibilidad, el plazo y las condiciones"
    15:42:39  ← Joaquín: "48h desde la OC. Transferencia: Banco..."
    15:42:47  → Baiyer:  "nos falta la disponibilidad y EL PRECIO UNITARIO"

El precio ya estaba extraído, aplicado y persistido desde las 15:23 (confianza
1.0). El cálculo de "qué falta" era `CAMPOS_SEGUIMIENTO - campos_recibidos`, y
`campos_recibidos` se armaba dentro del bucle de cada mensaje: se reiniciaba en
cada correo. Además `disponibilidad` no tiene columna en `resultados`, así que
era insatisfacible por construcción y se pedía siempre.
"""
from unittest.mock import MagicMock

from app.routers.gmail import (
    MAX_SEGUIMIENTOS_AUTOMATICOS, _campos_pendientes, _seguimientos_ya_enviados,
)

ITEM = "ea41d2ff-e08d-4b1a-ad84-e5b033ddca2c"


def _sb(resultados: list[dict], disponibilidad_aplicada: int = 0, outbound: int = 0):
    """Supabase falso que responde según la tabla consultada."""
    sb = MagicMock()

    def por_tabla(nombre):
        t = MagicMock()
        if nombre == "resultados":
            t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=resultados)
        elif nombre == "item_field_updates":
            (t.select.return_value.in_.return_value.in_.return_value
             .eq.return_value.execute.return_value) = MagicMock(count=disponibilidad_aplicada)
        elif nombre == "gmail_messages":
            (t.select.return_value.eq.return_value.eq.return_value
             .execute.return_value) = MagicMock(count=outbound)
        return t

    sb.table.side_effect = por_tabla
    return sb


COMPLETO = {
    "id": ITEM, "precio_cotizado": 19990.0,
    "plazo_entrega": "48h desde la recepción de la OC",
    "condiciones_pago": "transferencia",
}


# ─── Memoria: lo persistido manda, no el último correo ───────────────────────

def test_no_vuelve_a_pedir_el_precio_ya_guardado():
    """El bug exacto de las 15:42:47."""
    sb = _sb([COMPLETO], disponibilidad_aplicada=1)
    assert _campos_pendientes(sb, [ITEM]) == set()


def test_pide_solo_lo_que_realmente_falta():
    sb = _sb([{**COMPLETO, "condiciones_pago": None}], disponibilidad_aplicada=1)
    assert _campos_pendientes(sb, [ITEM]) == {"condiciones_pago"}


def test_ficha_vacia_pide_todo():
    sb = _sb([{"id": ITEM, "precio_cotizado": None, "plazo_entrega": None,
               "condiciones_pago": None}])
    assert _campos_pendientes(sb, [ITEM]) == {
        "precio_unitario", "plazo_entrega", "condiciones_pago", "disponibilidad",
    }


def test_cadena_vacia_cuenta_como_faltante():
    """Un campo en "" no es un dato, es un hueco."""
    sb = _sb([{**COMPLETO, "plazo_entrega": ""}], disponibilidad_aplicada=1)
    assert "plazo_entrega" in _campos_pendientes(sb, [ITEM])


# ─── disponibilidad: dejó de ser insatisfacible ──────────────────────────────

def test_disponibilidad_respondida_no_se_vuelve_a_pedir():
    """No tiene columna propia: se resuelve contra el log de auditoría."""
    sb = _sb([COMPLETO], disponibilidad_aplicada=1)
    assert "disponibilidad" not in _campos_pendientes(sb, [ITEM])


def test_disponibilidad_sin_responder_sigue_pendiente():
    sb = _sb([COMPLETO], disponibilidad_aplicada=0)
    assert _campos_pendientes(sb, [ITEM]) == {"disponibilidad"}


# ─── Conversaciones de varios ítems ──────────────────────────────────────────

def test_con_al_menos_un_dato_no_se_insiste():
    """RFQ agrupada: si un ítem trajo precio, no se le vuelve a pedir "el precio"
    al proveedor. Preferimos un dato incompleto —que se pide a mano— antes que
    escribirle de más a alguien que ya respondió."""
    sb = _sb([
        {"id": ITEM, "precio_cotizado": 19990.0, "plazo_entrega": None, "condiciones_pago": None},
        {"id": "otro", "precio_cotizado": None, "plazo_entrega": None, "condiciones_pago": None},
    ], disponibilidad_aplicada=1)
    assert "precio_unitario" not in _campos_pendientes(sb, [ITEM, "otro"])


def test_sin_items_no_consulta_nada():
    sb = _sb([])
    assert _campos_pendientes(sb, []) == set()
    sb.table.assert_not_called()


# ─── Tope duro de seguimientos ───────────────────────────────────────────────

def test_el_primer_outbound_es_la_rfq_no_un_seguimiento():
    assert _seguimientos_ya_enviados(_sb([], outbound=1), "c1") == 0


def test_cuenta_los_seguimientos_reales():
    assert _seguimientos_ya_enviados(_sb([], outbound=3), "c1") == 2


def test_nunca_es_negativo():
    """Conversación sin outbound registrado (dato viejo o import parcial)."""
    assert _seguimientos_ya_enviados(_sb([], outbound=0), "c1") == 0


def test_el_tope_es_bajo_a_proposito():
    """Tres correos automáticos ya fue demasiado en el caso real."""
    assert MAX_SEGUIMIENTOS_AUTOMATICOS <= 2
