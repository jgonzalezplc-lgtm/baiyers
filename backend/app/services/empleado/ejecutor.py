"""Barrera de herramientas del empleado digital.

La autorización se decide acá, antes de que corra una capacidad. Un argumento
`confirmed` llegado desde un modelo no tiene valor de seguridad y se elimina.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.tool_registry import Efecto, ToolSpec, spec


@dataclass(frozen=True)
class AutorizacionHumana:
    """Referencia trazable a una aprobación persistida; nunca un booleano."""

    id: str
    responsable_id: str
    herramienta: str
    vigente: bool


class ValidadorAutorizacion(Protocol):
    def __call__(self, actor: ApplicationActorContext, aprobacion: AutorizacionHumana) -> bool: ...


class HandlerTool(Protocol):
    def __call__(self, actor: ApplicationActorContext, argumentos: Mapping[str, Any]) -> Any | Awaitable[Any]: ...


class Auditor(Protocol):
    def __call__(self, evento: "EventoTool") -> None: ...


@dataclass(frozen=True)
class EventoTool:
    herramienta: str
    efecto: Efecto
    actor_user_id: str
    organization_id: str
    resultado: str  # ejecutada | bloqueada | fallida
    autorizacion_id: str | None = None
    motivo: str | None = None


def _sin_confirmacion_del_modelo(argumentos: Mapping[str, Any]) -> dict[str, Any]:
    """Evita que `confirmed=true` sea una ruta lateral alrededor de la barrera."""
    return {clave: valor for clave, valor in argumentos.items() if clave != "confirmed"}


class EjecutorTools:
    """Ejecuta sólo handlers allowlisteados y clasificados en ``tool_registry``."""

    def __init__(
        self,
        handlers: Mapping[str, HandlerTool],
        *,
        validar_autorizacion: ValidadorAutorizacion,
        auditar: Auditor | None = None,
    ) -> None:
        self._handlers = dict(handlers)
        self._validar_autorizacion = validar_autorizacion
        self._auditar = auditar or (lambda _evento: None)

    def ejecutar(
        self,
        actor: ApplicationActorContext,
        herramienta: str,
        argumentos: Mapping[str, Any],
        *,
        autorizacion: AutorizacionHumana | None = None,
    ) -> Any:
        declaracion = spec(herramienta)
        handler = self._handlers.get(herramienta)
        if handler is None:
            self._registrar(actor, herramienta, declaracion, "bloqueada", motivo="handler_no_allowlisteado")
            raise HTTPException(status_code=403, detail="La capacidad no está habilitada para el empleado digital")

        try:
            actor.require_scope(declaracion.scope)
            self._exigir_barrera(actor, herramienta, declaracion, autorizacion)
            resultado = handler(actor, _sin_confirmacion_del_modelo(argumentos))
            if inspect.isawaitable(resultado):
                # El adaptador asíncrono debe usar ``ejecutar_async``. No iniciar
                # loops ocultos desde una llamada síncrona hace el borde predecible.
                raise RuntimeError("El handler asíncrono requiere ejecutar_async")
        except Exception as exc:
            if isinstance(exc, HTTPException) and exc.status_code == 403:
                self._registrar(actor, herramienta, declaracion, "bloqueada", autorizacion, str(exc.detail))
            else:
                self._registrar(actor, herramienta, declaracion, "fallida", autorizacion, type(exc).__name__)
            raise
        self._registrar(actor, herramienta, declaracion, "ejecutada", autorizacion)
        return resultado

    async def ejecutar_async(
        self,
        actor: ApplicationActorContext,
        herramienta: str,
        argumentos: Mapping[str, Any],
        *,
        autorizacion: AutorizacionHumana | None = None,
    ) -> Any:
        declaracion = spec(herramienta)
        handler = self._handlers.get(herramienta)
        if handler is None:
            self._registrar(actor, herramienta, declaracion, "bloqueada", motivo="handler_no_allowlisteado")
            raise HTTPException(status_code=403, detail="La capacidad no está habilitada para el empleado digital")
        try:
            actor.require_scope(declaracion.scope)
            self._exigir_barrera(actor, herramienta, declaracion, autorizacion)
            resultado = handler(actor, _sin_confirmacion_del_modelo(argumentos))
            if inspect.isawaitable(resultado):
                resultado = await resultado
        except Exception as exc:
            if isinstance(exc, HTTPException) and exc.status_code == 403:
                self._registrar(actor, herramienta, declaracion, "bloqueada", autorizacion, str(exc.detail))
            else:
                self._registrar(actor, herramienta, declaracion, "fallida", autorizacion, type(exc).__name__)
            raise
        self._registrar(actor, herramienta, declaracion, "ejecutada", autorizacion)
        return resultado

    def _exigir_barrera(
        self,
        actor: ApplicationActorContext,
        herramienta: str,
        declaracion: ToolSpec,
        autorizacion: AutorizacionHumana | None,
    ) -> None:
        if declaracion.efecto not in {Efecto.EXTERNO, Efecto.DINERO}:
            return
        if not autorizacion or autorizacion.herramienta != herramienta or not autorizacion.vigente:
            raise HTTPException(status_code=403, detail="Esta acción exige una autorización humana vigente")
        if not self._validar_autorizacion(actor, autorizacion):
            raise HTTPException(status_code=403, detail="La autorización humana no es válida para esta organización")

    def _registrar(
        self,
        actor: ApplicationActorContext,
        herramienta: str,
        declaracion: ToolSpec,
        resultado: str,
        autorizacion: AutorizacionHumana | None = None,
        motivo: str | None = None,
    ) -> None:
        self._auditar(EventoTool(
            herramienta=herramienta,
            efecto=declaracion.efecto,
            actor_user_id=actor.actor_user_id,
            organization_id=actor.organization_id,
            resultado=resultado,
            autorizacion_id=autorizacion.id if autorizacion else None,
            motivo=motivo,
        ))
