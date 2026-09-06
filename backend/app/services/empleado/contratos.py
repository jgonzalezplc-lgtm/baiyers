"""Contrato independiente del canal para el empleado digital.

El cerebro nunca recibe un objeto Gmail, Slack o WhatsApp. Recibe estas
estructuras y devuelve una respuesta con una ruta opaca que sólo entiende el
adaptador de origen. Así el modelo no puede inventar otro destinatario.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class Canal(StrEnum):
    CORREO = "correo"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    TEAMS = "teams"


@dataclass(frozen=True)
class IdentidadExterna:
    """Identificador nativo del remitente, aún sin asumir que es un usuario."""

    canal: Canal
    valor: str
    nombre_visible: str | None = None
    verificada: bool = False


@dataclass(frozen=True)
class AdjuntoEntrante:
    nombre: str
    mime_type: str | None = None
    referencia: str | None = None


@dataclass(frozen=True)
class RutaRespuesta:
    """Destino opaco, emitido por el adaptador y no manipulable por el modelo."""

    canal: Canal
    hilo: str
    destinatario: str
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MensajeEntrante:
    canal: Canal
    identidad: IdentidadExterna
    texto: str
    ruta_respuesta: RutaRespuesta
    mensaje_id: str
    hilo_id: str
    adjuntos: tuple[AdjuntoEntrante, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.identidad.canal != self.canal or self.ruta_respuesta.canal != self.canal:
            raise ValueError("La identidad y la ruta deben pertenecer al canal de entrada")
        if not self.mensaje_id or not self.hilo_id:
            raise ValueError("Todo mensaje debe tener identificador e hilo estables")


@dataclass(frozen=True)
class RespuestaSaliente:
    texto: str
    ruta: RutaRespuesta
    metadata: Mapping[str, Any] = field(default_factory=dict)
