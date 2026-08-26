"""Persistencia y selección de líneas de cotización.

Convive con `resultados`: si la tabla de la 049 no existe, todo degrada a vacío
y el flujo anterior sigue funcionando.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import quote_lines_service as svc
from app.services.mcp_context import ApplicationActorContext

ITEM_RESULTADO = "res-1"
COTIZACION = "cot-1"


def actor():
    return ApplicationActorContext("user-1", "org-1", "Org", ("owner", "user-1"), client_id="codex")


def p(field, valor, *, currency=None, nota=""):
    return {"entity_id": ITEM_RESULTADO, "field": field, "new_value": valor,
            "currency": currency, "nota": nota, "confidence": 1.0}


PROPUESTAS = [
    p("precio_unitario", 19990.0, currency="CLP", nota="E27 estándar"),
    p("precio_unitario", 25000.0, currency="CLP", nota="E27/E40 alta potencia"),
    p("plazo_entrega", "48h desde la OC"),
]


class _TablaAusente(Exception):
    def __str__(self):
        return "relation \"quote_lines\" does not exist"


def _sb(filas=None, error=None):
    sb = MagicMock()
    if error:
        sb.table.return_value.upsert.return_value.execute.side_effect = error
        sb.table.return_value.select.side_effect = error
    else:
        sb.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=filas or [])
        cadena = sb.table.return_value.select.return_value.eq.return_value.in_.return_value
        cadena.neq.return_value.order.return_value.execute.return_value = MagicMock(data=filas or [])
        cadena.limit.return_value.execute.return_value = MagicMock(data=filas or [])
        sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=filas or [])
        (sb.table.return_value.update.return_value.eq.return_value.eq.return_value
         .execute.return_value) = MagicMock(data=[])
    return sb


# ─── Registro desde un correo ────────────────────────────────────────────────

def test_registra_una_fila_por_oferta():
    sb = _sb()
    svc.registrar_desde_correo(
        sb, user_id="user-1", propuestas=PROPUESTAS,
        entity_a_cotizacion={ITEM_RESULTADO: COTIZACION},
        proveedor_nombre="Joaquín González", proveedor_email="joaquin@usach.cl",
        mensaje_id="msg-1",
    )
    filas = sb.table.return_value.upsert.call_args[0][0]
    assert len(filas) == 2
    assert sorted(f["precio"] for f in filas) == [19990.0, 25000.0]
    assert all(f["cotizacion_id"] == COTIZACION for f in filas)
    assert all(f["source_message_id"] == "msg-1" for f in filas)


def test_el_upsert_ignora_duplicados():
    """Un correo re-sincronizado no puede duplicar sus líneas."""
    sb = _sb()
    svc.registrar_desde_correo(
        sb, user_id="user-1", propuestas=PROPUESTAS,
        entity_a_cotizacion={ITEM_RESULTADO: COTIZACION},
        proveedor_nombre=None, proveedor_email=None, mensaje_id="msg-1",
    )
    kwargs = sb.table.return_value.upsert.call_args[1]
    assert kwargs["ignore_duplicates"] is True
    assert "source_message_id" in kwargs["on_conflict"]


def test_sin_mapa_de_cotizacion_no_inventa_lineas():
    """Una línea sin ítem no sabría a qué compra pertenece."""
    sb = _sb()
    assert svc.registrar_desde_correo(
        sb, user_id="user-1", propuestas=PROPUESTAS, entity_a_cotizacion={},
        proveedor_nombre=None, proveedor_email=None, mensaje_id="msg-1",
    ) == []
    sb.table.return_value.upsert.assert_not_called()


def test_tabla_ausente_degrada_sin_lanzar(capsys):
    """La 049 puede no estar aplicada: la sincronización no puede caerse."""
    assert svc.registrar_desde_correo(
        _sb(error=_TablaAusente()), user_id="user-1", propuestas=PROPUESTAS,
        entity_a_cotizacion={ITEM_RESULTADO: COTIZACION},
        proveedor_nombre=None, proveedor_email=None, mensaje_id="msg-1",
    ) == []
    assert "049" in capsys.readouterr().out


def test_un_error_cualquiera_tampoco_tumba_la_sincronizacion():
    assert svc.registrar_desde_correo(
        _sb(error=Exception("timeout")), user_id="user-1", propuestas=PROPUESTAS,
        entity_a_cotizacion={ITEM_RESULTADO: COTIZACION},
        proveedor_nombre=None, proveedor_email=None, mensaje_id="msg-1",
    ) == []


# ─── Lectura ─────────────────────────────────────────────────────────────────

def test_listar_excluye_descartadas():
    sb = _sb(filas=[{"id": "ql-1", "precio": 19990.0}])
    svc.listar_por_item(sb, actor(), COTIZACION)
    cadena = sb.table.return_value.select.return_value.eq.return_value.in_.return_value
    cadena.neq.assert_called_with("estado", "descartada")


def test_listar_sin_tabla_devuelve_vacio():
    assert svc.listar_por_item(_sb(error=_TablaAusente()), actor(), COTIZACION) == []


def test_linea_inexistente_es_404_no_403():
    """Un 403 confirmaría que el id existe en otra organización."""
    with pytest.raises(HTTPException) as error:
        svc.obtener(_sb(filas=[]), actor(), "ql-inexistente")
    assert error.value.status_code == 404


def test_sin_migracion_lo_dice_explicito():
    with pytest.raises(HTTPException) as error:
        svc.obtener(_sb(error=_TablaAusente()), actor(), "ql-1")
    assert error.value.status_code == 409
    assert "049" in error.value.detail


# ─── Selección ───────────────────────────────────────────────────────────────

def test_selecciona_y_libera_la_anterior():
    """Reemplazar no borra: la línea previa vuelve a vigente."""
    sb = _sb(filas=[{"id": "ql-1", "cotizacion_id": COTIZACION, "precio": 19990.0,
                     "estado": "propuesta"}])
    svc.seleccionar(sb, actor(), "ql-1")
    estados = [c[0][0] for c in sb.table.return_value.update.call_args_list]
    assert {"estado": "vigente"} in estados
    assert {"estado": "seleccionada"} in estados


def test_no_se_puede_elegir_una_linea_sin_precio():
    sb = _sb(filas=[{"id": "ql-2", "cotizacion_id": COTIZACION, "precio": None,
                     "estado": "propuesta"}])
    with pytest.raises(HTTPException) as error:
        svc.seleccionar(sb, actor(), "ql-2")
    assert error.value.detail["error"] == "linea_no_seleccionable"


def test_no_se_puede_elegir_una_linea_sin_stock():
    """El 'kit de pernos: no tenemos' no puede terminar en una OC."""
    sb = _sb(filas=[{"id": "ql-3", "cotizacion_id": COTIZACION, "precio": 1000.0,
                     "disponibilidad": "no_disponible", "estado": "propuesta"}])
    with pytest.raises(HTTPException):
        svc.seleccionar(sb, actor(), "ql-3")


def test_descartar_no_borra():
    """La oferta existió: borrarla haría imposible auditar la decisión."""
    sb = _sb(filas=[{"id": "ql-1", "cotizacion_id": COTIZACION, "precio": 19990.0}])
    svc.descartar(sb, actor(), "ql-1")
    assert sb.table.return_value.update.call_args[0][0] == {"estado": "descartada"}
    sb.table.return_value.delete.assert_not_called()
