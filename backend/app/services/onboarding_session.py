"""
Sesión de onboarding conversacional persistida (Fase 1 del rediseño).

Antes, todo el estado de la conversación de onboarding vivía en React
(`OnboardingChat.tsx`) — si el usuario recargaba la página a mitad de
camino, se perdía. Este módulo mueve esa verdad a `onboarding_sessions`
(migración 034): un `draft` por campo con confianza/origen/confirmación,
mensajes y preguntas pendientes, reanudable entre sesiones del navegador.

Campos críticos que deben estar confirmados antes de poder cerrar la
sesión como `completado`.
"""
from datetime import datetime, timezone
from typing import Optional

# El orden también define la entrevista: primero conocemos a la persona y
# recién después investigamos su empresa.
CAMPOS_CRITICOS = ("nombre_usuario", "empresa", "rut")


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def crear_o_reanudar_sesion(user_id: str) -> dict:
    """Devuelve la sesión `en_progreso`/`esperando_confirmacion` más reciente
    del usuario, o crea una nueva si no tiene ninguna abierta. Nunca reanuda
    una sesión ya `completado`/`abandonado` — esas quedan como historial."""
    sb = _sb()
    abierta = sb.table("onboarding_sessions").select("*").eq("user_id", user_id).in_(
        "estado", ["en_progreso", "esperando_confirmacion"]
    ).order("created_at", desc=True).limit(1).execute().data
    if abierta:
        return abierta[0]

    nueva = sb.table("onboarding_sessions").insert({
        "user_id": user_id,
        "estado": "en_progreso",
        "draft": {},
        "mensajes": [],
        "preguntas_pendientes": [],
    }).execute().data
    return nueva[0]


def obtener_sesion(session_id: str, user_id: str) -> Optional[dict]:
    """Devuelve la sesión si pertenece a `user_id`, o None si no existe/no
    es dueño — el router debe traducir None a 404, nunca filtrar existencia
    de sesiones ajenas con un mensaje distinto."""
    sb = _sb()
    # `.maybe_single()` en postgrest-py 2.x devuelve `None` desde `.execute()`
    # (no un objeto con `.data = None`) cuando no hay ninguna fila — hay que
    # chequear antes de acceder a `.data`, o una sesión inexistente/ajena
    # crashea con 500 en vez de devolver el 404 esperado.
    resp = sb.table("onboarding_sessions").select("*").eq("id", session_id).eq(
        "user_id", user_id
    ).maybe_single().execute()
    return resp.data if resp else None


def fusionar_draft(draft_actual: dict, actualizaciones: dict) -> dict:
    """Combina el draft existente con nuevos valores extraídos del turno.

    Un campo ya `confirmado=True` NO se sobreescribe salvo que la
    actualización venga marcada explícitamente como `correccion=True` (el
    usuario dijo "no, es X" sobre un campo que ya había confirmado antes).
    Esto evita que una mención ambigua posterior pise un dato ya cerrado."""
    resultado = dict(draft_actual or {})
    for campo, nuevo in (actualizaciones or {}).items():
        existente = resultado.get(campo)
        es_correccion = bool(nuevo.get("correccion"))
        if existente and existente.get("confirmado") and not es_correccion:
            continue
        resultado[campo] = {
            "valor": nuevo.get("valor"),
            "confianza": nuevo.get("confianza", "media"),
            "origen": nuevo.get("origen", "usuario"),
            "confirmado": bool(nuevo.get("confirmado")),
            "evidencia": nuevo.get("evidencia", ""),
        }
    return resultado


def campos_faltantes(draft: dict) -> list[str]:
    faltan = []
    for campo in CAMPOS_CRITICOS:
        entrada = (draft or {}).get(campo)
        if not entrada or not entrada.get("confirmado") or not entrada.get("valor"):
            faltan.append(campo)
    return faltan


def guardar_turno(
    session_id: str, user_id: str, mensaje_usuario: str, mensajes_asistente: list[str],
    draft_nuevo: dict, preguntas_pendientes: list[str],
    propuesta_workflow: Optional[dict], estado: str,
) -> dict:
    """Persiste el resultado de un turno completo. Siempre reemplaza
    `draft`/`preguntas_pendientes` con el estado ya fusionado (calculado por
    el llamador vía `fusionar_draft`) — este módulo no vuelve a fusionar acá
    para no aplicar la lógica de merge dos veces."""
    sb = _sb()
    fila = obtener_sesion(session_id, user_id)
    if not fila:
        raise ValueError("Sesión no encontrada")

    mensajes = list(fila.get("mensajes") or [])
    mensajes.append({"rol": "usuario", "texto": mensaje_usuario, "ts": _ahora()})
    for texto in mensajes_asistente:
        mensajes.append({"rol": "asistente", "texto": texto, "ts": _ahora()})

    actualizacion = {
        "draft": draft_nuevo,
        "mensajes": mensajes,
        "preguntas_pendientes": preguntas_pendientes,
        "estado": estado,
        "version": (fila.get("version") or 1) + 1,
        "updated_at": _ahora(),
    }
    if propuesta_workflow is not None:
        actualizacion["propuesta_workflow"] = propuesta_workflow

    actualizada = sb.table("onboarding_sessions").update(actualizacion).eq(
        "id", session_id
    ).execute().data
    return actualizada[0]
