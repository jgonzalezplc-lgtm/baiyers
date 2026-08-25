"""Medidor de gasto de Gemini — avisa, nunca corta.

Motivo: la cuenta de Gemini es PAGADA, así que un endpoint que llame al modelo
en loop (o un abuso) factura sin freno. El único techo real hoy es el saldo
prepago de AI Studio con recarga automática desactivada — sirve, pero se entera
uno cuando el servicio ya se cortó.

Esto es un contador, no un candado: **jamás bloquea una llamada**. Un umbral mal
calibrado que corte a un usuario legítimo en medio de una cotización es peor que
la factura que evita. Cuando el gasto estimado del día cruza un escalón, escribe
un WARNING en el log de Railway (donde ya miras cuando algo anda mal) y sigue.

Cómo mide, y por qué así: en vez de instrumentar los 20 sitios que construyen un
`GenerativeModel` —que se olvida en el sitio 21— envuelve una sola vez los
métodos del SDK. Cubre todo el backend, incluido el código que se escriba
mañana, y no hay forma de "olvidarse" de medir.

Lo que NO es:
  - No es preciso al centavo. Usa el catálogo de precios de
    `control_plane_telemetry.DEFAULT_PRICES`, que puede quedar viejo, y no
    distingue tarifas de contexto largo ni de caché.
  - No persiste. El contador vive en memoria y por proceso: si hay varias
    réplicas, cada una lleva su propia cuenta y el total real es la suma. Con
    una sola instancia en Railway hoy alcanza; si se escala, el número correcto
    hay que sacarlo de `ai_usage_events`.
  - No reemplaza la cuota de la API en la consola de Google, que es el único
    corte duro del lado del proveedor.
"""
from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal
from typing import Any

# Escalones de aviso en USD de gasto estimado por día. El primero es
# deliberadamente bajo: el consumo real ronda 1.500 CLP/mes (~1,6 USD), así que
# un solo día de 5 USD ya es una anomalía que vale mirar.
ESCALONES_USD: tuple[float, ...] = (5.0, 20.0, 50.0, 100.0)

_lock = threading.Lock()
_dia: date | None = None
_gasto_usd = Decimal("0")
_llamadas = 0
_avisados: set[float] = set()


def _hoy() -> date:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date()


def estado() -> dict[str, Any]:
    """Snapshot para diagnóstico. No es una fuente contable."""
    with _lock:
        return {
            "dia": str(_dia) if _dia else None,
            "gasto_estimado_usd": float(_gasto_usd),
            "llamadas": _llamadas,
            "escalones_avisados": sorted(_avisados),
            "nota": "estimación en memoria y por proceso — ver ai_usage_events para el dato real",
        }


def registrar(modelo: str, input_tokens: int, output_tokens: int) -> None:
    """Suma una llamada y avisa si cruzó un escalón. Nunca lanza."""
    try:
        from app.services.control_plane_telemetry import estimar_costo_usd

        costo, _ = estimar_costo_usd("google", modelo, input_tokens, output_tokens)
        cruzados: list[float] = []
        with _lock:
            global _dia, _gasto_usd, _llamadas
            hoy = _hoy()
            if _dia != hoy:            # día nuevo, contador limpio
                _dia, _gasto_usd, _llamadas = hoy, Decimal("0"), 0
                _avisados.clear()
            _gasto_usd += costo
            _llamadas += 1
            total = float(_gasto_usd)
            for escalon in ESCALONES_USD:
                if total >= escalon and escalon not in _avisados:
                    _avisados.add(escalon)
                    cruzados.append(escalon)
            llamadas = _llamadas

        # Fuera del lock: ni el log ni el envío del aviso deben serializar las
        # llamadas a Gemini.
        for escalon in cruzados:
            print(
                f"[GeminiBudget] ALERTA: el gasto estimado de hoy superó "
                f"USD {escalon:.2f} (total {total:.2f} en {llamadas} llamadas, "
                f"último modelo {modelo}). Es una estimación por proceso; "
                f"confirmá en AI Studio antes de sacar conclusiones."
            )
            _alertar(escalon, total, llamadas, modelo)
    except Exception as e:                      # nunca romper una llamada real
        print(f"[GeminiBudget] no se pudo contabilizar la llamada: {e}")


def _alertar(escalon: float, total: float, llamadas: int, modelo: str) -> None:
    """Manda el aviso al control plane y al correo de operación. Nunca lanza:
    el medidor no puede romper la llamada que lo disparó."""
    try:
        from app.services.alerta_operacional import DESTINO_OPERACION, alertar

        dia = _dia or _hoy()
        alertar(
            evento="gemini_budget_alerta",
            clave_idempotencia=f"gemini-budget:{dia}:{escalon}",
            asunto=f"[Baiyer] Gemini superó USD {escalon:.0f} estimados hoy",
            cuerpo=(
                f"El gasto estimado de Gemini del {dia} cruzó el escalón de "
                f"USD {escalon:.2f}.\n\n"
                f"  Total estimado hoy : USD {total:.2f}\n"
                f"  Llamadas           : {llamadas}\n"
                f"  Último modelo      : {modelo}\n\n"
                "Ojo con qué es este número: es una ESTIMACIÓN calculada en "
                "memoria y por proceso, con un catálogo de precios que puede "
                "estar viejo. No distingue tarifas de contexto largo ni de "
                "caché, y si hay varias réplicas cada una cuenta por su lado.\n\n"
                "El dato real está en AI Studio y en la tabla ai_usage_events. "
                "Confirmá ahí antes de tomar cualquier decisión.\n\n"
                "Este aviso no cortó ninguna llamada: el medidor sólo avisa.\n"
            ),
            metadata={
                "escalon_usd": escalon, "total_estimado_usd": round(total, 4),
                "llamadas": llamadas, "modelo": modelo, "destino": DESTINO_OPERACION,
            },
        )
    except Exception as e:
        print(f"[GeminiBudget] no se pudo emitir la alerta: {e}")


def _tokens(respuesta: Any) -> tuple[int, int]:
    uso = getattr(respuesta, "usage_metadata", None)
    return (
        getattr(uso, "prompt_token_count", 0) or 0,
        getattr(uso, "candidates_token_count", 0) or 0,
    )


def _nombre_modelo(modelo: Any) -> str:
    """El SDK expone `model_name` como "models/gemini-2.5-flash", pero el
    catálogo de precios usa la clave corta."""
    nombre = getattr(modelo, "model_name", "") or "desconocido"
    return nombre.split("/")[-1]


def instrumentar() -> None:
    """Envuelve `GenerativeModel.generate_content[_async]` una sola vez.

    Idempotente: marca la función envuelta, así que un segundo llamado (tests,
    reload del módulo en dev) no apila wrappers.
    """
    try:
        import google.generativeai as genai
    except Exception as e:
        print(f"[GeminiBudget] SDK de Gemini no disponible, sin medición: {e}")
        return

    modelo_cls = genai.GenerativeModel

    for nombre, es_async in (("generate_content", False), ("generate_content_async", True)):
        original = getattr(modelo_cls, nombre, None)
        if original is None or getattr(original, "_baiyer_medido", False):
            continue

        if es_async:
            async def envuelto(self, *args, _original=original, **kwargs):
                respuesta = await _original(self, *args, **kwargs)
                entrada, salida = _tokens(respuesta)
                registrar(_nombre_modelo(self), entrada, salida)
                return respuesta
        else:
            def envuelto(self, *args, _original=original, **kwargs):
                respuesta = _original(self, *args, **kwargs)
                entrada, salida = _tokens(respuesta)
                registrar(_nombre_modelo(self), entrada, salida)
                return respuesta

        envuelto._baiyer_medido = True
        setattr(modelo_cls, nombre, envuelto)
