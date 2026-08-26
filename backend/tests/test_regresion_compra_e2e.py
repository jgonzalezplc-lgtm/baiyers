"""Regresión del flujo completo de compra, sobre el caso real de la ampolleta.

Recorre los diez pasos del caso obligatorio con un Supabase en memoria: lo que
una etapa escribe es lo que lee la siguiente. Los límites externos —Gemini y
Gmail— se sustituyen; todo lo demás es el código real.

Origen (2026-08-26): el usuario pidió una ampolleta LED E27 equivalente a 100 W.
Joaquín respondió con DOS productos en un mismo correo (E27 estándar $19.990 y
E27/E40 alta potencia $25.000), el sistema los colapsó en una sola oferta, y el
borrador de OC quedó en $25.000 cuando lo elegido era $19.990.
"""
import json

import pytest
from fastapi import HTTPException

from app.services import contexto_compra_service as contexto_svc
from app.services import quote_lines_service as lineas_svc
from app.services.contexto_compra import derivar_etapa
from app.services.mcp_context import ApplicationActorContext
from app.services.quote_lines import ESTADO_SELECCIONADA, agrupar_en_lineas
from tests.fake_supabase import FakeSupabase

USER = "2661668d-2a57-4144-86ac-4d61e1cf846f"
LISTA = "lista-ampolleta"
COTIZACION = "cot-ampolleta"
RESULTADO = "res-joaquin"
MENSAJE = "msg-joaquin"


def actor():
    return ApplicationActorContext(USER, "org-1", "Vital", (USER,), client_id="codex")


# Lo que el extractor devuelve para el correo real de Joaquín. Se fija acá en vez
# de llamar a Gemini: la prueba verifica el flujo, no el modelo.
PROPUESTAS_DEL_CORREO = [
    {"entity_id": RESULTADO, "field": "precio_unitario", "new_value": 19990.0,
     "currency": "CLP", "confidence": 1.0, "nota": "E27 estándar de 100 W"},
    {"entity_id": RESULTADO, "field": "precio_unitario", "new_value": 25000.0,
     "currency": "CLP", "confidence": 1.0, "nota": "E27/E40 alta potencia"},
    {"entity_id": RESULTADO, "field": "plazo_entrega", "new_value": "48h desde la recepción de la OC",
     "currency": None, "confidence": 0.9, "nota": ""},
]


@pytest.fixture
def sb():
    """Base con la lista creada y la RFQ ya enviada a Joaquín."""
    lista_json = json.dumps({
        "tipo": "lista_cotizacion",
        "items": [{"cotizacion_id": COTIZACION, "nombre": "Ampolleta LED E27 100W", "cantidad": 1}],
        "definitivos": {},
    }, ensure_ascii=False)
    return FakeSupabase(
        proyectos=[{"id": LISTA, "user_id": USER, "nombre": "Ampolleta LED Cocina",
                    "descripcion": lista_json, "estado": "cotizando", "monto_total": 0}],
        cotizaciones=[{"id": COTIZACION, "user_id": USER,
                       "nombre_identificado": "Ampolleta LED E27 100W"}],
        resultados=[{"id": RESULTADO, "cotizacion_id": COTIZACION,
                     "proveedor_nombre": "Joaquín González",
                     "proveedor_email": "joaquin.gonzalez.pl@usach.cl",
                     "precio": None, "precio_cotizado": None}],
        gmail_messages=[{"id": MENSAJE, "direction": "inbound"}],
        rfq_batches=[{"id": "rfq-1", "lista_proyecto_id": LISTA, "estado": "sent",
                      "proveedor_id": "prov-joaquin"}],
        gmail_conversations=[{"id": "conv-1", "lista_proyecto_id": LISTA,
                              "estado": "supplier_replied"}],
        ordenes_compra=[],
        quote_lines=[],
    )


def _registrar_respuesta(sb):
    return lineas_svc.registrar_desde_correo(
        sb, user_id=USER, propuestas=PROPUESTAS_DEL_CORREO,
        entity_a_cotizacion={RESULTADO: COTIZACION},
        proveedor_nombre="Joaquín González",
        proveedor_email="joaquin.gonzalez.pl@usach.cl",
        mensaje_id=MENSAJE,
    )


# ─── Pasos 5 y 6: dos ofertas → dos líneas independientes ────────────────────

def test_paso_5_y_6_dos_ofertas_producen_dos_lineas(sb):
    """El corazón del caso: ninguna oferta pisa a la otra."""
    _registrar_respuesta(sb)
    lineas = lineas_svc.listar_por_item(sb, actor(), COTIZACION)

    assert len(lineas) == 2
    assert sorted(l["precio"] for l in lineas) == [19990.0, 25000.0]
    assert all(l["source_message_id"] == MENSAJE for l in lineas)
    # Cada línea conserva QUÉ producto era: sin esto son dos números sueltos.
    descripciones = " ".join(l["descripcion_normalizada"] or "" for l in lineas)
    assert "estándar" in descripciones and "alta potencia" in descripciones


def test_el_plazo_se_comparte_entre_las_dos_lineas(sb):
    """El proveedor lo enunció una sola vez para toda su cotización."""
    _registrar_respuesta(sb)
    lineas = lineas_svc.listar_por_item(sb, actor(), COTIZACION)
    assert all("48h" in (l["plazo_entrega"] or "") for l in lineas)


def test_resincronizar_el_correo_no_duplica(sb):
    """El cron corre cada minuto: el mismo mensaje se reprocesa."""
    _registrar_respuesta(sb)
    _registrar_respuesta(sb)
    assert len(lineas_svc.listar_por_item(sb, actor(), COTIZACION)) == 2


def test_ningun_precio_se_aplica_solo_al_resultado(sb):
    """El bug original: `resultados` quedaba con el último precio del texto."""
    _registrar_respuesta(sb)
    resultado = sb.filas("resultados")[0]
    assert resultado["precio_cotizado"] is None
    assert resultado["precio"] is None


# ─── Paso 7: el usuario elige la de $19.990 ──────────────────────────────────

def test_paso_7_selecciona_la_linea_barata(sb):
    _registrar_respuesta(sb)
    barata = min(lineas_svc.listar_por_item(sb, actor(), COTIZACION), key=lambda l: l["precio"])

    elegida = lineas_svc.seleccionar(sb, actor(), barata["id"])

    assert elegida["precio"] == 19990.0
    assert elegida["estado"] == ESTADO_SELECCIONADA
    otras = [l for l in sb.filas("quote_lines") if l["id"] != barata["id"]]
    assert all(l["estado"] != ESTADO_SELECCIONADA for l in otras)


def test_reemplazar_la_seleccion_libera_la_anterior_sin_borrarla(sb):
    """Cambiar de decisión tiene que quedar auditable."""
    _registrar_respuesta(sb)
    lineas = sorted(lineas_svc.listar_por_item(sb, actor(), COTIZACION), key=lambda l: l["precio"])
    lineas_svc.seleccionar(sb, actor(), lineas[0]["id"])
    lineas_svc.seleccionar(sb, actor(), lineas[1]["id"])

    guardadas = {l["id"]: l["estado"] for l in sb.filas("quote_lines")}
    assert guardadas[lineas[1]["id"]] == ESTADO_SELECCIONADA
    assert guardadas[lineas[0]["id"]] == "vigente"
    assert len(sb.filas("quote_lines")) == 2, "ninguna se borró"


def test_una_linea_sin_stock_no_puede_elegirse(sb):
    """El 'kit de pernos: no tenemos' no puede terminar en una OC."""
    lineas_svc.registrar_desde_correo(
        sb, user_id=USER,
        propuestas=[{"entity_id": RESULTADO, "field": "disponibilidad",
                     "new_value": "no_disponible", "currency": None,
                     "confidence": 1.0, "nota": ""}],
        entity_a_cotizacion={RESULTADO: COTIZACION},
        proveedor_nombre="Joaquín González", proveedor_email="j@usach.cl",
        mensaje_id="msg-sin-stock",
    )
    sin_stock = lineas_svc.listar_por_item(sb, actor(), COTIZACION)[0]
    with pytest.raises(HTTPException) as error:
        lineas_svc.seleccionar(sb, actor(), sin_stock["id"])
    assert error.value.detail["error"] == "linea_no_seleccionable"


# ─── Pasos 8 y 9: la OC no sale sin aprobación ni sin datos ──────────────────

def test_paso_8_sin_aprobacion_la_etapa_no_llega_a_emision(sb):
    """El grafo exige aprobación: la compra no puede saltar a emitir la OC."""
    _registrar_respuesta(sb)
    senales = contexto_svc._leer_senales(
        sb, actor(), {"id": LISTA, "items": [{"cotizacion_id": COTIZACION}],
                      "definitivos": {COTIZACION: {"resultado_id": RESULTADO, "precio": 19990.0}},
                      "aprobacion": {}},
    )
    assert derivar_etapa(senales) != "emision_oc"


def test_paso_9_sin_direccion_de_despacho_se_avisa_al_emitir(monkeypatch, sb):
    """La OC saldría sin destino; no se infiere de la dirección administrativa."""
    monkeypatch.setattr(contexto_svc, "_tiene_despacho", lambda _actor: False)
    monkeypatch.setattr(contexto_svc, "_contexto_de_grafo", lambda *_a, **_k: None)
    lista = {"id": LISTA, "items": [{"cotizacion_id": COTIZACION}],
             "definitivos": {COTIZACION: {"resultado_id": RESULTADO, "precio": 19990.0}},
             "aprobacion": {"estado": "aprobado"}}

    proceso = contexto_svc.bloque_proceso(sb, actor(), LISTA, lista=lista)["process"]

    assert proceso["etapa_actual"] == "emision_oc"
    assert any(b["codigo"] == "sin_direccion_despacho" for b in proceso["bloqueos"])


def test_el_contexto_refleja_el_avance_paso_a_paso(monkeypatch, sb):
    """La etapa acompaña la compra en vez de quedarse fija."""
    monkeypatch.setattr(contexto_svc, "_contexto_de_grafo", lambda *_a, **_k: None)
    monkeypatch.setattr(contexto_svc, "_tiene_despacho", lambda _actor: True)
    base = {"id": LISTA, "items": [{"cotizacion_id": COTIZACION}], "definitivos": {}, "aprobacion": {}}

    def etapa(lista):
        return contexto_svc.bloque_proceso(sb, actor(), LISTA, lista=lista)["process"]["etapa_actual"]

    assert etapa(base) == "comparacion"
    con_definitivo = {**base, "definitivos": {COTIZACION: {"resultado_id": RESULTADO, "precio": 19990.0}}}
    assert etapa(con_definitivo) == "seleccion_lista"
    assert etapa({**con_definitivo, "aprobacion": {"estado": "pendiente"}}) == "esperando_aprobacion"
    assert etapa({**con_definitivo, "aprobacion": {"estado": "aprobado"}}) == "emision_oc"


# ─── Paso 10: nada se envía sin instrucción explícita ────────────────────────

def test_paso_10_registrar_la_respuesta_no_envia_correos(sb):
    """Ninguna escritura de esta prueba pasó por Gmail: si algún día el registro
    de líneas dispara un envío, este test lo detecta antes que un proveedor."""
    _registrar_respuesta(sb)
    assert sb.filas("gmail_messages") == [{"id": MENSAJE, "direction": "inbound"}]


def test_la_seleccion_no_envia_correos(sb):
    _registrar_respuesta(sb)
    linea = lineas_svc.listar_por_item(sb, actor(), COTIZACION)[0]
    lineas_svc.seleccionar(sb, actor(), linea["id"])
    assert not [m for m in sb.filas("gmail_messages") if m.get("direction") == "outbound"]


# ─── Paso 2: distinguir "equivalente a 100 W" de "100 W reales" ──────────────

def test_paso_2_la_distincion_de_potencia_no_es_deterministica():
    """Documenta una brecha real, en vez de fingir cobertura.

    En la sesión original quien distinguió "equivalente a 100 W" de "100 W
    reales" fue el modelo leyendo los títulos, no una regla de Baiyer. No existe
    hoy normalización de especificaciones que lo garantice: es lo que resolvería
    `normalizedSpecification` del diseño de QuoteLine, todavía sin implementar.
    """
    lineas = agrupar_en_lineas([
        {"entity_id": RESULTADO, "field": "precio_unitario", "new_value": 2990.0,
         "currency": "CLP", "confidence": 1.0, "nota": "15 W equivalente a 100 W"},
        {"entity_id": RESULTADO, "field": "precio_unitario", "new_value": 21190.0,
         "currency": "CLP", "confidence": 1.0, "nota": "100 W reales"},
    ])[RESULTADO]

    # Quedan como dos líneas separadas y con su descripción, que es lo que
    # permite decidir. Baiyer NO marca cuál es cuál.
    assert len(lineas) == 2
    assert all(l["descripcion_normalizada"] for l in lineas)
