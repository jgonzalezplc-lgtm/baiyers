"""`state` firmado para los flujos OAuth de correo (Gmail / Outlook).

Motivo (2026-08-25, hallazgo de la auditoría externa): el `state` era
`base64(json)` sin firma, y `GET /api/gmail/auth?user_id=...` estaba en
`RUTAS_PUBLICAS` con el motivo "lo llama Google" — pero a `/auth` lo llama el
navegador del usuario; a Google le corresponde sólo `/callback`.

Con eso, cualquiera podía abrir `/api/gmail/auth?user_id=<uuid_de_la_victima>`,
completar el consentimiento con SU PROPIA cuenta de Google, y el callback hacía
`upsert` de los tokens del atacante sobre la fila `user_integrations` de la
víctima. El resultado no es leer correo ajeno: las RFQ y OC de la víctima pasan
a salir desde el buzón del atacante, y el agente de Gmail ingiere correo que él
controla como si fueran cotizaciones de proveedores (con auto-aplicación de
precios a confianza >= 0.85). Es inyección directa en el flujo de compra.

El cierre tiene dos partes y las dos hacen falta:
  1. No existe más un endpoint que inicie el flujo sin sesión: el `user_id` sale
     de `get_auth_context`, nunca de la query.
  2. El `state` va firmado y con vencimiento, así que `/callback` — que sí es
     público porque lo invoca el proveedor — puede confiar en el `user_id` que
     lee. Sin la firma, el punto 1 solo se saltaría llamando a `/callback`
     directo con un `state` inventado.

La clave de firma es `SUPABASE_SERVICE_KEY`, que ya vive en el entorno del
backend y nunca sale de él — evita agregar un secreto más que rotar.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

# 10 minutos: alcanza de sobra para completar el consentimiento y acota la
# ventana en que un `state` capturado (historial, logs del proveedor) sirve.
VIGENCIA_SEGUNDOS = 600


def _clave() -> bytes:
    from app.config import settings
    return settings.supabase_service_key.encode()


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _desb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def firmar_state(user_id: str, verifier: str, next_path: str) -> str:
    """`<payload>.<firma>` — el payload sigue siendo legible (no es secreto),
    pero ya no es modificable."""
    payload = _b64(json.dumps({
        "u": user_id, "v": verifier, "n": next_path,
        "exp": int(time.time()) + VIGENCIA_SEGUNDOS,
    }).encode())
    firma = _b64(hmac.new(_clave(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{firma}"


def verificar_state(state: str) -> Optional[dict]:
    """Devuelve `{"u","v","n"}` si la firma es válida y no venció; `None` si no.

    Nunca lanza ni distingue el motivo del rechazo: el llamador responde lo
    mismo ante una firma inválida y un `state` vencido.
    """
    try:
        payload, firma = state.split(".", 1)
        esperada = _b64(hmac.new(_clave(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        datos = json.loads(_desb64(payload).decode())
    except Exception:
        return None
    if not isinstance(datos, dict) or not datos.get("u") or not datos.get("v"):
        return None
    if int(datos.get("exp") or 0) < int(time.time()):
        return None
    return datos
