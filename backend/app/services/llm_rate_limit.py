"""Rate limiting por IP para endpoints que gastan llamadas a un LLM.

Distinto del de `api_publica/rate_limiter.py`, que va por `api_key_id` y plan
contratado: acá no hay identidad, así que se limita por IP de origen.

Motivación concreta: `/api/workflows/interpretar` y `/api/workflows/proceso/turno`
llaman a Gemini sin autenticación. Con cuenta pagada no existe el techo de cuota
del free tier, así que un loop desde afuera factura sin freno.

Alcance honesto de esta defensa:
- Es un **freno**, no una garantía. Un atacante distribuido rota IPs y lo evade.
  La mitigación de fondo es el tope de tamaño del input (que acota el costo por
  request) y, en definitiva, exigir autenticación.
- El contador es **en memoria y por proceso**: con más de una instancia el
  límite efectivo se multiplica por la cantidad de réplicas. Alcanza para el
  despliegue actual (Railway Hobby, una instancia) y no agrega dependencias.
"""
import ipaddress
import threading
import time
from collections import deque
from typing import Callable

from fastapi import HTTPException, Request

# ventana[(nombre, ip)] = deque de timestamps (segundos, monotónicos)
_ventanas: dict[tuple[str, str], deque] = {}
_lock = threading.Lock()
_ultima_limpieza = 0.0

_HORA = 3600.0
_MINUTO = 60.0
# Cada cuánto se barren las ventanas vacías. Sin esto el dict crece sin techo
# con cada IP distinta y el propio limitador se vuelve un vector de memoria.
_INTERVALO_LIMPIEZA = 300.0


def ip_cliente(request: Request) -> str:
    """IP real del cliente detrás de Cloudflare → Railway.

    `CF-Connecting-IP` la escribe Cloudflare y sobrescribe cualquier valor que
    mande el cliente, así que es la fuente confiable. `X-Forwarded-For` queda
    como respaldo (falsificable: sirve para el caso normal, no contra un
    atacante que la falsee a propósito).
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf and cf.strip():
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def es_llamada_interna(request: Request) -> bool:
    """True si el request viene del propio backend (loopback), no de internet.

    Existe porque `/api/buscar` lo consumen server-to-server el servidor MCP
    (`app/mcp/tools/cotizar.py`) y la API pública (`app/api_publica/endpoints/
    cotizar.py`), ambos contra `http://localhost:8000`. Sin esta exención los
    dos comparten la misma IP de origen y se estrangulan entre sí: el límite
    pensado para frenar abuso externo terminaría rompiendo el flujo legítimo.
    No se pierde protección: esos dos caminos ya tienen su propio control
    aguas arriba (JWT en MCP, `rate_limiter.py` por `api_key_id` en la API
    pública).

    La detección es deliberadamente estricta: un request que llega de internet
    pasa por Cloudflare → Railway y **siempre** trae `cf-connecting-ip` o
    `x-forwarded-for`. Exigir que no exista ninguno de los dos evita que un
    atacante se declare interno falsificando `X-Forwarded-For: 127.0.0.1`.
    """
    if request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for"):
        return False
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _limpiar(ahora: float) -> None:
    """Elimina ventanas sin actividad en la última hora. Se llama con el lock
    tomado."""
    global _ultima_limpieza
    if ahora - _ultima_limpieza < _INTERVALO_LIMPIEZA:
        return
    _ultima_limpieza = ahora
    vacias = [k for k, v in _ventanas.items() if not v or ahora - v[-1] > _HORA]
    for k in vacias:
        _ventanas.pop(k, None)


def registrar_intento(nombre: str, ip: str, por_minuto: int, por_hora: int) -> None:
    """Registra un intento y lanza 429 si excede alguno de los dos límites.

    Separado de la dependencia FastAPI para poder testearlo sin request."""
    ahora = time.monotonic()
    with _lock:
        _limpiar(ahora)
        ventana = _ventanas.setdefault((nombre, ip), deque())
        while ventana and ahora - ventana[0] > _HORA:
            ventana.popleft()

        en_el_minuto = sum(1 for t in ventana if ahora - t <= _MINUTO)
        if en_el_minuto >= por_minuto or len(ventana) >= por_hora:
            # No se registra el intento rechazado: si no, un atacante en loop
            # mantendría la ventana llena para siempre y el bloqueo nunca
            # expiraría para esa IP (castigo permanente por un pico puntual).
            raise HTTPException(
                status_code=429,
                detail="Demasiadas solicitudes seguidas. Espera un momento y vuelve a intentarlo.",
            )
        ventana.append(ahora)


def limitar_por_ip(nombre: str, por_minuto: int, por_hora: int) -> Callable:
    """Dependencia FastAPI. `nombre` separa los contadores por endpoint para
    que gastar uno no bloquee el otro."""
    def dependencia(request: Request) -> None:
        if es_llamada_interna(request):
            return
        registrar_intento(nombre, ip_cliente(request), por_minuto, por_hora)
    return dependencia


def reset_para_tests() -> None:
    global _ultima_limpieza
    with _lock:
        _ventanas.clear()
        _ultima_limpieza = 0.0
