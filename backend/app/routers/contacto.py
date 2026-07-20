"""Contacto del proveedor al cotizar: email + WhatsApp con mensaje pre-hecho."""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["contacto"])


class ContactoRequest(BaseModel):
    url: str
    proveedor: Optional[str] = None
    nombre_item: str
    cantidad: float = 1
    email_existente: Optional[str] = None


@router.post("/contacto")
async def obtener_contacto(req: ContactoRequest):
    """Scrapea la página del proveedor y devuelve email + link de WhatsApp con
    un mensaje de cotización listo para copiar/pegar o abrir en WhatsApp."""
    from app.services.contacto_scraper import (
        extraer_contacto, armar_mensaje_cotizacion, link_wsp_con_mensaje,
    )

    mensaje = armar_mensaje_cotizacion(req.nombre_item, req.proveedor, req.cantidad)

    datos = await extraer_contacto(req.url)

    # Si ya venía un email en el resultado, priorizarlo
    email = req.email_existente if (req.email_existente and "@" in req.email_existente) else datos.get("email")

    whatsapp = None
    if datos.get("whatsapp"):
        numero = datos["whatsapp"]["numero"]
        whatsapp = {
            "numero": numero,
            "link": link_wsp_con_mensaje(numero, mensaje),
        }

    return {
        "email": email,
        "telefono": datos.get("telefono"),
        "whatsapp": whatsapp,
        "mensaje": mensaje,
    }
