"""El estado de Gmail debe reflejar si la autorización SIRVE, no si existe.

Bug real (2026-08-25): `/api/gmail/status` hacía `bool(refresh_token)`, así que una
autorización revocada figuraba "conectado / ok". Peor: el botón "Conectar Gmail" del
dashboard sólo se renderiza cuando `connected` es falso, o sea que el usuario quedaba
encerrado afuera — el sistema creía estar bien y no le ofrecía cómo arreglarlo. La
falla recién aparecía al intentar enviar un correo, a mitad de una tarea.
"""
from google.auth.exceptions import RefreshError

from app.services import gmail_service as gs


class _CredsFake:
    def __init__(self, error=None):
        self.error = error
        self.refrescos = 0

    def refresh(self, _request):
        self.refrescos += 1
        if self.error:
            raise self.error


def _montar(monkeypatch, creds):
    monkeypatch.setattr(gs, "_load_client_secrets", lambda: {"client_id": "id", "client_secret": "sec"})
    monkeypatch.setattr(gs, "Credentials", lambda **_: creds)
    monkeypatch.setattr(gs, "Request", lambda: object())
    gs._cache_validez.clear()


def test_credencial_viva(monkeypatch):
    _montar(monkeypatch, _CredsFake())
    assert gs.verificar_credencial("at", "rt") == (True, None)


def test_token_revocado_es_invalid_grant(monkeypatch):
    _montar(monkeypatch, _CredsFake(RefreshError("invalid_grant: Token has been expired or revoked.")))
    assert gs.verificar_credencial("at", "rt") == (False, "invalid_grant")


def test_secreto_mal_configurado_es_invalid_client(monkeypatch):
    """Distinguirlo importa: reconectar el buzón NO arregla este caso."""
    _montar(monkeypatch, _CredsFake(RefreshError("invalid_client: The provided client secret is invalid.")))
    assert gs.verificar_credencial("at", "rt") == (False, "invalid_client")


def test_sin_refresh_token_no_llama_a_google(monkeypatch):
    creds = _CredsFake()
    _montar(monkeypatch, creds)
    assert gs.verificar_credencial("at", "") == (False, "sin_refresh_token")
    assert creds.refrescos == 0


def test_caida_de_red_no_se_reporta_como_credencial_invalida(monkeypatch):
    """Decir "reconectá" ante un corte de red mandaría al usuario a rehacer un
    consentimiento que no hacía falta."""
    _montar(monkeypatch, _CredsFake(ConnectionError("sin red")))
    sirve, motivo = gs.verificar_credencial("at", "rt")
    assert sirve is True
    assert motivo == "verificacion_no_concluyente"


# ─── Caché ───────────────────────────────────────────────────────────────────

def test_cache_evita_pegarle_a_google_en_cada_carga(monkeypatch):
    creds = _CredsFake()
    _montar(monkeypatch, creds)
    for _ in range(5):
        assert gs.verificar_credencial_cacheada("u1", "at", "rt") == (True, None)
    assert creds.refrescos == 1


def test_resultado_no_concluyente_no_se_cachea(monkeypatch):
    creds = _CredsFake(ConnectionError("sin red"))
    _montar(monkeypatch, creds)
    gs.verificar_credencial_cacheada("u1", "at", "rt")
    gs.verificar_credencial_cacheada("u1", "at", "rt")
    assert creds.refrescos == 2  # se reintenta, no queda un veredicto inventado


def test_cache_expira(monkeypatch):
    creds = _CredsFake()
    _montar(monkeypatch, creds)
    gs.verificar_credencial_cacheada("u1", "at", "rt")
    reloj = [0.0]
    monkeypatch.setattr(gs.time, "time", lambda: reloj[0])
    gs._cache_validez["u1"] = (0.0, True, None)
    reloj[0] = gs.TTL_CACHE_VALIDEZ + 1
    gs.verificar_credencial_cacheada("u1", "at", "rt")
    assert creds.refrescos == 2


def test_reconectar_invalida_el_cache(monkeypatch):
    """Sin esto el dashboard seguiría diciendo "reconexión requerida" hasta 10
    minutos después de que el usuario ya reconectó."""
    _montar(monkeypatch, _CredsFake(RefreshError("invalid_grant")))
    assert gs.verificar_credencial_cacheada("u1", "at", "rt")[0] is False
    assert "u1" in gs._cache_validez

    gs.invalidar_cache_validez("u1")
    assert "u1" not in gs._cache_validez

    _montar(monkeypatch, _CredsFake())
    assert gs.verificar_credencial_cacheada("u1", "at", "rt") == (True, None)


def test_cache_es_por_usuario(monkeypatch):
    creds = _CredsFake()
    _montar(monkeypatch, creds)
    gs.verificar_credencial_cacheada("u1", "at", "rt")
    gs.verificar_credencial_cacheada("u2", "at", "rt")
    assert creds.refrescos == 2
