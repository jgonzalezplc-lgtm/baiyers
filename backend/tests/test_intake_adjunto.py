"""La puerta de entrada correcta cuando el usuario adjunta un documento.

Caso real (2026-08-26): el usuario adjuntó un PDF de un proyecto solar con 15
ítems ya itemizados (6,5 kWp, inversor 5 kW). El cliente MCP llamó
`start_project_intake` con un resumen en texto en vez de `preview_document_import`
con el archivo. Como `identify_intake` enciende el modo de cubicación cuando NO
hay archivo, Baiyer entró a dimensionar desde cero y preguntó el consumo en
kWh/mes — un dato que estaba en la página 1 del PDF y que, con las cantidades ya
dadas, no hacía ninguna falta. Costó 57 segundos y un turno completo.
"""
import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import project_intake as pi
from app.services.mcp_context import ApplicationActorContext


def actor():
    return ApplicationActorContext("user-1", "org-1", "Org", ("owner", "user-1"), client_id="codex")


TEXTO_REAL = "necesito comprar lo adjunto, usa el mcp de baiyer y dame un presupuesto estimado"


# ─── Detección ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    TEXTO_REAL,
    "Adjunto el PDF con la cotización del proyecto solar.",
    "Te paso el documento con los 15 ítems.",
    "Revisa el archivo que envío.",
    "En la planilla están las cantidades.",
    "Adjunté el excel con el detalle.",
])
def test_detecta_que_hay_un_documento(texto):
    assert pi.menciona_adjunto(texto) is True


@pytest.mark.parametrize("texto", [
    "Necesito 10 ampolletas LED E27 de 100 W, luz fría.",
    "Quiero instalar paneles solares en Puerto Varas.",
    "Cotiza un WC one-piece con descarga a piso.",
    "",
    None,
])
def test_no_bloquea_un_intake_legitimo(texto):
    """Un falso positivo acá cierra la puerta de entrada por texto."""
    assert pi.menciona_adjunto(texto) is False


# ─── Comportamiento del corte ────────────────────────────────────────────────

def _start(monkeypatch, descripcion, **kwargs):
    llamadas = []

    async def fake_identify(*_a, **_k):
        llamadas.append(1)
        return {"estado_flujo": "requiere_datos", "lista_items": []}

    monkeypatch.setattr(pi, "identify_intake", fake_identify)
    monkeypatch.setattr(pi, "create_draft", lambda *_a, **_k: {"id": "draft-1"})
    resultado = asyncio.run(pi.start_project_intake(
        MagicMock(), actor(), description=descripcion, **kwargs,
    ))
    return resultado, llamadas


def test_corta_antes_de_llamar_al_modelo(monkeypatch):
    """Seguir cuesta una llamada a Gemini y un turno para preguntar de más."""
    with pytest.raises(HTTPException) as error:
        _start(monkeypatch, TEXTO_REAL)
    assert error.value.status_code == 409
    assert error.value.detail["error"] == "documento_no_adjuntado"


def test_el_error_nombra_la_tool_correcta(monkeypatch):
    """Un 409 que no dice qué hacer obliga al modelo a adivinar."""
    with pytest.raises(HTTPException) as error:
        _start(monkeypatch, TEXTO_REAL)
    assert error.value.detail["accion"] == "preview_document_import"
    assert "preview_document_import" in error.value.detail["mensaje"]


def test_no_gasta_la_llamada_al_modelo(monkeypatch):
    llamadas = []

    async def fake_identify(*_a, **_k):
        llamadas.append(1)
        return {"estado_flujo": "listo", "lista_items": []}

    monkeypatch.setattr(pi, "identify_intake", fake_identify)
    with pytest.raises(HTTPException):
        asyncio.run(pi.start_project_intake(MagicMock(), actor(), description=TEXTO_REAL))
    assert llamadas == [], "no debe llegar a Gemini"


def test_override_para_quien_no_tiene_el_archivo(monkeypatch):
    """Sin salida explícita, esto sería un callejón sin salida."""
    _, llamadas = _start(monkeypatch, TEXTO_REAL, sin_archivo_disponible=True)
    assert llamadas == [1]


def test_intake_por_texto_sigue_funcionando(monkeypatch):
    _, llamadas = _start(monkeypatch, "Necesito 10 ampolletas LED E27 100 W luz fría")
    assert llamadas == [1]
