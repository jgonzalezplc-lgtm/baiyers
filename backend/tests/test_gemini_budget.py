"""El medidor de gasto avisa, y sobre todo NO rompe ni bloquea llamadas.

La propiedad más importante acá no es que el número sea exacto —es una
estimación por proceso— sino que envolver el SDK sea inocuo: si este wrapper
tira una excepción, se cae toda la identificación de ítems, que es el corazón
del producto.
"""
import asyncio

import pytest

from app.services import gemini_budget


@pytest.fixture(autouse=True)
def contador_limpio():
    gemini_budget._dia = None
    gemini_budget._gasto_usd = gemini_budget.Decimal("0")
    gemini_budget._llamadas = 0
    gemini_budget._avisados.clear()
    yield


def test_acumula_y_no_avisa_por_debajo_del_escalon(capsys):
    gemini_budget.registrar("gemini-2.5-flash", 1_000, 500)
    assert "ALERTA" not in capsys.readouterr().out
    assert gemini_budget.estado()["llamadas"] == 1
    assert gemini_budget.estado()["gasto_estimado_usd"] > 0


def test_avisa_una_sola_vez_por_escalon(capsys):
    # A USD 0,30/2,50 por millón, 20M tokens de salida son USD 50: cruza los
    # escalones de 5, 20 y 50 de una.
    gemini_budget.registrar("gemini-2.5-flash", 0, 20_000_000)
    salida = capsys.readouterr().out
    assert salida.count("ALERTA") == 3

    # Seguir gastando dentro del mismo tramo no vuelve a avisar.
    gemini_budget.registrar("gemini-2.5-flash", 0, 1_000)
    assert "ALERTA" not in capsys.readouterr().out


def test_el_contador_se_reinicia_al_cambiar_el_dia(monkeypatch):
    import datetime

    monkeypatch.setattr(gemini_budget, "_hoy", lambda: datetime.date(2026, 8, 25))
    gemini_budget.registrar("gemini-2.5-flash", 0, 20_000_000)
    assert gemini_budget.estado()["gasto_estimado_usd"] > 40

    monkeypatch.setattr(gemini_budget, "_hoy", lambda: datetime.date(2026, 8, 26))
    gemini_budget.registrar("gemini-2.5-flash", 0, 1_000)
    estado = gemini_budget.estado()
    assert estado["gasto_estimado_usd"] < 1
    assert estado["escalones_avisados"] == []


def test_un_fallo_del_medidor_no_propaga(monkeypatch, capsys):
    """Si el catálogo de precios cambia de forma o Supabase se cae, la llamada
    a Gemini tiene que seguir funcionando igual."""
    def explota(*_a, **_k):
        raise RuntimeError("catálogo roto")

    monkeypatch.setattr(
        "app.services.control_plane_telemetry.estimar_costo_usd", explota,
    )
    gemini_budget.registrar("gemini-2.5-flash", 10, 10)   # no debe lanzar
    assert "no se pudo contabilizar" in capsys.readouterr().out


# ─── El wrapper del SDK ──────────────────────────────────────────────────────

class _Uso:
    prompt_token_count = 100
    candidates_token_count = 200


class _Respuesta:
    usage_metadata = _Uso()
    text = "respuesta real"


class _ModeloFalso:
    """Imita lo justo del `GenerativeModel` del SDK."""
    model_name = "models/gemini-2.5-flash"

    def generate_content(self, *args, **kwargs):
        return _Respuesta()

    async def generate_content_async(self, *args, **kwargs):
        return _Respuesta()


def _instrumentar_clase(cls):
    """Aplica el mismo envoltorio de `instrumentar()` sobre una clase de prueba,
    sin depender de que el SDK real esté instalado."""
    for nombre, es_async in (("generate_content", False), ("generate_content_async", True)):
        original = getattr(cls, nombre)
        if es_async:
            async def envuelto(self, *a, _o=original, **k):
                r = await _o(self, *a, **k)
                e, s = gemini_budget._tokens(r)
                gemini_budget.registrar(gemini_budget._nombre_modelo(self), e, s)
                return r
        else:
            def envuelto(self, *a, _o=original, **k):
                r = _o(self, *a, **k)
                e, s = gemini_budget._tokens(r)
                gemini_budget.registrar(gemini_budget._nombre_modelo(self), e, s)
                return r
        setattr(cls, nombre, envuelto)


def test_el_wrapper_devuelve_la_respuesta_intacta_y_cuenta():
    _instrumentar_clase(_ModeloFalso)
    modelo = _ModeloFalso()

    assert modelo.generate_content("hola").text == "respuesta real"
    assert asyncio.run(modelo.generate_content_async("hola")).text == "respuesta real"
    assert gemini_budget.estado()["llamadas"] == 2


def test_instrumentar_es_idempotente():
    """Llamarlo dos veces no debe apilar wrappers y contar doble."""
    gemini_budget.instrumentar()
    gemini_budget.instrumentar()

    import google.generativeai as genai
    metodo = genai.GenerativeModel.generate_content
    assert getattr(metodo, "_baiyer_medido", False) is True


def test_el_nombre_del_modelo_pierde_el_prefijo():
    class M:
        model_name = "models/gemini-2.5-flash"

    assert gemini_budget._nombre_modelo(M()) == "gemini-2.5-flash"
