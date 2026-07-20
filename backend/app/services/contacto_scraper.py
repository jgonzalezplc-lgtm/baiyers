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

import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_WA_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=|web\.whatsapp\.com/send\?phone=)(\+?\d[\d\s\-]{6,})", re.I)
# Emails de plataformas/imágenes que no son contacto real
_EMAIL_BASURA = ("sentry", "example.com", "@2x", ".png", ".jpg", ".gif", "wixpress", "godaddy", "domain")
_RUTAS_CONTACTO = ["", "/contacto", "/contactenos", "/contacto.html", "/contact", "/nosotros"]


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
    for pref in ("ventas", "contacto", "cotiza", "comercial", "info"):
        for e in limpios:
            if e.startswith(pref):
                return e
    return limpios[0]


async def extraer_contacto(url: str, timeout: float = 8.0) -> dict:
    """Devuelve { email, whatsapp: {numero, link} | None, telefono }."""
    vacio = {"email": None, "whatsapp": None, "telefono": None}
    if not url or not url.startswith("http"):
        return vacio

    base = re.match(r"(https?://[^/?#]+)", url)
    base = base.group(1) if base else url

    emails: list[str] = []
    wsp_num: str | None = None
    telefono: str | None = None

    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True) as client:
            # La URL del producto primero, luego rutas de contacto típicas del dominio
            urls = [url] + [base + r for r in _RUTAS_CONTACTO if r]
            for u in urls[:4]:
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
