"""El bloque `process` que viaja adjunto a otras respuestas MCP.

Antes cada tool devolvía su resultado y nada más: el cliente no sabía en qué
etapa quedaba la compra ni qué la bloqueaba, así que lo reconstruía llamando
media docena de tools. Ahora las siete respuestas que cambian la conversación
llevan el estado del proceso adentro.
"""
from unittest.mock import MagicMock, patch

from app.services import contexto_compra_service as svc
from app.services.mcp_context import ApplicationActorContext


def actor():
    return ApplicationActorContext("user-1", "org-1", "Org", ("owner", "user-1"), client_id="codex")


LISTA = {
    "id": "lista-1", "nombre": "Cotización WC casa",
    "items": [{"cotizacion_id": f"c{i}", "nombre": f"Ítem {i}"} for i in range(6)],
    "definitivos": {},
    "aprobacion": {},
}


def _sb(conteos=None, sin_tabla=False):
    """Supabase falso: `conteos` mapea tabla → count devuelto."""
    conteos = conteos or {}
    sb = MagicMock()

    def por_tabla(nombre):
        t = MagicMock()
        if sin_tabla:
            t.select.side_effect = Exception(f"relation {nombre} does not exist")
            return t
        cadena = t.select.return_value.eq.return_value.in_.return_value
        cadena.execute.return_value = MagicMock(count=conteos.get(nombre, 0))
        t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        return t

    sb.table.side_effect = por_tabla
    return sb


def _bloque(sb, lista=LISTA):
    with patch.object(svc, "_contexto_de_grafo", return_value=None), \
         patch.object(svc, "_tiene_despacho", return_value=True):
        return svc.bloque_proceso(sb, actor(), lista["id"], lista=lista)


# ─── Forma del bloque ────────────────────────────────────────────────────────

def test_devuelve_la_clave_process():
    bloque = _bloque(_sb())
    assert set(bloque) == {"process"}
    assert set(bloque["process"]) == {
        "etapa_actual", "etapa_label", "origen",
        "completadas", "pendientes", "bloqueos", "proximas_acciones",
    }


def test_omite_lo_que_solo_importa_al_preguntar_por_el_proceso():
    """Transiciones y aprobaciones sólo viajan en get_purchase_context."""
    proceso = _bloque(_sb())["process"]
    assert "transiciones" not in proceso
    assert "aprobaciones_requeridas" not in proceso


def test_refleja_la_etapa_real():
    proceso = _bloque(_sb({"rfq_batches": 1}))["process"]
    assert proceso["etapa_actual"] in ("rfq_preparada", "esperando_cotizaciones")


# ─── Nunca puede tumbar la operación que sí funcionó ─────────────────────────

def test_sin_list_id_devuelve_vacio():
    assert svc.bloque_proceso(_sb(), actor(), None) == {}


def test_un_fallo_no_rompe_la_respuesta(capsys):
    """Es un adorno informativo: si falla, la tool responde como antes."""
    sb = MagicMock()
    sb.table.side_effect = Exception("supabase caído")
    with patch.object(svc, "get_list", side_effect=Exception("caído")):
        assert svc.bloque_proceso(sb, actor(), "lista-1") == {}
    assert "no se pudo armar el bloque" in capsys.readouterr().out


def test_una_tabla_ausente_degrada_la_senal_no_la_respuesta():
    """La 043 puede no estar aplicada; el contexto igual responde."""
    proceso = _bloque(_sb(sin_tabla=True))["process"]
    assert proceso["etapa_actual"] == "busqueda"


# ─── Carga en dos pasadas ────────────────────────────────────────────────────

def test_no_consulta_despacho_fuera_de_la_emision():
    """Sin esto, las siete respuestas pagarían consultas que sólo importan
    al emitir una OC."""
    with patch.object(svc, "_contexto_de_grafo", return_value=None), \
         patch.object(svc, "_tiene_despacho") as despacho:
        svc.bloque_proceso(_sb(), actor(), "lista-1", lista=LISTA)
    despacho.assert_not_called()


def test_consulta_despacho_al_emitir():
    lista_aprobada = {**LISTA, "aprobacion": {"estado": "aprobado"},
                      "definitivos": {"c0": {"resultado_id": "r0", "precio": 100}}}
    with patch.object(svc, "_contexto_de_grafo", return_value=None), \
         patch.object(svc, "_tiene_despacho", return_value=False) as despacho:
        proceso = svc.bloque_proceso(_sb(), actor(), "lista-1", lista=lista_aprobada)["process"]
    despacho.assert_called_once()
    assert any(b["codigo"] == "sin_direccion_despacho" for b in proceso["bloqueos"])


def test_reusa_la_lista_que_ya_cargo_el_llamador():
    """`compare_list` ya la leyó: no puede leerla dos veces por respuesta."""
    with patch.object(svc, "get_list") as lectura, \
         patch.object(svc, "_contexto_de_grafo", return_value=None), \
         patch.object(svc, "_tiene_despacho", return_value=True):
        svc.bloque_proceso(_sb(), actor(), "lista-1", lista=LISTA)
    lectura.assert_not_called()
