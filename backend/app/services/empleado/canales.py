"""Configuración de canales corporativos del empleado digital."""
from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.services.auth_context import AuthContext

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalizar_email(valor: str) -> str:
    email = (valor or "").strip().lower()
    if not _EMAIL.fullmatch(email):
        raise HTTPException(status_code=422, detail="La dirección operativa no es un correo válido")
    return email


def crear_canal_correo(sb, ctx: AuthContext, *, direccion_operativa: str, etiqueta_gmail: str) -> dict[str, Any]:
    """Crea o actualiza el borrador de canal; nunca almacena tokens acá."""
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Sólo un administrador puede configurar el correo del empleado")
    etiqueta = (etiqueta_gmail or "").strip()
    if not etiqueta or len(etiqueta) > 100:
        raise HTTPException(status_code=422, detail="Define una etiqueta Gmail de hasta 100 caracteres")
    fila = {
        "organizacion_id": ctx.organization_id,
        "canal": "correo",
        "estado": "borrador",
        "direccion_operativa": _normalizar_email(direccion_operativa),
        "etiqueta_gmail": etiqueta,
        "ultimo_error": None,
    }
    resultado = sb.table("canales_empleado").upsert(
        fila, on_conflict="organizacion_id,canal",
    ).execute()
    return _publico(resultado.data[0])


def obtener_canales(sb, ctx: AuthContext) -> list[dict[str, Any]]:
    resultado = sb.table("canales_empleado").select(
        "id,canal,estado,direccion_operativa,cuenta_autorizada,etiqueta_gmail,ultimo_error,created_at,updated_at"
    ).eq("organizacion_id", ctx.organization_id).order("created_at").execute()
    return [_publico(fila) for fila in (resultado.data or [])]


def _publico(fila: dict[str, Any]) -> dict[str, Any]:
    """Defensa contra una regresión que exponga tokens en la API de settings."""
    return {clave: fila.get(clave) for clave in (
        "id", "canal", "estado", "direccion_operativa", "cuenta_autorizada",
        "etiqueta_gmail", "ultimo_error", "created_at", "updated_at",
    )}
