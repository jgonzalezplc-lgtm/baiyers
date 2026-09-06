from app.mcp.welcome import BANNER, bienvenida
from app.services.mcp_context import ApplicationActorContext


def test_bienvenida_muestra_banner_y_organizacion():
    actor = ApplicationActorContext("u-1", "org-1", "Acme", ("u-1",), scopes=frozenset({"lists:read"}))
    resultado = bienvenida(actor)
    assert resultado["banner"] == BANNER
    assert resultado["organizacion"] == "Acme"
    assert "Cotizar" in resultado["capacidades"][0]
