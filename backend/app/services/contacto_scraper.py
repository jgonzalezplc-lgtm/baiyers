"""
Scraper de contacto: al momento de cotizar, entra a la página del proveedor y
extrae email de contacto y link de WhatsApp (para armar un mensaje pre-hecho).

Rápido y sin APIs de pago: descarga el HTML de la URL (y prueba /contacto,
/contacto.html, /contactenos) y busca:
  - Emails: enlaces mailto: y texto que matchee un email (prioriza ventas@/contacto@).
  - WhatsApp: enlaces wa.me / api.whatsapp.com / whatsapp://send + botones con
    data-phone, y números junto a la palabra "whatsapp". Normaliza a formato
    internacional chileno (+56) para el link wa.me.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _es_url_publica(url: str) -> bool:
    """Bloquea SSRF: rechaza esquemas distintos de http(s) y hosts que resuelvan
    a IPs privadas/loopback/link-local (incluye 169.254.169.254 de metadata cloud)."""
    try:
        partes = urllib.parse.urlsplit(url)
        if partes.scheme not in ("http", "https") or not partes.hostname:
            return False
        for info in socket.getaddrinfo(partes.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_WA_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=|web\.whatsapp\.com/send\?phone=)(\+?\d[\d\s\-]{6,})", re.I)
# Emails de plataformas/imágenes que no son contacto real
_EMAIL_BASURA = ("sentry", "example.com", "@2x", ".png", ".jpg", ".gif", "wixpress", "godaddy", "domain")
_RUTAS_CONTACTO = ["", "/contacto", "/contactenos", "/contacto.html", "/contact", "/nosotros"]

# Dominios agregadores donde NO hay contacto real del proveedor (hay que resolver la tienda)
_DOMINIOS_AGREGADORES = (
    "google.", "mercadolibre.", "mercadolibre.cl", "articulo.mercadolibre",
    "amazon.", "aliexpress.", "alibaba.", "bing.", "shopping.google",
)


def _es_agregador(url: str) -> bool:
    host = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    return any(d in host for d in _DOMINIOS_AGREGADORES)


async def _resolver_dominio_tienda(proveedor: str, client: httpx.AsyncClient) -> str | None:
    """Cuando el resultado viene de un agregador (Google Shopping, MercadoLibre),
    busca el sitio web real de la tienda por su nombre usando Serper."""
    from app.config import settings
    key = settings.serper_api_key
    if not key or not proveedor or len(proveedor.strip()) < 3:
        return None
    try:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": f"{proveedor} sitio oficial contacto", "gl": "cl", "hl": "es", "num": 5},
            timeout=8.0,
        )
        data = resp.json()
        for item in (data.get("organic") or [])[:5]:
            link = item.get("link", "")
            if link and not _es_agregador(link):
                m = re.match(r"(https?://[^/?#]+)", link)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


def _normalizar_wsp_cl(raw: str) -> str | None:
    """Deja solo dígitos y normaliza a internacional chileno para wa.me."""
    d = re.sub(r"\D", "", raw or "")
    if not d:
        return None
    if d.startswith("56") and len(d) >= 11:
        return d[:11]
    if d.startswith("9") and len(d) == 9:      # celular chileno 9XXXXXXXX
        return "56" + d
    if len(d) == 8:                             # a veces sin el 9
        return "569" + d
    if 10 <= len(d) <= 15:                      # ya internacional
        return d
    return None


def _mejor_email(emails: list[str]) -> str | None:
    if not emails:
        return None
    limpios = [e.lower() for e in emails if not any(b in e.lower() for b in _EMAIL_BASURA)]
    if not limpios:
        return None
    # Priorizar buzones de contacto/ventas
    for pref in ("ventas", "contacto", "cotiza", "comercial", "info", "hola", "clientes"):
        for e in limpios:
            if e.startswith(pref):
                return e
    # Deprioriza buzones no comerciales; úsalos solo si no hay nada mejor
    no_comercial = ("denuncia", "privacidad", "legal", "rrhh", "prensa", "trabaja", "postula", "spam", "abuse")
    comerciales = [e for e in limpios if not any(nc in e for nc in no_comercial)]
    return (comerciales or limpios)[0]


async def extraer_contacto(url: str, timeout: float = 8.0, proveedor: str | None = None) -> dict:
    """Devuelve { email, whatsapp: {numero, link} | None, telefono }.

    Si la URL es de un agregador (Google Shopping, MercadoLibre…), primero
    resuelve el sitio real de la tienda por el nombre del proveedor.
    """
    vacio = {"email": None, "whatsapp": None, "telefono": None}
    if not url or not _es_url_publica(url):
        return vacio

    emails: list[str] = []
    wsp_num: str | None = None
    telefono: str | None = None

    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True) as client:
            # Si viene de un agregador, resolver el dominio real de la tienda
            origen = url
            if _es_agregador(url) and proveedor:
                dominio = await _resolver_dominio_tienda(proveedor, client)
                if dominio:
                    origen = dominio

            base = re.match(r"(https?://[^/?#]+)", origen)
            base = base.group(1) if base else origen

            # La URL (producto o tienda) primero, luego rutas de contacto típicas
            urls = [origen] + [base + r for r in _RUTAS_CONTACTO if r]
            for u in urls[:5]:
                if not _es_url_publica(u):
                    continue
                try:
                    resp = await client.get(u)
                    if resp.status_code != 200:
                        continue
                    html = resp.text
                except Exception:
                    continue

                # WhatsApp en enlaces / atributos
                if not wsp_num:
                    m = _WA_RE.search(html)
                    if m:
                        wsp_num = _normalizar_wsp_cl(m.group(1))

                soup = BeautifulSoup(html, "html.parser")

                # Emails: mailto + texto
                for a in soup.select('a[href^="mailto:"]'):
                    addr = a.get("href", "")[7:].split("?")[0].strip()
                    if _EMAIL_RE.fullmatch(addr):
                        emails.append(addr)
                emails += _EMAIL_RE.findall(html)

                # WhatsApp por atributos data-phone / tel de botones flotantes
                if not wsp_num:
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "whatsapp" in href.lower() or "wa.me" in href.lower():
                            mm = re.search(r"(\+?\d[\d\s\-]{6,})", href)
                            if mm:
                                wsp_num = _normalizar_wsp_cl(mm.group(1))
                                break

                # Teléfono (tel:) como respaldo
                if not telefono:
                    tel = soup.select_one('a[href^="tel:"]')
                    if tel:
                        telefono = tel.get("href", "")[4:].strip()

                # Si ya tenemos email de contacto Y whatsapp, no seguir pidiendo páginas
                if _mejor_email(emails) and wsp_num:
                    break
    except Exception as e:
        print(f"[ContactoScraper] {url}: {e}")

    email = _mejor_email(emails)
    whatsapp = {"numero": wsp_num, "link": f"https://wa.me/{wsp_num}"} if wsp_num else None
    return {"email": email, "whatsapp": whatsapp, "telefono": telefono}


def armar_mensaje_cotizacion(nombre_item: str, proveedor: str | None = None, cantidad: float | int = 1) -> str:
    """Mensaje pre-hecho de solicitud de cotización (para WhatsApp o email)."""
    saludo = f"Hola {proveedor}" if proveedor else "Hola"
    cant = f"{int(cantidad) if float(cantidad).is_integer() else cantidad} unidad(es) de " if cantidad and cantidad != 1 else ""
    return (
        f"{saludo}, ¿me pueden cotizar {cant}\"{nombre_item}\"? "
        f"Necesito precio, disponibilidad y plazo de entrega. ¡Gracias!"
    )


def link_wsp_con_mensaje(numero: str, mensaje: str) -> str:
    return f"https://wa.me/{numero}?text={urllib.parse.quote(mensaje)}"
