"""Creación de notificaciones para la campanita del frontend (ver 022_notificaciones.sql).

Los triggers actuales son aprobación de cotización (aprobaciones.py) y respuesta
de proveedor por correo con datos aplicados (gmail.py). Se agregan más triggers
llamando a crear_notificacion desde el punto del código donde ocurre el evento.
"""


def crear_notificacion(sb, user_id: str, tipo: str, titulo: str, mensaje: str, data: dict | None = None) -> None:
    try:
        sb.table("notificaciones").insert({
            "user_id": user_id,
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "data": data or {},
        }).execute()
    except Exception as e:
        # Una notificación que falla no debe tumbar el flujo que la dispara.
        print(f"[Notificaciones] no se pudo crear ({tipo}) para {user_id}: {e}")
