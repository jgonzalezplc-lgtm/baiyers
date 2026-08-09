"""
Subida de logo de empresa a Supabase Storage (bucket `company-logos`).

Dos caminos: confirmar un candidato investigado (URL de Clearbit/Google
favicons) o subir un archivo propio. En ambos casos el backend nunca
persiste una URL/data-URL arbitraria sin antes descargarla y validarla él
mismo — mitigación de SSRF: sin seguir redirects, resolviendo el host antes
de conectar y rechazando IPs privadas/loopback/link-local, timeout corto,
content-type real de la respuesta y límite de tamaño.
"""
import ipaddress
import socket
import uuid
from urllib.parse import urlparse

TIPOS_PERMITIDOS = {"image/png", "image/jpeg", "image/webp", "image/svg+xml", "image/x-icon", "image/vnd.microsoft.icon"}
TAMANO_MAXIMO_BYTES = 3 * 1024 * 1024  # 3 MB
_ESQUEMAS_PERMITIDOS = {"https"}


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _host_es_privado(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True  # si no resuelve, no se confía
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


async def descargar_y_validar_url(url: str) -> bytes:
    """Descarga una URL externa con protecciones anti-SSRF. Lanza ValueError
    con un motivo legible si no pasa alguna validación."""
    import httpx

    parsed = urlparse(url)
    if parsed.scheme not in _ESQUEMAS_PERMITIDOS:
        raise ValueError("Solo se permiten URLs https")
    if not parsed.hostname:
        raise ValueError("URL sin host")
    if _host_es_privado(parsed.hostname):
        raise ValueError("No se permite descargar desde direcciones privadas")

    async with httpx.AsyncClient(timeout=6.0, follow_redirects=False) as client:
        resp = await client.get(url)
        if resp.status_code in (301, 302, 303, 307, 308):
            raise ValueError("No se siguen redirects al descargar el logo")
        if resp.status_code != 200:
            raise ValueError(f"El servidor respondió {resp.status_code}")

        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type not in TIPOS_PERMITIDOS:
            raise ValueError(f"Tipo de archivo no permitido: {content_type or 'desconocido'}")

        contenido = resp.content
        if len(contenido) > TAMANO_MAXIMO_BYTES:
            raise ValueError("El archivo supera el tamaño máximo permitido")
        return contenido


def validar_archivo_subido(content_type: str, contenido: bytes) -> None:
    if (content_type or "").lower() not in TIPOS_PERMITIDOS:
        raise ValueError(f"Tipo de archivo no permitido: {content_type}")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise ValueError("El archivo supera el tamaño máximo permitido")
    if len(contenido) == 0:
        raise ValueError("Archivo vacío")


_EXTENSION_POR_TIPO = {
    "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
    "image/svg+xml": "svg", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico",
}


def subir_logo(organizacion_id: str, content_type: str, contenido: bytes) -> str:
    """Sube el logo ya validado al bucket `company-logos` y devuelve la URL
    pública. El path incluye un UUID para invalidar cachés de navegador al
    reemplazar el logo."""
    ext = _EXTENSION_POR_TIPO.get((content_type or "").lower(), "png")
    filename = f"{organizacion_id}/{uuid.uuid4().hex}.{ext}"
    sb = _sb()
    sb.storage.from_("company-logos").upload(
        filename, contenido, {"content-type": content_type, "upsert": "true"},
    )
    return sb.storage.from_("company-logos").get_public_url(filename)
