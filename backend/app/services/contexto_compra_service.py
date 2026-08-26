"""Lectura de las señales de una compra y armado de su contexto de proceso.

Separado de `contexto_compra` (núcleo puro) por la misma razón que
`workflow_service` está separado de `workflow_engine`: la lógica de "en qué
etapa estoy" se puede probar sin base de datos, y acá vive sólo el acceso.

**Sólo lectura.** Ninguna función de este módulo escribe.
"""
from dataclasses import replace
from typing import Any, Optional

from app.services.contexto_compra import Senales, construir_contexto, derivar_etapa
from app.services.lista_service import get_list
from app.services.mcp_context import ApplicationActorContext
from app.services.supabase import ejecutar_maybe_single

# Estados de conversación que significan "una persona tiene que mirar esto".
_ESTADOS_REVISION = ("human_review_required", "clarification_required")
_ESTADOS_RESPONDIDA = ("supplier_replied", "partially_answered", "complete", "closed", "compra_iniciada")


def obtener_contexto_compra(
    sb, actor: ApplicationActorContext, list_id: str, *,
    lista: Optional[dict] = None,
) -> dict[str, Any]:
    """Contexto de proceso de una lista. Nunca escribe, nunca lanza por datos
    faltantes: una tabla ausente degrada la señal, no tumba la respuesta.

    `lista` permite reusar la que el llamador ya cargó. Importa cuando esto se
    embebe en otra respuesta: sin eso, `compare_list` leería la lista dos veces.
    """
    lista = lista or get_list(sb, actor, list_id)
    senales = _leer_senales(sb, actor, lista)

    grafo = _contexto_de_grafo(sb, actor, list_id)
    if grafo:
        return construir_contexto(
            list_id, senales, origen="grafo",
            etapa=grafo["etapa"], etiqueta=grafo["etiqueta"],
            completadas=grafo["completadas"], pendientes=grafo["pendientes"],
            transiciones=grafo["transiciones"], aprobaciones=grafo["aprobaciones"],
        )
    return construir_contexto(list_id, senales)


def bloque_proceso(
    sb, actor: ApplicationActorContext, list_id: Optional[str], *,
    lista: Optional[dict] = None,
) -> dict[str, Any]:
    """`{"process": {...}}` para adjuntar a la respuesta de otra tool.

    Vista reducida del mismo contexto: etapa, avance, bloqueos y qué sigue. Se
    omiten transiciones y aprobaciones, que sólo interesan cuando alguien
    pregunta explícitamente por el proceso (`get_purchase_context`).

    **Nunca lanza.** Es un adorno informativo de la respuesta de otra tool: si
    fallara, rompería una operación que sí funcionó. Ante cualquier problema
    devuelve `{}` y el llamador responde como antes.
    """
    if not list_id:
        return {}
    try:
        contexto = obtener_contexto_compra(sb, actor, list_id, lista=lista)
    except Exception as e:
        print(f"[ContextoCompra] no se pudo armar el bloque: {type(e).__name__}: {e}")
        return {}
    return {"process": {
        "etapa_actual": contexto["etapa_actual"],
        "etapa_label": contexto["etapa_label"],
        "origen": contexto["origen"],
        "completadas": contexto["completadas"],
        "pendientes": contexto["pendientes"],
        "bloqueos": contexto["bloqueos"],
        "proximas_acciones": contexto["proximas_acciones"],
    }}


def _leer_senales(sb, actor: ApplicationActorContext, lista: dict) -> Senales:
    """Carga en dos pasadas: primero lo barato, que ya define la etapa; después
    sólo las señales que esa etapa puede necesitar.

    Sin esto, embeber el contexto en siete respuestas haría que TODAS pagaran
    consultas que sólo importan al emitir una OC (correo del proveedor,
    dirección de despacho, homologación). La etapa se deriva igual, porque
    ninguna de esas señales participa de `derivar_etapa` — sólo de los bloqueos.
    """
    items = lista.get("items") or []
    definitivos = lista.get("definitivos") or {}
    lista_id = lista["id"]

    basicas = Senales(
        items_total=len(items),
        rfq_preparadas=_contar(sb, "rfq_batches", lista_id, "estado", ["draft", "ready_to_send"]),
        rfq_enviadas=_contar(sb, "rfq_batches", lista_id, "estado", ["sent", "sending", "delivery_uncertain"]),
        respuestas_recibidas=_contar(sb, "gmail_conversations", lista_id, "estado", list(_ESTADOS_RESPONDIDA)),
        conversaciones_en_revision=_contar(sb, "gmail_conversations", lista_id, "estado", list(_ESTADOS_REVISION)),
        definitivos=len(definitivos),
        definitivos_sin_precio=sum(
            1 for d in definitivos.values()
            if d.get("precio") in (None, "") and d.get("precio_clp") in (None, "")
        ),
        aprobacion_estado=(lista.get("aprobacion") or {}).get("estado"),
        requiere_aprobacion=bool(lista.get("aprobacion")),
        ocs_creadas=_contar(sb, "ordenes_compra", lista_id, "estado", ["borrador"]),
        ocs_enviadas=_contar(sb, "ordenes_compra", lista_id, "estado",
                             ["enviada", "confirmada", "recibido_conforme", "despachada"]),
    )

    extra: dict[str, Any] = {
        "proveedores_sin_homologar": _contar_homologacion_pendiente(sb, lista_id),
    }
    if derivar_etapa(basicas) == "emision_oc":
        ids = [d.get("resultado_id") for d in definitivos.values() if d.get("resultado_id")]
        extra["definitivos_sin_email"] = _contar_sin_email(sb, ids)
        extra["tiene_direccion_despacho"] = _tiene_despacho(actor)
    else:
        # No se consultan, y tampoco se reportan como faltantes: fuera de la
        # emisión no bloquean nada y un `False` acá se leería como un problema.
        extra["tiene_direccion_despacho"] = True

    return replace(basicas, **extra)


def _contar(sb, tabla: str, lista_id: str, columna: str, valores: list[str]) -> int:
    """Cuenta filas de una tabla asociadas a la lista. Una tabla o columna que
    no exista devuelve 0: la señal se pierde, el contexto no."""
    try:
        res = sb.table(tabla).select("id", count="exact").eq(
            "lista_proyecto_id", lista_id
        ).in_(columna, valores).execute()
        return res.count or 0
    except Exception as e:
        print(f"[ContextoCompra] no se pudo contar {tabla}: {type(e).__name__}: {e}")
        return 0


def _contar_items_con_ofertas(sb, items: list[dict]) -> int:
    ids = [i.get("cotizacion_id") for i in items if i.get("cotizacion_id")]
    if not ids:
        return 0
    try:
        filas = sb.table("resultados").select("cotizacion_id").in_("cotizacion_id", ids).execute().data or []
        return len({f["cotizacion_id"] for f in filas})
    except Exception:
        return 0


def _contar_sin_email(sb, ids_resultado: list[str]) -> int:
    if not ids_resultado:
        return 0
    try:
        filas = sb.table("resultados").select("id,proveedor_email").in_("id", ids_resultado).execute().data or []
        return sum(1 for f in filas if not (f.get("proveedor_email") or "").strip())
    except Exception:
        return 0


def _contar_homologacion_pendiente(sb, lista_id: str) -> int:
    try:
        res = sb.table("supplier_homologation_cases").select("id", count="exact").eq(
            "lista_proyecto_id", lista_id
        ).in_("estado", ["pendiente", "antecedentes_solicitados", "antecedentes_recibidos"]).execute()
        return res.count or 0
    except Exception:
        # La 043 puede no estar aplicada, o la lista puede no usar homologación.
        return 0


def _tiene_despacho(actor: ApplicationActorContext) -> bool:
    from app.services.organizacion import obtener_despacho_organizacion
    return bool(obtener_despacho_organizacion(actor.organization_id))


# ─── Modo grafo ──────────────────────────────────────────────────────────────

def _contexto_de_grafo(sb, actor: ApplicationActorContext, list_id: str) -> Optional[dict]:
    """Etapa real del workflow, o None si esta compra no corre en `unified`.

    Devolver None es el caso normal hoy: el rollout arranca en `legacy` y la
    Fase G todavía no tiene su checkpoint productivo. No es un error.
    """
    try:
        instancia = ejecutar_maybe_single(
            sb.table("workflow_instances").select("*").eq("lista_proyecto_id", list_id)
            .eq("execution_owner", "unified").in_("estado_workflow", ["activo", "pausado"])
            .order("created_at", desc=True).limit(1).maybe_single()
        ).data
    except Exception as e:
        print(f"[ContextoCompra] sin instancia de workflow: {type(e).__name__}: {e}")
        return None
    if not instancia:
        return None

    try:
        workflow = ejecutar_maybe_single(
            sb.table("workflow_definitions").select("nodos,conexiones")
            .eq("id", instancia["workflow_id"]).maybe_single()
        ).data or {}
        nodos = workflow.get("nodos") or []
        conexiones = workflow.get("conexiones") or []
        nodo_id = instancia.get("nodo_actual_id")
        nodo = next((n for n in nodos if n.get("id") == nodo_id), None)

        visitados = sb.table("workflow_node_executions").select("nodo_id,estado").eq(
            "workflow_instance_id", instancia["id"]
        ).execute().data or []
        completadas = [v["nodo_id"] for v in visitados
                       if v.get("estado") == "completada" and v.get("nodo_id") != nodo_id]

        # Las transiciones salen del grafo, no de un orden fijo: un proceso real
        # puede volver atrás ("rechazado → volver a cotizar").
        transiciones = [
            {"hacia": c.get("hasta") or c.get("destino"), "resultado": c.get("resultado")}
            for c in conexiones
            if (c.get("desde") or c.get("origen")) == nodo_id
        ]
        pendientes = [n["id"] for n in nodos
                      if n.get("id") not in completadas and n.get("id") != nodo_id]

        return {
            "etapa": nodo_id or "desconocida",
            "etiqueta": (nodo or {}).get("label") or (nodo or {}).get("titulo") or nodo_id or "",
            "completadas": completadas,
            "pendientes": pendientes,
            "transiciones": transiciones,
            "aprobaciones": _aprobaciones_del_nodo(sb, instancia, nodo),
        }
    except Exception as e:
        # Si el grafo no se puede leer, mejor caer al derivado que no responder.
        print(f"[ContextoCompra] no se pudo leer el grafo: {type(e).__name__}: {e}")
        return None


def _aprobaciones_del_nodo(sb, instancia: dict, nodo: Optional[dict]) -> list[dict]:
    if not nodo:
        return []
    try:
        asignaciones = sb.table("workflow_node_assignments").select("*").eq(
            "workflow_id", instancia["workflow_id"]
        ).eq("nodo_id", nodo.get("id")).execute().data or []
        return [{"rol": a.get("rol_clave"), "responsable_id": a.get("responsable_id"),
                 "modo": a.get("modo")} for a in asignaciones]
    except Exception:
        return []
