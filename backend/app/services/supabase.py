from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


class _RespuestaVacia:
    """Standin con `.data = None` — mismo shape que una respuesta real de
    postgrest-py, para que el código que llama nunca tenga que distinguir
    entre 'no encontró nada' y 'la librería devolvió None'."""
    data = None


def ejecutar_maybe_single(query):
    """Ejecuta un query que ya tiene `.maybe_single()` aplicado y SIEMPRE
    devuelve un objeto con `.data` accesible (nunca `None` directamente).

    Bug real encontrado en producción: en postgrest-py 2.x,
    `.maybe_single().execute()` devuelve `None` (no un objeto con
    `.data = None`) cuando la consulta no matchea ninguna fila. Cualquier
    `respuesta.data` sin este wrapper corre riesgo de
    `AttributeError: 'NoneType' object has no attribute 'data'` — encontrado
    primero en `resolver_organizacion()`, donde tumbaba dashboard, listas,
    gmail y workflows enteros para cualquier usuario sin fila en
    `membresias_organizacion`.

    Uso: reemplaza `query.maybe_single().execute()` por
    `ejecutar_maybe_single(query.maybe_single())` — todo el código
    downstream (`resp.data`, `(resp.data or {})`, `if resp.data:`) sigue
    funcionando igual, sin tener que reescribir cada sitio.

    Deliberadamente NO atrapa excepciones: solo cubre el caso puntual donde
    la librería devuelve `None` en vez de lanzar. Un error real de red/query
    debe seguir propagándose, no esconderse como "no encontrado".
    """
    resp = query.execute()
    return resp if resp is not None else _RespuestaVacia()
