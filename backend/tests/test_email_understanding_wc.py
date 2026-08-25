"""Regresión del correo real de cotización del WC (2026-08-25).

Contexto del bug que cubren estas pruebas: el correo llegó bien y el batch RFQ tenía
sus 6 ítems, pero `extraer_actualizaciones` se caía por `asyncio.TimeoutError` contra un
timeout de 25s (el correo mide ~20.7s, dominado por tokens de thinking). El `except`
devolvía `vacio_seguro`, que produce exactamente el síntoma observado:
`propuestas_generadas: 0` + conversación en `clarification_required` sin propuestas
pendientes. `TimeoutError` además stringifica a "", así que el log no decía nada.
"""
import asyncio
import json

import pytest

from app.services import email_understanding as eu

# Cuerpo textual exacto del mensaje inbound e5509195-f876-42f4-957c-1e53ab0f2b9d.
CORREO_WC = (
    "Hola\r\n\r\nSi tenemos !\r\n\r\n"
    "-wc one piece : 150.000 la unidad\r\n"
    "-flexible de agua: 8.000 la unidad\r\n"
    "-llave de paso angular: 2.000 la unidad\r\n"
    "- sello para wc: 1750 la unidad\r\n"
    "- kit de pernos de fijación: no tenemos\r\n"
    "- silicona sanitaria: 2.500 la unidad\r\n\r\n"
    "Puedes comprar directo en este link, o si trabajar con OC la puedes\r\n"
    "adjuntar a este correo.\r\n\r\n"
    "Los despachos son 24h hábiles después de recibido el pago o la OC\r\n\r\nSaludos\r\n"
)

# Los 6 ítems reales del rfq_batch 6ddddfbb-a4c7-444a-b51e-6ab209b07ff1.
ITEMS_WC = [
    {"entity_id": "13c40311", "nombre": "WC one-piece descarga a piso", "proveedor": "Joaquín González"},
    {"entity_id": "84097dc1", "nombre": "Flexible de agua 1/2 x 7/8", "proveedor": "Joaquín González"},
    {"entity_id": "05fa5270", "nombre": "Llave angular 1/2", "proveedor": "Joaquín González"},
    {"entity_id": "6c533ef4", "nombre": "Sello o brida para WC", "proveedor": "Joaquín González"},
    {"entity_id": "7a8d49c5", "nombre": "Kit de pernos de fijación para WC", "proveedor": "Joaquín González"},
    {"entity_id": "da10c649", "nombre": "Silicona sanitaria", "proveedor": "Joaquín González"},
]

PRECIOS_ESPERADOS = {
    "13c40311": 150000.0,
    "84097dc1": 8000.0,
    "05fa5270": 2000.0,
    "6c533ef4": 1750.0,
    "da10c649": 2500.0,
}


# ─── Normalización de montos CLP (determinística, sin LLM) ────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    ("150.000", 150000.0),
    ("8.000", 8000.0),
    ("1750", 1750.0),
    ("2.500", 2500.0),
    ("$ 150.000 la unidad", 150000.0),
    ("150.000 CLP c/u", 150000.0),
    # La coma es decimal en Chile; el punto es separador de miles.
    ("1.234,56", 1234.56),
    ("150,5", 150.5),
    # Un punto con menos de 3 dígitos al final NO es separador de miles.
    ("150.5", 150.5),
    (150000, 150000.0),
    ("no tenemos", None),
    ("", None),
])
def test_normalizar_monto(crudo, esperado):
    assert eu.normalizar_monto(crudo) == esperado


def test_precio_no_numerico_se_descarta():
    """'no tenemos' en precio_unitario no puede colarse como monto."""
    p = {"field": "precio_unitario", "new_value": "no tenemos", "confidence": 0.9}
    assert eu._filtrar_propuesta(p) is None


def test_precio_se_normaliza_al_filtrar():
    p = {"field": "precio_unitario", "new_value": "150.000", "currency": "CLP", "confidence": 0.95}
    assert eu._filtrar_propuesta(p)["new_value"] == 150000.0


def test_entity_id_vacio_se_vuelve_none():
    """El schema usa "" como centinela porque Gemini responde peor con nullables."""
    p = {"entity_id": "", "field": "plazo_entrega", "new_value": "24h", "confidence": 0.8}
    assert eu._filtrar_propuesta(p)["entity_id"] is None


# ─── Contrato de fallo: por qué se veía clarification_required ────────────────

def _correr(monkeypatch, fake_model):
    monkeypatch.setattr("app.config.settings.gemini_api_key", "test-key", raising=False)
    import google.generativeai as genai
    monkeypatch.setattr(genai, "configure", lambda **_: None)
    monkeypatch.setattr(genai, "GenerativeModel", lambda *a, **k: fake_model)
    return asyncio.run(eu.extraer_actualizaciones(CORREO_WC, ITEMS_WC))


class _ModeloFake:
    """Devuelve respuestas encoladas; una excepción encolada se lanza."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    async def generate_content_async(self, _prompt):
        self.llamadas += 1
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return type("Resp", (), {"text": r})()


def _payload_ok():
    propuestas = [
        {"entity_id": eid, "field": "precio_unitario", "new_value": f"{int(v)}",
         "currency": "CLP", "confidence": 0.95, "nota": ""}
        for eid, v in PRECIOS_ESPERADOS.items()
    ]
    propuestas.append({"entity_id": "7a8d49c5", "field": "disponibilidad",
                       "new_value": "no_disponible", "currency": "", "confidence": 0.95, "nota": ""})
    return json.dumps({"propuestas": propuestas, "respondio_todo": True,
                       "requiere_aclaracion": False})


def test_timeout_agotado_devuelve_vacio_seguro(monkeypatch):
    """El síntoma original: 0 propuestas + requiere_aclaracion, nunca datos inventados."""
    fake = _ModeloFake(asyncio.TimeoutError(), asyncio.TimeoutError())
    r = _correr(monkeypatch, fake)
    assert r["propuestas"] == []
    assert r["requiere_aclaracion"] is True
    assert fake.llamadas == eu.INTENTOS_EXTRACCION


def test_reintenta_tras_un_timeout(monkeypatch):
    """Un timeout aislado ya no pierde el correo entero."""
    fake = _ModeloFake(asyncio.TimeoutError(), _payload_ok())
    r = _correr(monkeypatch, fake)
    assert fake.llamadas == 2
    assert r["requiere_aclaracion"] is False
    assert len(r["propuestas"]) == 6


def test_timeout_es_holgado_para_el_correo_real():
    """~20.7s medidos contra los 25s originales: el margen era el bug."""
    assert eu.TIMEOUT_EXTRACCION >= 60.0


def test_error_de_extraccion_loguea_el_tipo(monkeypatch, capsys):
    """TimeoutError tiene str() vacío; sin el tipo el log queda mudo."""
    _correr(monkeypatch, _ModeloFake(asyncio.TimeoutError(), asyncio.TimeoutError()))
    assert "TimeoutError" in capsys.readouterr().out


# ─── Extracción completa sobre el correo real ────────────────────────────────

def test_extrae_cinco_precios_y_un_sin_stock(monkeypatch):
    r = _correr(monkeypatch, _ModeloFake(_payload_ok()))

    precios = {p["entity_id"]: p["new_value"]
               for p in r["propuestas"] if p["field"] == "precio_unitario"}
    assert precios == PRECIOS_ESPERADOS
    assert all(p["currency"] == "CLP" for p in r["propuestas"] if p["field"] == "precio_unitario")

    sin_stock = [p for p in r["propuestas"] if p["field"] == "disponibilidad"]
    assert len(sin_stock) == 1
    assert sin_stock[0]["entity_id"] == "7a8d49c5"  # kit de pernos
    assert "7a8d49c5" not in precios  # el ítem sin stock nunca lleva precio

    # Criterio de aceptación: OC por 164.250 excluyendo el kit de pernos.
    assert sum(precios.values()) == 164250.0


def test_respuesta_sin_json_valido_no_inventa_datos(monkeypatch):
    r = _correr(monkeypatch, _ModeloFake("no soy json", "tampoco"))
    assert r["propuestas"] == []
    assert r["requiere_aclaracion"] is True


def test_sin_items_de_contexto_no_llama_al_modelo(monkeypatch):
    monkeypatch.setattr("app.config.settings.gemini_api_key", "test-key", raising=False)
    assert asyncio.run(eu.extraer_actualizaciones(CORREO_WC, []))["requiere_aclaracion"] is True
