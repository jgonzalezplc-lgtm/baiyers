"""Dónde está una compra dentro del proceso, y qué se puede hacer ahora.

Existe porque las tools MCP son acciones sueltas: cada una sabe hacer lo suyo,
ninguna sabe en qué etapa está la compra ni qué la bloquea. El cliente tenía que
reconstruirlo llamando media docena de tools y adivinando.

**Es de sólo lectura.** Deliberadamente separado de los `asegurar_contexto_*` de
`workflow_rfq`/`workflow_purchase_order`, que crean instancias, actualizan
`nodo_actual_id` e insertan eventos: si preguntar "¿en qué etapa estoy?" mutara
el proceso, la pregunta dejaría de ser gratis y el dato dejaría de ser confiable.

Dos orígenes posibles, y el contexto SIEMPRE declara cuál usó:

- `grafo`     — hay una instancia `unified`: etapa y etiquetas salen del workflow
                real de la empresa.
- `derivado`  — modo legacy (el default hoy, ver `workflow_rollout`): la etapa se
                infiere del estado observable. Es una inferencia útil, no el
                proceso. Sin ese marcador, el día que se active `unified` la
                etapa podría cambiar de nombre sin que nadie sepa por qué.

El núcleo es puro: `derivar_etapa`, `derivar_bloqueos` y `acciones_de` trabajan
sobre `Senales` y no tocan la base. La IO junta las señales y arma la respuesta.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

# Orden real del proceso de compra. Se usa para separar completadas de
# pendientes; las etiquetas de acá son genéricas a propósito y sólo aplican al
# origen `derivado` — en `grafo` mandan las del canvas de la empresa.
ETAPAS: tuple[tuple[str, str], ...] = (
    ("busqueda", "Buscando alternativas"),
    ("rfq_preparada", "Solicitudes de cotización preparadas"),
    ("esperando_cotizaciones", "Esperando respuesta de proveedores"),
    ("comparacion", "Comparando ofertas"),
    ("seleccion_lista", "Selección lista para autorizar"),
    ("esperando_aprobacion", "Esperando aprobación"),
    ("emision_oc", "Emisión de orden de compra"),
    ("seguimiento", "Seguimiento de la orden"),
)

_ORDEN = {clave: posicion for posicion, (clave, _) in enumerate(ETAPAS)}
_ETIQUETAS = dict(ETAPAS)

# Acciones sugeridas por etapa. Son NOMBRES DE TOOLS MCP, no prosa: el valor de
# esto es que el cliente pueda ejecutar el siguiente paso sin traducir nada.
_ACCIONES: dict[str, tuple[str, ...]] = {
    "busqueda": ("start_web_quote", "get_list_coverage", "suggest_suppliers"),
    "rfq_preparada": ("get_rfq_preview", "update_rfq_draft", "send_rfq"),
    "esperando_cotizaciones": ("get_rfq_status", "sync_supplier_replies", "search_alternatives"),
    "comparacion": ("compare_list", "explain_quote_recommendation", "select_final_quote"),
    "seleccion_lista": ("compare_list", "request_approval", "clear_final_quote"),
    "esperando_aprobacion": ("get_approval_status", "get_approval_route", "clear_final_quote"),
    "emision_oc": ("prepare_purchase_order", "create_purchase_order", "send_purchase_order"),
    "seguimiento": ("get_purchase_order_tracking", "list_supplier_replies"),
}


@dataclass(frozen=True)
class Senales:
    """Hechos observables de una compra. Todo lo que el núcleo necesita saber."""
    items_total: int = 0
    items_con_ofertas: int = 0
    rfq_preparadas: int = 0
    rfq_enviadas: int = 0
    respuestas_recibidas: int = 0
    conversaciones_en_conflicto: int = 0   # más de un precio: hay que elegir
    conversaciones_ambiguas: int = 0       # no se pudo interpretar el correo
    definitivos: int = 0
    definitivos_sin_precio: int = 0
    definitivos_sin_email: int = 0
    aprobacion_estado: Optional[str] = None
    requiere_aprobacion: bool = False
    ocs_creadas: int = 0
    ocs_enviadas: int = 0
    tiene_direccion_despacho: bool = False
    proveedores_sin_homologar: int = 0


# ─── Núcleo puro ─────────────────────────────────────────────────────────────

def derivar_etapa(s: Senales) -> str:
    """Etapa inferida del estado observable, de la más avanzada hacia atrás.

    El orden importa: una compra con OC enviada sigue teniendo definitivos y
    respuestas, así que evaluar de atrás para adelante la dejaría en `comparacion`.
    """
    if s.ocs_enviadas:
        return "seguimiento"
    if s.ocs_creadas:
        return "emision_oc"
    if s.aprobacion_estado == "aprobado":
        return "emision_oc"
    if s.aprobacion_estado in ("pendiente", "aprobado_con_observaciones", "rechazado", "expirado"):
        return "esperando_aprobacion"
    if s.items_total and s.definitivos >= s.items_total:
        return "seleccion_lista"
    if s.respuestas_recibidas:
        return "comparacion"
    if s.rfq_enviadas:
        return "esperando_cotizaciones"
    if s.rfq_preparadas:
        return "rfq_preparada"
    return "busqueda"


def derivar_bloqueos(s: Senales, etapa: str) -> list[dict[str, str]]:
    """Qué impide avanzar, con la acción concreta para resolverlo.

    Cada bloqueo nombra una tool: un bloqueo que no dice cómo salir obliga al
    cliente a adivinar, que es como se pierde un turno entero.
    """
    bloqueos: list[dict[str, str]] = []

    if s.conversaciones_en_conflicto:
        bloqueos.append({
            "codigo": "precios_en_conflicto",
            "mensaje": (
                f"{s.conversaciones_en_conflicto} conversación(es) con más de un precio para "
                "el mismo ítem. Ninguno se aplicó solo: hay que elegir cuál corresponde."
            ),
            "accion": "get_quote_lines",
        })

    if s.conversaciones_ambiguas:
        bloqueos.append({
            "codigo": "respuesta_no_interpretada",
            "mensaje": (
                f"{s.conversaciones_ambiguas} respuesta(s) de proveedor que la extracción no "
                "pudo interpretar. Los datos están en el correo pero no en la ficha; "
                "reprocesá el mensaje o cargalos a mano."
            ),
            "accion": "get_supplier_reply",
        })

    if s.definitivos_sin_precio:
        bloqueos.append({
            "codigo": "oferta_sin_precio",
            "mensaje": f"{s.definitivos_sin_precio} oferta(s) definitiva(s) sin precio persistido.",
            "accion": "select_final_quote",
        })

    if etapa == "esperando_aprobacion":
        bloqueos.append({
            "codigo": "aprobacion_pendiente",
            "mensaje": _MENSAJE_APROBACION.get(
                s.aprobacion_estado or "no_solicitada",
                "La compra requiere una aprobación limpia antes de emitir la OC.",
            ),
            "accion": "get_approval_status",
        })

    if etapa == "emision_oc":
        if s.definitivos_sin_email:
            bloqueos.append({
                "codigo": "proveedor_sin_email",
                "mensaje": f"{s.definitivos_sin_email} proveedor(es) definitivo(s) sin correo: la OC no se puede enviar.",
                "accion": "update_supplier",
            })
        if not s.tiene_direccion_despacho:
            bloqueos.append({
                "codigo": "sin_direccion_despacho",
                "mensaje": (
                    "La organización no tiene dirección de despacho configurada. La OC saldrá "
                    "sin destino y el proveedor va a preguntarlo. No se infiere de la dirección "
                    "administrativa."
                ),
                "accion": "configurar_despacho_en_settings",
            })

    if s.proveedores_sin_homologar:
        bloqueos.append({
            "codigo": "proveedor_no_homologado",
            "mensaje": f"{s.proveedores_sin_homologar} proveedor(es) con homologación pendiente.",
            "accion": "get_supplier",
        })

    return bloqueos


_MENSAJE_APROBACION = {
    "no_solicitada": "Nadie solicitó la aprobación todavía.",
    "pendiente": "La aprobación está pendiente de decisión del responsable.",
    "aprobado_con_observaciones": "Aprobada con observaciones: hay que resolverlas y pedir una aprobación limpia.",
    "rechazado": "La aprobación fue rechazada.",
    "expirado": "La aprobación expiró sin decisión.",
}


def acciones_de(etapa: str) -> list[str]:
    return list(_ACCIONES.get(etapa, ()))


def separar_etapas(etapa_actual: str) -> tuple[list[str], list[str]]:
    """Completadas y pendientes, según la posición de la etapa actual.

    Sólo aplica al origen `derivado`: asume el proceso lineal de arriba. En
    `grafo` el recorrido real puede tener ciclos ("rechazado → volver a cotizar")
    y las completadas salen de las ejecuciones de nodo, no de este orden.
    """
    posicion = _ORDEN.get(etapa_actual, 0)
    completadas = [clave for clave, _ in ETAPAS if _ORDEN[clave] < posicion]
    pendientes = [clave for clave, _ in ETAPAS if _ORDEN[clave] > posicion]
    return completadas, pendientes


def construir_contexto(
    list_id: str,
    senales: Senales,
    *,
    origen: str = "derivado",
    etapa: Optional[str] = None,
    etiqueta: Optional[str] = None,
    completadas: Optional[list[str]] = None,
    pendientes: Optional[list[str]] = None,
    transiciones: Optional[list[dict]] = None,
    aprobaciones: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Arma la respuesta. Puro: no consulta nada.

    `etapa`/`etiqueta`/`completadas` se pasan cuando el origen es `grafo`; si no,
    se derivan de las señales.
    """
    etapa_actual = etapa or derivar_etapa(senales)
    if completadas is None or pendientes is None:
        derivadas = separar_etapas(etapa_actual)
        completadas = completadas if completadas is not None else derivadas[0]
        pendientes = pendientes if pendientes is not None else derivadas[1]

    bloqueos = derivar_bloqueos(senales, etapa_actual)
    acciones = acciones_de(etapa_actual)
    return {
        "list_id": list_id,
        "origen": origen,
        "etapa_actual": etapa_actual,
        "etapa_label": etiqueta or _ETIQUETAS.get(etapa_actual, etapa_actual),
        "completadas": completadas,
        "pendientes": pendientes,
        "bloqueos": bloqueos,
        "transiciones": transiciones or [],
        "aprobaciones_requeridas": aprobaciones or [],
        "acciones_disponibles": acciones,
        "proximas_acciones": [
            {"tool": b["accion"], "por_que": b["mensaje"]} for b in bloqueos
        ] or ([{"tool": acciones[0], "por_que": f"Siguiente paso en '{etapa_actual}'."}] if acciones else []),
        "resumen": {
            "items": senales.items_total,
            "con_oferta_definitiva": senales.definitivos,
            "rfq_enviadas": senales.rfq_enviadas,
            "respuestas": senales.respuestas_recibidas,
        },
    }
