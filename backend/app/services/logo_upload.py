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
        actual = url
        # Clearbit y Google suelen redirigir el recurso aunque la imagen se
        # renderice bien en el navegador. Seguimos pocos saltos, validando
        # esquema, DNS e IP en CADA destino para conservar la protección SSRF.
        for _ in range(4):
            resp = await client.get(actual)
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            destino = str(resp.url.join(resp.headers.get("location", "")))
            parsed_destino = urlparse(destino)
            if parsed_destino.scheme not in _ESQUEMAS_PERMITIDOS or not parsed_destino.hostname:
                raise ValueError("Redirección de logo no permitida")
            if _host_es_privado(parsed_destino.hostname):
                raise ValueError("No se permite redirigir a direcciones privadas")
            actual = destino
        else:
            raise ValueError("Demasiadas redirecciones al descargar el logo")
        if resp.status_code != 200:
            raise ValueError(f"El servidor respondió {resp.status_code}")

        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type not in TIPOS_PERMITIDOS:
            raise ValueError(f"Tipo de archivo no permitido: {content_type or 'desconocido'}")

        contenido = resp.content
        if len(contenido) > TAMANO_MAXIMO_BYTES:
            raise ValueError("El archivo supera el tamaño máximo permitido")
        return contenido


def detectar_content_type(contenido: bytes, fallback: str = "image/png") -> str:
    """Detecta el formato real; las URLs de logos casi nunca tienen extensión."""
    inicio = contenido[:512].lstrip()
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if inicio.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if inicio.startswith((b"RIFF",)) and contenido[8:12] == b"WEBP":
        return "image/webp"
    if inicio.startswith((b"<svg", b"<?xml")):
        return "image/svg+xml"
    if inicio.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    return fallback


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


BUCKET_LOGOS = "company-logos"

# Una semana. El logo se consume desde el navegador de un miembro de la
# organización justo después de pedir el perfil, así que con minutos alcanzaría;
# la ventana larga existe porque `user_metadata.logo_url` guarda una COPIA de
# esta URL (la leen el dashboard y /settings) y una copia con vida corta se
# rompería sola a los pocos minutos. No es "casi público": sigue caducando, sigue
# sin ser enumerable y se puede revocar rotando el objeto.
VIGENCIA_URL_LOGO_SEGUNDOS = 7 * 24 * 60 * 60


def subir_logo(organizacion_id: str, content_type: str, contenido: bytes) -> str:
    """Sube el logo ya validado y devuelve su PATH dentro del bucket.

    Devuelve el path y no una URL a propósito: el path es lo durable y es lo que
    va a `organizaciones.logo_storage_path`. La URL se firma al leer, con
    `url_firmada_de_logo()`.

    Antes esto devolvía `get_public_url(...)` y esa URL se guardaba en la base.
    El bucket `company-logos` es privado, así que la ruta `/object/public/...`
    respondía `400 Bucket not found` y el logo NUNCA cargaba: los PDFs de OC y
    los informes caían siempre al fallback de texto, en silencio, porque el
    fallback se ve bien y nadie lo leyó como un error.

    El UUID en el path invalida cachés de navegador al reemplazar el logo.
    """
    ext = _EXTENSION_POR_TIPO.get((content_type or "").lower(), "png")
    filename = f"{organizacion_id}/{uuid.uuid4().hex}.{ext}"
    _sb().storage.from_(BUCKET_LOGOS).upload(
        filename, contenido, {"content-type": content_type, "upsert": "true"},
    )
    return filename


def url_firmada_de_logo(path: str) -> str | None:
    """URL temporal para un logo del bucket privado. `None` si no se puede
    firmar — el logo es decorativo y su ausencia nunca debe tumbar la generación
    de un documento (mismo criterio que `obtener_perfil_organizacion`)."""
    if not path:
        return None
    try:
        resp = _sb().storage.from_(BUCKET_LOGOS).create_signed_url(
            path, VIGENCIA_URL_LOGO_SEGUNDOS,
        )
    except Exception as e:
        print(f"[logo] no se pudo firmar '{path}': {e}")
        return None
    if isinstance(resp, dict):
        # El SDK cambió el nombre de la clave entre versiones.
        return resp.get("signedURL") or resp.get("signedUrl") or resp.get("signed_url")
    return getattr(resp, "signed_url", None)


def path_de_logo_legado(url: str | None) -> str | None:
    """Rescata el path desde una `logo_url` vieja de tipo `/object/public/...`.

    Las organizaciones que subieron su logo antes de este cambio tienen una URL
    rota guardada, pero esa URL CONTIENE el path real. Extraerlo evita tener que
    correr un backfill: se recuperan solas la primera vez que alguien lee su
    perfil. Devuelve None si la URL no es de este bucket.
    """
    if not url:
        return None
    marca = f"/{BUCKET_LOGOS}/"
    if marca not in url:
        return None
    path = url.split(marca, 1)[1].split("?", 1)[0].strip()
    return path or None
