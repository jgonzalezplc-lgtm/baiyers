"""El `state` de los flujos OAuth de correo tiene que ser infalsificable.

Sin esto, alguien completa el consentimiento con SU cuenta de Google y deja sus
tokens en la fila `user_integrations` de otra empresa: las RFQ y OC de la
víctima empiezan a salir desde el buzón del atacante y el agente de Gmail
ingiere correo que él controla como si fueran cotizaciones de proveedores.
"""
import base64
import json
import time

import pytest

from app.services.oauth_state import VIGENCIA_SEGUNDOS, firmar_state, verificar_state


def test_ida_y_vuelta():
    state = firmar_state("usuario-1", "verifier-1", "/onboarding")
    datos = verificar_state(state)
    assert datos["u"] == "usuario-1"
    assert datos["v"] == "verifier-1"
    assert datos["n"] == "/onboarding"


def test_state_sin_firmar_se_rechaza():
    """El formato viejo: `base64(json)` a secas, que es lo que un atacante
    escribe a mano con el UUID de la víctima."""
    falso = base64.urlsafe_b64encode(
        json.dumps({"u": "victima", "v": "cualquiera", "n": "/dashboard"}).encode()
    ).decode()
    assert verificar_state(falso) is None


def test_no_se_puede_cambiar_el_user_id_conservando_la_firma():
    state = firmar_state("usuario-1", "verifier-1", "/dashboard")
    payload, firma = state.split(".", 1)
    datos = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode())
    datos["u"] = "victima"
    payload_falso = base64.urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()
    assert verificar_state(f"{payload_falso}.{firma}") is None


def test_state_vencido_se_rechaza(monkeypatch):
    state = firmar_state("usuario-1", "verifier-1", "/dashboard")
    ahora = time.time()
    monkeypatch.setattr(time, "time", lambda: ahora + VIGENCIA_SEGUNDOS + 1)
    assert verificar_state(state) is None


@pytest.mark.parametrize("basura", ["", ".", "sin-punto", "a.b", "..."])
def test_basura_no_lanza(basura):
    assert verificar_state(basura) is None
