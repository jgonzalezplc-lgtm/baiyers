"""Contratos puros de la automatización por tarjeta (PRD Fase A).

Este módulo no toca Supabase ni envía correos. Centraliza validación y claves
idempotentes para que canvas, activación, scheduler y tests usen las mismas
reglas cuando las fases siguientes conecten ejecución real.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.mail_events import EVENTOS


MODOS_ASIGNACION = {"individual", "paralelo", "secuencial"}
AUDIENCIAS = {"internal", "external"}
DESTINATARIOS = {
    "responsable_rol", "solicitante", "autorizador", "equipo",
    "proveedor", "contacto_proveedor",
}
DESTINATARIOS_INTERNOS = {"responsable_rol", "solicitante", "autorizador", "equipo"}
DESTINATARIOS_EXTERNOS = {"proveedor", "contacto_proveedor"}
DISPARADORES = {"al_entrar", "al_ocurrir_evento", "manual", "despues_demora"}
ALCANCES_TERMINO = {"destinatario", "proveedor", "tarjeta"}
POLITICAS_AGOTAMIENTO = {"pausar", "escalar", "descartar_entidad", "avanzar_timeout"}

# Vocabulario canónico que las integraciones traducirán en fases D-F. Separar
# hechos de negocio de nombres de plantilla evita que "envié una OC" se
# confunda con "el proveedor confirmó la OC".
EVENTOS_DOMINIO = {
    "rfq_respuesta_recibida", "rfq_completa", "proveedor_descartado",
    "seleccion_enviada", "aprobado", "rechazado", "devuelto",
    "documentacion_completa", "proveedor_homologado", "proveedor_rechazado",
    "oc_emitida", "oc_recepcion_confirmada", "despacho_informado",
    "compra_recibida",
}
EVENTOS_TECNICOS = {
    "node_entered", "mail_reserved", "mail_sent", "mail_failed",
    "schedule_cancelled", "loop_exhausted", "node_completed",
    "transition_applied",
}


def _error(codigo: str, mensaje: str, *, nodo_id: str | None = None, regla_id: str | None = None) -> dict:
    error = {"codigo": codigo, "mensaje": mensaje}
    if nodo_id:
        error["nodo_id"] = nodo_id
    if regla_id:
        error["regla_id"] = regla_id
    return error


def validar_automatizacion(
    nodos: list[dict], conexiones: list[dict], asignaciones: list[dict], reglas: list[dict],
    responsables: dict[str, dict] | None = None,
) -> list[dict]:
    """Valida configuración por tarjeta sin depender de filas persistidas.

    `responsables` es opcional para permitir validación estructural antes de
    cargar el directorio. Si se entrega, valida activo/email para reglas
    internas. Los errores son datos mostrables, igual que `validar_grafo`.
    """
    errores: list[dict] = []
    por_id = {n.get("id"): n for n in nodos if n.get("id")}
    resultados_por_nodo = {n_id: set(n.get("resultados") or []) for n_id, n in por_id.items()}
    salidas = {
        (c.get("origen_nodo_id"), c.get("resultado") or "default")
        for c in conexiones
    }

    asignaciones_por_nodo_rol: dict[tuple[str, str], list[dict]] = {}
    for a in asignaciones:
        nodo_id, rol = a.get("nodo_id"), a.get("rol_clave")
        if nodo_id not in por_id:
            errores.append(_error("asignacion_nodo_inexistente", "La asignación referencia una tarjeta inexistente.", nodo_id=nodo_id))
            continue
        if not rol or rol not in (por_id[nodo_id].get("roles") or []):
            errores.append(_error("asignacion_rol_invalido", "El rol asignado no participa en esta tarjeta.", nodo_id=nodo_id))
            continue
        modo = a.get("modo", "individual")
        if modo not in MODOS_ASIGNACION:
            errores.append(_error("modo_asignacion_invalido", f"Modo de asignación inválido: {modo}.", nodo_id=nodo_id))
        if modo == "secuencial" and not isinstance(a.get("orden"), int):
            errores.append(_error("orden_secuencial_requerido", "Una asignación secuencial necesita orden entero.", nodo_id=nodo_id))
        if modo != "secuencial" and a.get("orden") is not None:
            errores.append(_error("orden_no_aplica", "El orden sólo aplica a asignaciones secuenciales.", nodo_id=nodo_id))
        asignaciones_por_nodo_rol.setdefault((nodo_id, rol), []).append(a)

        if responsables is not None:
            responsable = responsables.get(a.get("responsable_id"))
            if not responsable or not responsable.get("activo", False):
                errores.append(_error("responsable_inactivo", "La asignación requiere un responsable activo.", nodo_id=nodo_id))

    for nodo_id, nodo in por_id.items():
        if nodo.get("tipo") in {"tarea_humana", "revision", "autorizacion", "homologacion"}:
            for rol in nodo.get("roles") or []:
                if not asignaciones_por_nodo_rol.get((nodo_id, rol)):
                    errores.append(_error("rol_sin_responsable_nodo", f"El rol '{rol}' no tiene responsable en esta tarjeta.", nodo_id=nodo_id))

    for (nodo_id, rol), grupo in asignaciones_por_nodo_rol.items():
        modos = {a.get("modo", "individual") for a in grupo}
        if len(modos) > 1:
            errores.append(_error("modos_asignacion_mezclados", f"El rol '{rol}' mezcla modos de asignación en la misma tarjeta.", nodo_id=nodo_id))
        elif modos == {"individual"} and len(grupo) > 1:
            errores.append(_error("asignacion_individual_multiple", f"El rol '{rol}' está en modo individual pero tiene más de un responsable.", nodo_id=nodo_id))
        elif modos == {"secuencial"}:
            ordenes = [a.get("orden") for a in grupo]
            if len([o for o in ordenes if isinstance(o, int)]) != len(set(o for o in ordenes if isinstance(o, int))):
                errores.append(_error("orden_secuencial_duplicado", f"El rol '{rol}' tiene órdenes secuenciales repetidos.", nodo_id=nodo_id))

    for regla in reglas:
        regla_id = regla.get("id")
        nodo_id = regla.get("nodo_id")
        if nodo_id not in por_id:
            errores.append(_error("regla_nodo_inexistente", "La regla referencia una tarjeta inexistente.", nodo_id=nodo_id, regla_id=regla_id))
            continue
        evento = regla.get("evento_plantilla")
        catalogo = EVENTOS.get(evento)
        if not catalogo:
            errores.append(_error("evento_plantilla_inexistente", f"Evento de plantilla desconocido: {evento}.", nodo_id=nodo_id, regla_id=regla_id))
        elif catalogo.audiencia != regla.get("audiencia"):
            errores.append(_error("audiencia_incompatible", "La audiencia de la regla no coincide con la plantilla.", nodo_id=nodo_id, regla_id=regla_id))

        audiencia = regla.get("audiencia")
        destinatario = regla.get("destinatario_tipo")
        if audiencia not in AUDIENCIAS or destinatario not in DESTINATARIOS:
            errores.append(_error("destinatario_invalido", "La regla no tiene una audiencia/destinatario válido.", nodo_id=nodo_id, regla_id=regla_id))
        elif audiencia == "internal" and destinatario not in DESTINATARIOS_INTERNOS:
            errores.append(_error("destinatario_audiencia_incompatible", "Una comunicación interna no puede usar destinatario externo.", nodo_id=nodo_id, regla_id=regla_id))
        elif audiencia == "external" and destinatario not in DESTINATARIOS_EXTERNOS:
            errores.append(_error("destinatario_audiencia_incompatible", "Una comunicación externa debe resolverse desde un proveedor.", nodo_id=nodo_id, regla_id=regla_id))

        disparador = regla.get("disparador_tipo", "al_entrar")
        if disparador not in DISPARADORES:
            errores.append(_error("disparador_invalido", f"Disparador inválido: {disparador}.", nodo_id=nodo_id, regla_id=regla_id))
        if disparador == "al_ocurrir_evento" and not regla.get("disparador_evento"):
            errores.append(_error("disparador_evento_requerido", "El disparador por evento necesita indicar cuál.", nodo_id=nodo_id, regla_id=regla_id))

        intervalo = regla.get("repetir_cada_dias")
        if intervalo is not None and (not isinstance(intervalo, int) or intervalo < 1):
            errores.append(_error("intervalo_invalido", "La repetición debe ser un número entero de días mayor o igual a 1.", nodo_id=nodo_id, regla_id=regla_id))
        if intervalo is not None and not regla.get("evento_termino"):
            errores.append(_error("loop_sin_evento_termino", "Todo loop necesita un evento de término.", nodo_id=nodo_id, regla_id=regla_id))
        if intervalo is not None and not regla.get("politica_agotamiento"):
            errores.append(_error("loop_sin_politica_agotamiento", "Todo loop necesita una política de agotamiento.", nodo_id=nodo_id, regla_id=regla_id))

        max_intentos = regla.get("max_intentos")
        if max_intentos is not None and (not isinstance(max_intentos, int) or max_intentos < 1):
            errores.append(_error("max_intentos_invalido", "El máximo de intentos debe ser entero y mayor o igual a 1.", nodo_id=nodo_id, regla_id=regla_id))
        if max_intentos is not None and intervalo is None and max_intentos != 1:
            errores.append(_error("max_intentos_sin_loop", "Una comunicación no recurrente sólo puede tener un intento.", nodo_id=nodo_id, regla_id=regla_id))

        politica = regla.get("politica_agotamiento")
        if politica is not None and politica not in POLITICAS_AGOTAMIENTO:
            errores.append(_error("politica_agotamiento_invalida", f"Política de agotamiento inválida: {politica}.", nodo_id=nodo_id, regla_id=regla_id))
        if politica == "avanzar_timeout" and not regla.get("resultado_agotamiento"):
            errores.append(_error("resultado_timeout_requerido", "Avanzar por timeout necesita un resultado.", nodo_id=nodo_id, regla_id=regla_id))

        alcance = regla.get("alcance_termino", "tarjeta")
        if alcance not in ALCANCES_TERMINO:
            errores.append(_error("alcance_termino_invalido", f"Alcance de término inválido: {alcance}.", nodo_id=nodo_id, regla_id=regla_id))

        for campo in ("resultado_al_terminar", "resultado_agotamiento"):
            resultado = regla.get(campo)
            if resultado and resultado not in resultados_por_nodo.get(nodo_id, set()):
                errores.append(_error("resultado_no_declarado", f"El resultado '{resultado}' no está declarado en la tarjeta.", nodo_id=nodo_id, regla_id=regla_id))
            elif resultado and (nodo_id, resultado) not in salidas:
                errores.append(_error("resultado_sin_conexion", f"El resultado '{resultado}' no tiene conexión de salida.", nodo_id=nodo_id, regla_id=regla_id))

        if responsables is not None and audiencia == "internal" and regla.get("rol_clave"):
            asignadas = asignaciones_por_nodo_rol.get((nodo_id, regla["rol_clave"]), [])
            if not any((responsables.get(a.get("responsable_id")) or {}).get("email") for a in asignadas):
                errores.append(_error("responsable_sin_email", "La comunicación interna no tiene un responsable con email resoluble.", nodo_id=nodo_id, regla_id=regla_id))

    nodos_rfq = {
        r.get("nodo_id") for r in reglas
        if r.get("evento_plantilla") in {"rfq_requested", "rfq_followup"}
    }
    for nodo_id in nodos_rfq:
        nodo = por_id.get(nodo_id) or {}
        criterio = nodo.get("criterio_cierre") or "todos_resueltos"
        if criterio not in {"todos_resueltos", "minimo_respuestas", "cierre_manual"}:
            errores.append(_error(
                "criterio_cierre_rfq_invalido",
                "El cierre RFQ debe ser todos resueltos, mínimo de respuestas o manual.",
                nodo_id=nodo_id,
            ))
        minimo = nodo.get("minimo_respuestas")
        if criterio == "minimo_respuestas" and (
            not isinstance(minimo, int) or isinstance(minimo, bool) or minimo < 1
        ):
            errores.append(_error(
                "minimo_respuestas_rfq_invalido",
                "El cierre por mínimo requiere al menos una respuesta.", nodo_id=nodo_id,
            ))

    return errores


def clave_idempotencia(*, instance_id: str, nodo_id: str, visit_number: int,
                        rule_id: str, recipient_key: str, attempt_number: int) -> str:
    """Clave estable, opaca y sin PII visible para un intento funcional."""
    componentes = {
        "instance_id": instance_id,
        "nodo_id": nodo_id,
        "visit_number": visit_number,
        "rule_id": rule_id,
        "recipient_key": recipient_key.strip().lower(),
        "attempt_number": attempt_number,
    }
    canonical = json.dumps(componentes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "workflow-mail:v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def proximo_vencimiento(desde: datetime, dias: int) -> datetime:
    if not isinstance(dias, int) or dias < 1:
        raise ValueError("dias debe ser un entero mayor o igual a 1")
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    return desde + timedelta(days=dias)
