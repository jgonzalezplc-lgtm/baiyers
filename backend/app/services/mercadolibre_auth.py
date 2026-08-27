"""Token de MercadoLibre para la API de búsqueda.

`GET /sites/MLC/search` era anónimo durante años y por eso Baiyer lo llamaba sin
credenciales. MercadoLibre lo cerró: desde 2025 responde **403 forbidden** sin
`Authorization`. Como cada fuente se tragaba su excepción, la búsqueda devolvía
cero en silencio y el diagnóstico apuntaba al lugar equivocado durante días.

**Sobre el grant:** la documentación oficial lista `authorization_code` y
`refresh_token` como únicos valores válidos, pero hay ejemplos de MercadoLibre
usando `client_credentials`. No se pudo verificar cuál aplica a la API de
búsqueda —su sitio bloquea a los clientes no-navegador—, así que se intentan los
dos y se registra cuál funcionó. Cuando se confirme, el otro se puede borrar.

El token se cachea en memoria hasta su expiración: pedir uno nuevo en cada
búsqueda gastaría cuota y latencia sin necesidad. Es por proceso, así que con
varias réplicas cada una tiene el suyo — inofensivo.
"""
import time
from typing import Any, Optional

TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

# Margen antes de la expiración real: renovar justo en el límite deja requests
# en vuelo con un token que caduca a mitad de camino.
_MARGEN_SEGUNDOS = 60

_cache: dict[str, Any] = {"token": None, "expira_en": 0.0, "grant": None}


class SinCredencialesMeli(Exception):
    """No hay client_id/secret configurados. Es distinto de un fallo de red: no
    tiene sentido reintentar, hay que configurar la aplicación."""


def _credenciales() -> tuple[str, str, Optional[str]]:
    from app.config import settings

    client_id = getattr(settings, "meli_client_id", "") or ""
    client_secret = getattr(settings, "meli_client_secret", "") or ""
    refresh_token = getattr(settings, "meli_refresh_token", "") or ""
    if not client_id or not client_secret:
        raise SinCredencialesMeli(
            "MercadoLibre requiere autenticación desde 2025. Falta configurar "
            "MELI_CLIENT_ID y MELI_CLIENT_SECRET (app en developers.mercadolibre.cl)."
        )
    return client_id, client_secret, refresh_token or None


def invalidar_cache() -> None:
    """Fuerza pedir un token nuevo. Se usa al recibir un 401: el token pudo
    revocarse antes de su expiración nominal."""
    _cache.update({"token": None, "expira_en": 0.0, "grant": None})


async def obtener_token(client) -> str:
    """Access token vigente, del caché o pidiendo uno nuevo.

    `client` es un `httpx.AsyncClient` ya abierto: la búsqueda ya tiene uno y
    abrir otro por token sería desperdiciar una conexión.
    """
    ahora = time.time()
    if _cache["token"] and ahora < _cache["expira_en"]:
        return _cache["token"]

    client_id, client_secret, refresh_token = _credenciales()

    intentos = [("client_credentials", {
        "grant_type": "client_credentials",
        "client_id": client_id, "client_secret": client_secret,
    })]
    if refresh_token:
        intentos.append(("refresh_token", {
            "grant_type": "refresh_token", "client_id": client_id,
            "client_secret": client_secret, "refresh_token": refresh_token,
        }))

    errores = []
    for nombre, datos in intentos:
        try:
            resp = await client.post(
                TOKEN_URL, data=datos,
                headers={"accept": "application/json",
                         "content-type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
        except Exception as e:
            errores.append(f"{nombre}: {type(e).__name__}")
            continue
        if resp.status_code != 200:
            errores.append(f"{nombre}: HTTP {resp.status_code} {resp.text[:80]}")
            continue

        cuerpo = resp.json()
        token = cuerpo.get("access_token")
        if not token:
            errores.append(f"{nombre}: respuesta sin access_token")
            continue

        _cache.update({
            "token": token,
            "expira_en": ahora + max(60, int(cuerpo.get("expires_in") or 21600)) - _MARGEN_SEGUNDOS,
            "grant": nombre,
        })
        print(f"[MercadoLibre] token obtenido con grant '{nombre}'")
        return token

    raise RuntimeError("No se pudo obtener token de MercadoLibre — " + " | ".join(errores))


def grant_en_uso() -> Optional[str]:
    """Con cuál de los dos se consiguió el token vigente. Sirve para confirmar
    empíricamente cuál soporta la API y borrar el otro."""
    return _cache["grant"]
