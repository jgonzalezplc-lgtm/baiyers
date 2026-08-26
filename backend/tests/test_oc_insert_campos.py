"""Crear una OC no puede perder el proveedor en silencio.

Caso real: OC-2026-0007 (2026-08-26) quedó en la DB con `proveedor_nombre`,
`nombre_item`, `precio_unitario`, `notas` y `lista_proyecto_id` en null. La API
igual devolvió esos valores —hacía eco del request— así que la OC parecía
correcta hasta que el envío falló por no tener a quién mandarla, y hubo que
restaurar el correo a mano.

Causa: el insert intentaba las columnas agregadas por ALTER TABLE manual y, ante
CUALQUIER excepción, reintentaba sin ellas. El `except Exception as e` ligaba `e`
y nunca lo usaba, así que tampoco quedó registro de por qué falló.
"""
from unittest.mock import MagicMock

import pytest

from app.routers.oc import _CAMPOS_EXTRA_OC, _es_columna_inexistente, _insertar_oc

FILA = {
    "numero_oc": "OC-2026-0008", "estado": "borrador", "precio_total": 23788.0,
    "nombre_item": "Ampolleta LED E27 100W", "proveedor_nombre": "Joaquín González",
    "proveedor_email": "joaquin.gonzalez.pl@usach.cl", "cantidad": 1,
    "precio_unitario": 19990.0, "notas": None, "lista_proyecto_id": "lista-1",
    "direccion_despacho": "Bodega Central, Maipú",
}


def _sb(fallos: list):
    """Supabase falso: `fallos` son las excepciones a lanzar, en orden, antes de
    que el insert funcione."""
    sb = MagicMock()
    pendientes = list(fallos)
    llamadas = []

    def insert(row):
        llamadas.append(row)
        ejec = MagicMock()
        if pendientes:
            ejec.execute.side_effect = pendientes.pop(0)
        else:
            ejec.execute.return_value = MagicMock(data=[{"id": "oc-nueva", **row}])
        return ejec

    sb.table.return_value.insert.side_effect = insert
    sb.llamadas = llamadas
    return sb


class _ErrorColumna(Exception):
    def __str__(self):
        return "{'code': 'PGRST204', 'message': \"Could not find the 'notas' column of 'ordenes_compra'\"}"


# ─── Clasificación del error ─────────────────────────────────────────────────

def test_reconoce_columna_inexistente_por_codigo():
    assert _es_columna_inexistente(_ErrorColumna()) is True


def test_reconoce_columna_inexistente_por_mensaje():
    assert _es_columna_inexistente(Exception("Could not find the 'x' column")) is True


@pytest.mark.parametrize("mensaje", [
    "violates foreign key constraint",
    "invalid input syntax for type numeric",
    "timeout",
    "duplicate key value violates unique constraint",
])
def test_otros_errores_no_son_columna_inexistente(mensaje):
    """Estos son justamente los que antes producían una OC incompleta."""
    assert _es_columna_inexistente(Exception(mensaje)) is False


# ─── Comportamiento del insert ───────────────────────────────────────────────

def test_camino_feliz_conserva_todos_los_campos():
    sb = _sb([])
    fila, omitidos = _insertar_oc(sb, dict(FILA))
    assert omitidos == ()
    assert fila["proveedor_email"] == "joaquin.gonzalez.pl@usach.cl"
    assert fila["proveedor_nombre"] == "Joaquín González"


def test_un_error_real_se_propaga_en_vez_de_crear_una_oc_incompleta():
    """Mejor no crear la OC que crear una sin proveedor ni precio unitario."""
    sb = _sb([Exception("violates foreign key constraint")])
    with pytest.raises(Exception, match="foreign key"):
        _insertar_oc(sb, dict(FILA))
    assert len(sb.llamadas) == 1, "no debe reintentar sin los campos"


def test_columna_ausente_reintenta_y_declara_lo_omitido():
    sb = _sb([_ErrorColumna()])
    fila, omitidos = _insertar_oc(sb, dict(FILA))
    assert set(omitidos) == set(_CAMPOS_EXTRA_OC)
    assert "proveedor_email" not in fila
    assert len(sb.llamadas) == 2


def test_el_reintento_conserva_los_campos_base():
    """Perder las columnas extra no puede llevarse el número ni el total."""
    sb = _sb([_ErrorColumna()])
    fila, _ = _insertar_oc(sb, dict(FILA))
    assert fila["numero_oc"] == "OC-2026-0008"
    assert fila["precio_total"] == 23788.0


def test_solo_declara_omitidos_los_campos_que_venian_en_la_fila():
    """Si la OC no traía notas, no se reporta como campo perdido."""
    fila_parcial = {k: v for k, v in FILA.items() if k not in ("notas", "lista_proyecto_id")}
    sb = _sb([_ErrorColumna()])
    _, omitidos = _insertar_oc(sb, fila_parcial)
    assert "notas" not in omitidos
    assert "proveedor_email" in omitidos


def test_se_registra_el_motivo_del_fallback(capsys):
    """El bug quedó sin diagnóstico porque nadie logueaba la excepción."""
    _insertar_oc(_sb([_ErrorColumna()]), dict(FILA))
    salida = capsys.readouterr().out
    assert "PGRST204" in salida
    assert "proveedor_email" in salida
