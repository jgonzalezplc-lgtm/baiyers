"""El embudo de extracción con varias fuentes (cuerpo + adjuntos).

Lo que se fija acá es que el adjunto entre por el MISMO camino que el cuerpo. Es
la decisión de diseño central de la feature: la cadena
`extraer → detectar conflictos → líneas → aplicar o proponer` costó bugs reales
(el conflicto de precios del 2026-08-26, que dejó un borrador de OC por $25.000
cuando lo cotizado era $19.990) y no se duplica para los adjuntos.
"""
from __future__ import annotations

import asyncio

import pytest

from app.routers import gmail
from app.services.adjunto_parser import Documento

ITEMS = [{"entity_id": "e1", "nombre": "Casco de seguridad", "proveedor": "ACME"}]


class SupabaseFalso:
    """Sólo entiende lo que el helper le pide: leer y actualizar adjuntos."""

    def __init__(self, adjuntos):
        self._adjuntos = adjuntos
        self.updates = []
        self._pendiente = None

    def table(self, nombre):
        assert nombre == "gmail_attachments"
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def update(self, valores):
        self._pendiente = valores
        return self

    def execute(self):
        if self._pendiente is not None:
            self.updates.append(self._pendiente)
            self._pendiente = None
            return type("R", (), {"data": []})()
        return type("R", (), {"data": list(self._adjuntos)})()


def _propuesta(valor, entity="e1", field="precio_unitario", confianza=0.99):
    return {"entity_id": entity, "field": field, "new_value": valor,
            "currency": "CLP", "confidence": confianza, "nota": ""}


def _extraccion(propuestas, respondio_todo=True, requiere_aclaracion=False):
    return {"propuestas": propuestas, "respondio_todo": respondio_todo,
            "requiere_aclaracion": requiere_aclaracion}


@pytest.fixture
def correr(monkeypatch):
    """Corre el helper con extracción y descarga de adjuntos falsas.

    `guion` mapea el filename del documento (o None para el cuerpo) a lo que
    devolvería el modelo para esa fuente.
    """

    def _correr(adjuntos, guion, documentos=None, cuerpo="adjunto valores"):
        documentos = documentos if documentos is not None else {
            a["filename"]: Documento(filename=a["filename"], sha256="a" * 64,
                                     parte={"mime_type": "application/pdf", "data": b"%PDF"})
            for a in adjuntos
        }
        llamadas = []

        async def extraer_falso(cuerpo_recibido, items, *, documento=None):
            llamadas.append({"cuerpo": cuerpo_recibido,
                             "documento": documento.filename if documento else None})
            return guion.get(documento.filename if documento else None, _extraccion([]))

        monkeypatch.setattr(
            "app.services.email_understanding.extraer_actualizaciones", extraer_falso
        )
        monkeypatch.setattr(
            "app.services.adjunto_parser.preparar_adjunto",
            lambda service, mid, adjunto: documentos.get(adjunto["filename"]),
        )
        sb = SupabaseFalso(adjuntos)
        resultado = asyncio.run(gmail._extraer_de_todas_las_fuentes(
            sb, object(), {"id": "conv-1"}, "gmail-msg-1", "row-1", cuerpo, ITEMS,
        ))
        return resultado, sb, llamadas

    return _correr


def _adjunto(filename="cotizacion.pdf", **extra):
    return {"id": "adj-1", "filename": filename, "mime_type": "application/pdf",
            "gmail_attachment_id": "att-1", "texto_extraido": None, **extra}


# ── El caso que motivó la feature ────────────────────────────────────────────

def test_el_precio_del_pdf_llega_aunque_el_cuerpo_no_diga_nada(correr):
    """"Estimado, adjunto cotización": antes esto entraba como una respuesta
    sin datos y alguien transcribía el PDF a mano."""
    resultado, _, _ = correr(
        [_adjunto()],
        {None: _extraccion([]), "cotizacion.pdf": _extraccion([_propuesta("21190")])},
    )
    assert len(resultado["propuestas"]) == 1
    assert resultado["propuestas"][0]["new_value"] == "21190"
    assert resultado["propuestas"][0]["_origen"]["filename"] == "cotizacion.pdf"


def test_la_propuesta_del_cuerpo_no_lleva_origen(correr):
    resultado, _, _ = correr([], {None: _extraccion([_propuesta("21190")])})
    assert resultado["propuestas"][0]["_origen"] is None


def test_al_adjunto_no_se_le_reenvia_el_cuerpo(correr):
    """Si se le mandara, el modelo volvería a extraer del cuerpo los mismos
    datos de la primera llamada y saldrían dos propuestas para un solo hecho."""
    _, _, llamadas = correr([_adjunto()], {}, cuerpo="el precio es 21190")
    del_adjunto = [c for c in llamadas if c["documento"]]
    assert del_adjunto and del_adjunto[0]["cuerpo"] == ""


# ── Conflictos entre fuentes ────────────────────────────────────────────────

def test_cuerpo_y_pdf_con_precios_distintos_quedan_como_conflicto(correr):
    """El efecto secundario buscado de mezclar las fuentes antes de comparar.

    Es el mismo escenario del bug de 2026-08-26, pero repartido entre dos
    fuentes en vez de dos líneas del mismo texto.
    """
    resultado, _, _ = correr(
        [_adjunto()],
        {None: _extraccion([_propuesta("25000")]),
         "cotizacion.pdf": _extraccion([_propuesta("19990")])},
    )
    conflictos = gmail._campos_en_conflicto(resultado["propuestas"], "e1")
    assert ("e1", "precio_unitario") in conflictos


def test_el_mismo_precio_en_dos_fuentes_no_es_un_conflicto(correr):
    resultado, _, _ = correr(
        [_adjunto()],
        {None: _extraccion([_propuesta("21190")]),
         "cotizacion.pdf": _extraccion([_propuesta("21190")])},
    )
    assert gmail._campos_en_conflicto(resultado["propuestas"], "e1") == set()


def test_un_dato_repetido_no_genera_dos_propuestas(correr):
    """Mismo ítem, mismo campo, mismo valor = un solo hecho que revisar."""
    resultado, _, _ = correr(
        [_adjunto()],
        {None: _extraccion([_propuesta("21190")]),
         "cotizacion.pdf": _extraccion([_propuesta("21190")])},
    )
    assert len(resultado["propuestas"]) == 1


# ── Idempotencia: lo que protege la factura de Gemini ───────────────────────

def test_un_adjunto_ya_parseado_no_se_vuelve_a_procesar(correr):
    """El cron corre cada minuto sobre todos los usuarios: sin esto, cada
    conversación abierta re-parsearía sus adjuntos para siempre."""
    _, _, llamadas = correr(
        [_adjunto(texto_extraido="[procesado como application/pdf · sha256:abc]")],
        {None: _extraccion([])},
    )
    assert [c["documento"] for c in llamadas] == [None], "se volvió a llamar al modelo"


def test_procesar_un_adjunto_deja_su_rastro_de_auditoria(correr):
    _, sb, _ = correr([_adjunto()], {"cotizacion.pdf": _extraccion([_propuesta("21190")])})
    assert len(sb.updates) == 1
    assert "application/pdf" in sb.updates[0]["texto_extraido"]
    assert sb.updates[0]["hash"] == "a" * 64


# ── Robustez: el adjunto nunca puede tumbar la sincronización ───────────────

def test_un_adjunto_ilegible_no_impide_procesar_el_cuerpo(correr, monkeypatch):
    resultado, _, _ = correr(
        [_adjunto()],
        {None: _extraccion([_propuesta("21190")])},
        documentos={},  # preparar_adjunto devuelve None
    )
    assert len(resultado["propuestas"]) == 1
    assert resultado["propuestas"][0]["_origen"] is None


def test_si_explota_el_parseo_del_adjunto_el_cuerpo_igual_vale(monkeypatch):
    async def extraer_falso(cuerpo, items, *, documento=None):
        return _extraccion([_propuesta("21190")] if documento is None else [])

    def explota(service, mid, adjunto):
        raise RuntimeError("PDF corrupto")

    monkeypatch.setattr("app.services.email_understanding.extraer_actualizaciones", extraer_falso)
    monkeypatch.setattr("app.services.adjunto_parser.preparar_adjunto", explota)

    resultado = asyncio.run(gmail._extraer_de_todas_las_fuentes(
        SupabaseFalso([_adjunto()]), object(), {"id": "c"}, "g", "row-1", "hola", ITEMS,
    ))
    assert len(resultado["propuestas"]) == 1


def test_si_no_se_pueden_leer_los_adjuntos_el_cuerpo_igual_vale(monkeypatch):
    async def extraer_falso(cuerpo, items, *, documento=None):
        return _extraccion([_propuesta("21190")])

    class SupabaseRoto:
        def table(self, _):
            raise RuntimeError("supabase caído")

    monkeypatch.setattr("app.services.email_understanding.extraer_actualizaciones", extraer_falso)
    resultado = asyncio.run(gmail._extraer_de_todas_las_fuentes(
        SupabaseRoto(), object(), {"id": "c"}, "g", "row-1", "hola", ITEMS,
    ))
    assert len(resultado["propuestas"]) == 1


# ── Umbral diferenciado ─────────────────────────────────────────────────────

def test_el_umbral_del_adjunto_es_mas_exigente_que_el_del_cuerpo():
    """Se fija el número acá porque vive dentro de `_sincronizar_usuario` y no
    hay otra forma de que un cambio silencioso rompa algo."""
    import inspect

    fuente = inspect.getsource(gmail._sincronizar_usuario)
    assert "UMBRAL_AUTO_APLICAR = 0.85" in fuente
    assert "UMBRAL_AUTO_APLICAR_ADJUNTO = 0.95" in fuente
    # El umbral se elige por origen, no está fijo.
    assert "UMBRAL_AUTO_APLICAR_ADJUNTO if origen else UMBRAL_AUTO_APLICAR" in fuente
