"""Etapa, bloqueos y próximas acciones de una compra.

Las tools MCP son acciones sueltas: ninguna sabía en qué etapa estaba la compra
ni qué la bloqueaba, así que el cliente lo reconstruía llamando media docena y
adivinando. Este núcleo es puro y no toca la base.
"""
import pytest

from app.services.contexto_compra import (
    ETAPAS, Senales, acciones_de, construir_contexto, derivar_bloqueos,
    derivar_etapa, separar_etapas,
)


def s(**kwargs) -> Senales:
    return Senales(**{"items_total": 1, **kwargs})


# ─── Derivación de etapa ─────────────────────────────────────────────────────

@pytest.mark.parametrize("senales,esperada", [
    (s(), "busqueda"),
    (s(items_con_ofertas=1), "busqueda"),
    (s(rfq_preparadas=2), "rfq_preparada"),
    (s(rfq_preparadas=2, rfq_enviadas=1), "esperando_cotizaciones"),
    (s(rfq_enviadas=1, respuestas_recibidas=1), "comparacion"),
    (s(respuestas_recibidas=1, definitivos=1), "seleccion_lista"),
    (s(definitivos=1, aprobacion_estado="pendiente"), "esperando_aprobacion"),
    (s(definitivos=1, aprobacion_estado="rechazado"), "esperando_aprobacion"),
    (s(definitivos=1, aprobacion_estado="aprobado"), "emision_oc"),
    (s(definitivos=1, aprobacion_estado="aprobado", ocs_creadas=1), "emision_oc"),
    (s(definitivos=1, aprobacion_estado="aprobado", ocs_enviadas=1), "seguimiento"),
])
def test_deriva_la_etapa(senales, esperada):
    assert derivar_etapa(senales) == esperada


def test_evalua_de_la_etapa_mas_avanzada_hacia_atras():
    """Una compra con OC enviada TAMBIÉN tiene definitivos y respuestas: si se
    evaluara al revés quedaría en 'comparacion' para siempre."""
    avanzada = s(rfq_enviadas=3, respuestas_recibidas=3, definitivos=1,
                 aprobacion_estado="aprobado", ocs_creadas=1, ocs_enviadas=1)
    assert derivar_etapa(avanzada) == "seguimiento"


def test_definitivos_incompletos_no_avanzan_a_seleccion():
    assert derivar_etapa(s(items_total=6, definitivos=5, respuestas_recibidas=1)) == "comparacion"


def test_lista_vacia_no_se_declara_lista_para_autorizar():
    assert derivar_etapa(Senales(items_total=0, definitivos=0)) == "busqueda"


# ─── Bloqueos ────────────────────────────────────────────────────────────────

def test_precios_en_conflicto_bloquea():
    """El caso del correo con $19.990 y $25.000 para el mismo ítem."""
    bloqueos = derivar_bloqueos(s(conversaciones_en_conflicto=1), "comparacion")
    assert [b["codigo"] for b in bloqueos] == ["precios_en_conflicto"]
    assert bloqueos[0]["accion"] == "get_quote_lines"


def test_respuesta_no_interpretada_es_un_bloqueo_distinto():
    """Se descubrió con datos reales: la lista del WC estaba en
    `clarification_required` por un timeout del extractor, no por precios en
    conflicto, y el aviso decía "más de un precio" — falso y engañoso."""
    bloqueos = derivar_bloqueos(s(conversaciones_ambiguas=1), "comparacion")
    assert [b["codigo"] for b in bloqueos] == ["respuesta_no_interpretada"]
    assert "más de un precio" not in bloqueos[0]["mensaje"]


def test_los_dos_motivos_de_revision_pueden_convivir():
    bloqueos = derivar_bloqueos(s(conversaciones_en_conflicto=1, conversaciones_ambiguas=1), "comparacion")
    assert {b["codigo"] for b in bloqueos} == {"precios_en_conflicto", "respuesta_no_interpretada"}


def test_oferta_sin_precio_bloquea():
    bloqueos = derivar_bloqueos(s(definitivos=1, definitivos_sin_precio=1), "seleccion_lista")
    assert any(b["codigo"] == "oferta_sin_precio" for b in bloqueos)


def test_aprobacion_pendiente_explica_su_estado():
    bloqueos = derivar_bloqueos(s(aprobacion_estado="rechazado"), "esperando_aprobacion")
    aprobacion = next(b for b in bloqueos if b["codigo"] == "aprobacion_pendiente")
    assert "rechazada" in aprobacion["mensaje"]


def test_falta_de_despacho_solo_bloquea_al_emitir():
    """Antes de la OC no molesta; al emitirla sí, porque saldría sin destino."""
    assert not any(b["codigo"] == "sin_direccion_despacho"
                   for b in derivar_bloqueos(s(tiene_direccion_despacho=False), "comparacion"))
    assert any(b["codigo"] == "sin_direccion_despacho"
               for b in derivar_bloqueos(s(tiene_direccion_despacho=False), "emision_oc"))


def test_proveedor_sin_email_bloquea_el_envio():
    bloqueos = derivar_bloqueos(s(definitivos_sin_email=1, tiene_direccion_despacho=True), "emision_oc")
    assert any(b["codigo"] == "proveedor_sin_email" for b in bloqueos)


def test_compra_sana_no_tiene_bloqueos():
    """Si el camino feliz reporta bloqueos, se aprende a ignorarlos."""
    sana = s(definitivos=1, aprobacion_estado="aprobado", tiene_direccion_despacho=True)
    assert derivar_bloqueos(sana, "emision_oc") == []


def test_todo_bloqueo_nombra_una_accion():
    """Un bloqueo que no dice cómo salir obliga al cliente a adivinar."""
    todos = s(conversaciones_en_conflicto=1, definitivos_sin_precio=1, definitivos_sin_email=1,
              proveedores_sin_homologar=1, aprobacion_estado="pendiente")
    for etapa in ("comparacion", "esperando_aprobacion", "emision_oc"):
        for bloqueo in derivar_bloqueos(todos, etapa):
            assert bloqueo["accion"], f"{bloqueo['codigo']} sin acción"
            assert len(bloqueo["mensaje"]) > 20


# ─── Acciones y orden ────────────────────────────────────────────────────────

def test_las_acciones_son_nombres_de_tools():
    """El valor está en que el cliente pueda ejecutarlas sin traducir."""
    for clave, _ in ETAPAS:
        acciones = acciones_de(clave)
        assert acciones, f"{clave} sin acciones"
        assert all(a.islower() and " " not in a for a in acciones)


def test_separa_completadas_de_pendientes():
    completadas, pendientes = separar_etapas("comparacion")
    assert completadas == ["busqueda", "rfq_preparada", "esperando_cotizaciones"]
    assert "emision_oc" in pendientes
    assert "comparacion" not in completadas + pendientes


def test_la_primera_etapa_no_tiene_completadas():
    completadas, _ = separar_etapas("busqueda")
    assert completadas == []


# ─── Contrato de salida ──────────────────────────────────────────────────────

def test_el_origen_derivado_es_explicito():
    """Sin este marcador, activar `unified` cambiaría las etapas sin aviso."""
    contexto = construir_contexto("lista-1", s())
    assert contexto["origen"] == "derivado"


def test_el_modo_grafo_usa_las_etiquetas_de_la_empresa():
    """En `grafo` mandan los nombres del canvas, no los genéricos de acá."""
    contexto = construir_contexto(
        "lista-1", s(), origen="grafo", etapa="nodo-7",
        etiqueta="Esperando aprobación financiera",
        completadas=["nodo-1"], pendientes=["nodo-9"],
    )
    assert contexto["origen"] == "grafo"
    assert contexto["etapa_label"] == "Esperando aprobación financiera"
    assert contexto["completadas"] == ["nodo-1"]


def test_las_proximas_acciones_priorizan_los_bloqueos():
    contexto = construir_contexto("lista-1", s(conversaciones_en_conflicto=1))
    assert contexto["proximas_acciones"][0]["tool"] == "get_quote_lines"


def test_sin_bloqueos_propone_el_siguiente_paso():
    contexto = construir_contexto("lista-1", s(respuestas_recibidas=1))
    assert contexto["proximas_acciones"][0]["tool"] == "compare_list"


def test_la_respuesta_trae_todas_las_claves_del_contrato():
    contexto = construir_contexto("lista-1", s())
    esperadas = {
        "list_id", "origen", "etapa_actual", "etapa_label", "completadas", "pendientes",
        "bloqueos", "transiciones", "aprobaciones_requeridas", "acciones_disponibles",
        "proximas_acciones", "resumen",
    }
    assert esperadas <= set(contexto)
