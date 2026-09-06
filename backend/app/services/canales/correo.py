"""Normalización de un correo entrante; no envía ni lee Gmail directamente."""
from __future__ import annotations

from app.services.empleado.contratos import Canal, IdentidadExterna, MensajeEntrante, RutaRespuesta


def normalizar_correo(
    *,
    gmail_message_id: str,
    gmail_thread_id: str,
    from_email: str,
    body_text: str,
    nombre_remitente: str | None = None,
) -> MensajeEntrante:
    """Convierte metadatos Gmail ya verificados en el contrato del empleado.

    La ruta se ata al thread original. Quien planifica la respuesta puede cambiar
    el texto, pero no puede reemplazar el destinatario ni sacar el hilo.
    """
    email = from_email.strip().lower()
    if not email or not gmail_message_id or not gmail_thread_id:
        raise ValueError("El correo requiere remitente, mensaje e hilo Gmail")
    return MensajeEntrante(
        canal=Canal.CORREO,
        identidad=IdentidadExterna(Canal.CORREO, email, nombre_remitente),
        texto=body_text or "",
        mensaje_id=gmail_message_id,
        hilo_id=gmail_thread_id,
        ruta_respuesta=RutaRespuesta(
            canal=Canal.CORREO,
            hilo=gmail_thread_id,
            destinatario=email,
            metadata={"gmail_message_id": gmail_message_id},
        ),
    )
