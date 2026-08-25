"""Avisos para el operador de la plataforma (no para el cliente).

Un WARNING en el log de Railway no es una alarma: sólo existe si alguien abre
los logs. Esto manda el mismo aviso a dos lados donde sí se ve:

  1. `product_events` con `status="warning"` — aparece en el feed de actividad
     del control plane (CapoDiTutti, `GET /api/admin-control-plane/activity`).
     La `clave_idempotencia` es UNIQUE en la 028, así que repetir el mismo aviso
     no duplica la fila.
  2. Un correo a la casilla de operación.

Reglas de la casa, porque esto corre dentro del camino de un request real:
  - **Nunca lanza.** Un fallo del aviso no puede tumbar lo que el usuario pidió.
  - **Nunca bloquea.** El envío va en un thread aparte; el request no espera a
    que Gmail conteste.
  - No manda nada si no hay un buzón desde donde mandarlo, y lo dice en el log.

Limitación conocida: el correo no está deduplicado entre procesos. Quien llama
decide cuándo alertar (hoy `gemini_budget`, con un set en memoria), así que con
varias réplicas en Railway podrían salir varios correos del mismo evento. La
fila de `product_events` sí queda una sola, por la clave idempotente.
"""
from __future__ import annotations

import threading
from typing import Optional

# Casilla de operación. No es la de ningún cliente: es donde mira el dueño de
# la plataforma.
DESTINO_OPERACION = "hola@claria.cc"


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _buzon_del_operador() -> Optional[tuple[str, str, str]]:
    """`(user_id, access_token, refresh_token)` del primer admin del control
    plane que tenga Gmail conectado, o None.

    Se usa la cuenta del operador y no la de un cliente a propósito: mandar un
    aviso interno desde el buzón de una empresa cliente sería usar su
    infraestructura para nuestra operación, y quedaría en SU carpeta de
    enviados.
    """
    try:
        sb = _sb()
        admins = sb.table("admin_users").select("user_id").eq(
            "activo", True
        ).order("created_at").execute().data or []
        for admin in admins:
            fila = sb.table("user_integrations").select(
                "access_token, refresh_token"
            ).eq("user_id", admin["user_id"]).eq("provider", "gmail").limit(1).execute().data
            if fila and fila[0].get("access_token"):
                return admin["user_id"], fila[0]["access_token"], fila[0].get("refresh_token") or ""
    except Exception as e:
        print(f"[Alerta] no se pudo resolver el buzón del operador: {e}")
    return None


def _enviar_correo(asunto: str, cuerpo: str) -> None:
    buzon = _buzon_del_operador()
    if not buzon:
        print(
            f"[Alerta] SIN CANAL DE CORREO: no hay ningún admin del control plane "
            f"con Gmail conectado, así que este aviso sólo queda en el log y en "
            f"product_events. Asunto: {asunto}"
        )
        return
    user_id, access_token, refresh_token = buzon
    try:
        from app.services.gmail_service import get_gmail_service, send_email

        service, _ = get_gmail_service(access_token, refresh_token)
        # `from_email="me"` deja que Gmail resuelva la dirección de la cuenta
        # autenticada — no hace falta saber cuál es.
        send_email(service, DESTINO_OPERACION, asunto, cuerpo, "me")
        print(f"[Alerta] correo enviado a {DESTINO_OPERACION}: {asunto}")
    except Exception as e:
        print(f"[Alerta] no se pudo enviar el correo a {DESTINO_OPERACION}: {e}")


def alertar(
    *, evento: str, asunto: str, cuerpo: str,
    clave_idempotencia: str, metadata: Optional[dict] = None,
) -> None:
    """Registra el aviso en el control plane y dispara el correo en background.

    `clave_idempotencia` tiene que ser estable para el mismo hecho (ej.
    `gemini-budget:2026-08-25:20.0`) — es lo que evita la fila duplicada.
    """
    try:
        from app.services.control_plane_telemetry import registrar_evento_producto

        registrar_evento_producto(
            evento,
            status="warning",
            clave_idempotencia=clave_idempotencia,
            metadata=metadata or {},
        )
    except Exception as e:
        print(f"[Alerta] no se pudo registrar el evento en el control plane: {e}")

    # En background: el usuario que disparó esto no tiene por qué esperar a que
    # Gmail responda. `daemon` para no demorar un apagado de Railway.
    try:
        threading.Thread(
            target=_enviar_correo, args=(asunto, cuerpo),
            name="alerta-operacional", daemon=True,
        ).start()
    except Exception as e:
        print(f"[Alerta] no se pudo lanzar el envío en background: {e}")
