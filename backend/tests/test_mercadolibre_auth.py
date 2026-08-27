"""MercadoLibre dejó de aceptar búsquedas anónimas.

`GET /sites/MLC/search` era abierto durante años y Baiyer lo llamaba sin
credenciales. Desde 2025 responde 403 sin `Authorization`, y como cada fuente se
tragaba su excepción, la búsqueda devolvía cero en silencio: cualquier compra no
industrial quedaba en $0 y el diagnóstico apuntaba a la categoría del ítem.

Sobre el grant: la doc oficial lista `authorization_code` y `refresh_token`, pero
hay ejemplos usando `client_credentials`, y su sitio bloquea a los clientes no
navegador así que no se pudo verificar. Se intentan los dos y se registra cuál
funcionó, para poder borrar el otro cuando se confirme.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import mercadolibre_auth as auth


@pytest.fixture(autouse=True)
def _limpiar_cache():
    auth.invalidar_cache()
    yield
    auth.invalidar_cache()


def _client(*respuestas):
    """Cliente falso que devuelve las respuestas en orden."""
    client = MagicMock()
    client.post = AsyncMock(side_effect=list(respuestas))
    return client


def _resp(status, cuerpo=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = cuerpo or {}
    r.text = str(cuerpo or "")
    return r


def _con_credenciales(refresh=""):
    ajustes = MagicMock()
    ajustes.meli_client_id = "id-123"
    ajustes.meli_client_secret = "secreto"
    ajustes.meli_refresh_token = refresh
    return patch("app.config.settings", ajustes)


def _token(client):
    return asyncio.run(auth.obtener_token(client))


# ─── Sin credenciales: error distinto, no reintentable ───────────────────────

def test_sin_credenciales_lanza_un_error_propio():
    """Reintentar no sirve: hay que configurar la aplicación."""
    ajustes = MagicMock()
    ajustes.meli_client_id = ""
    ajustes.meli_client_secret = ""
    ajustes.meli_refresh_token = ""
    with patch("app.config.settings", ajustes):
        with pytest.raises(auth.SinCredencialesMeli) as error:
            _token(_client())
    assert "MELI_CLIENT_ID" in str(error.value)
    assert "developers.mercadolibre.cl" in str(error.value)


# ─── Los dos grants ──────────────────────────────────────────────────────────

def test_usa_client_credentials_si_funciona():
    with _con_credenciales():
        token = _token(_client(_resp(200, {"access_token": "T1", "expires_in": 21600})))
    assert token == "T1"
    assert auth.grant_en_uso() == "client_credentials"


def test_cae_a_refresh_token_si_el_primero_falla():
    """El caso que la doc oficial sí documenta."""
    with _con_credenciales(refresh="R1"):
        token = _token(_client(
            _resp(400, {"error": "unsupported_grant_type"}),
            _resp(200, {"access_token": "T2", "expires_in": 21600}),
        ))
    assert token == "T2"
    assert auth.grant_en_uso() == "refresh_token"


def test_sin_refresh_token_no_intenta_el_segundo_grant():
    with _con_credenciales():
        client = _client(_resp(400, {"error": "x"}))
        with pytest.raises(RuntimeError):
            _token(client)
    assert client.post.await_count == 1


def test_el_error_final_nombra_los_dos_intentos():
    """Sin esto, "no se pudo obtener token" no dice qué probar."""
    with _con_credenciales(refresh="R1"):
        with pytest.raises(RuntimeError) as error:
            _token(_client(_resp(400, {"error": "a"}), _resp(401, {"error": "b"})))
    assert "client_credentials" in str(error.value)
    assert "refresh_token" in str(error.value)


# ─── Caché ───────────────────────────────────────────────────────────────────

def test_el_token_se_cachea_entre_busquedas():
    """Pedir uno por búsqueda gastaría cuota y latencia sin necesidad."""
    with _con_credenciales():
        client = _client(_resp(200, {"access_token": "T1", "expires_in": 21600}))
        assert _token(client) == "T1"
        assert _token(client) == "T1"
    assert client.post.await_count == 1


def test_renueva_cuando_el_token_expira():
    with _con_credenciales():
        client = _client(
            _resp(200, {"access_token": "T1", "expires_in": 21600}),
            _resp(200, {"access_token": "T2", "expires_in": 21600}),
        )
        assert _token(client) == "T1"
        auth._cache["expira_en"] = 0
        assert _token(client) == "T2"


def test_renueva_con_margen_antes_de_expirar():
    """Renovar justo en el límite deja requests en vuelo con un token vencido."""
    import time

    with _con_credenciales():
        _token(_client(_resp(200, {"access_token": "T1", "expires_in": 3600})))
    vida_util = auth._cache["expira_en"] - time.time()
    assert vida_util < 3600, "debe renovar antes de la expiración nominal"


def test_invalidar_fuerza_un_token_nuevo():
    """Un token puede revocarse antes de su expiración nominal."""
    with _con_credenciales():
        client = _client(
            _resp(200, {"access_token": "T1", "expires_in": 21600}),
            _resp(200, {"access_token": "T2", "expires_in": 21600}),
        )
        assert _token(client) == "T1"
        auth.invalidar_cache()
        assert _token(client) == "T2"


def test_una_respuesta_sin_access_token_no_se_cachea():
    with _con_credenciales(refresh="R1"):
        with pytest.raises(RuntimeError):
            _token(_client(_resp(200, {"scope": "read"}), _resp(200, {"scope": "read"})))
    assert auth.grant_en_uso() is None
