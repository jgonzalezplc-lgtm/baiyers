"""Batería de correos por defecto para un workflow recién creado.

Los 24 eventos de `mail_events.py` son la batería que cada rol usa en su parte
del proceso, interna y externamente. Este módulo traduce eso a las reglas
concretas por tarjeta, para que un ciclo creado desde el chat llegue al canvas
YA funcionando en vez de con tarjetas mudas que hay que cablear a mano.

REGLA DE ORO DE ESTE MÓDULO: sólo se generan reglas para eventos que algún
flujo REALMENTE consume. No hay ejecutor genérico de reglas — cada flujo
filtra por `evento_plantilla` concreto:

  approval_reminder                     -> workflow_scheduler.py
  rfq_requested / rfq_followup          -> workflow_rfq.py
  supplier_intake_followup              -> workflow_homologation.py
  purchase_order_ack_reminder,
  dispatch_status_request,
  purchase_order_internal_copy,
  purchase_order_acknowledged_internal,
  dispatch_notified_internal            -> workflow_purchase_order.py

Crear una regla para un evento fuera de esa lista (`internal_task_assigned`,
`approval_requested`, `rfq_received_thanks`, ...) mostraría en la UI un correo
configurado que nunca se enviaría: o se manda imperativamente sin regla, o no
está cableado todavía. Al conectar un flujo nuevo, agregar acá su evento.

Los loops usan valores conservadores y `politica_agotamiento="pausar"`: al
agotarse, la instancia se detiene para que la vea un humano. Nunca autoaprueban
ni descartan a un proveedor por su cuenta.
"""
from typing import Optional

# Cada cuántos días insiste un loop y cuántas veces. Holgado a propósito: un
# proveedor real puede tardar días en responder y el costo de insistir de más
# es reputacional, no técnico.
DIAS_ENTRE_INSISTENCIAS = 3
MAX_INSISTENCIAS = 3


def _loop_externo(evento: str, evento_termino: str) -> dict:
    """Insistencia a un proveedor, acotada por proveedor (no por tarjeta): que
    uno no responda no puede frenar los recordatorios de los demás."""
    return {
        "evento_plantilla": evento,
        "audiencia": "external",
        "destinatario_tipo": "proveedor",
        "disparador_tipo": "despues_demora",
        "demora_inicial_dias": DIAS_ENTRE_INSISTENCIAS,
        "repetir_cada_dias": DIAS_ENTRE_INSISTENCIAS,
        "max_intentos": MAX_INSISTENCIAS,
        "evento_termino": evento_termino,
        "alcance_termino": "proveedor",
        "politica_agotamiento": "pausar",
    }


def _aviso_interno(evento: str, rol_clave: str, disparador_evento: Optional[str] = None) -> dict:
    """Aviso a una persona del equipo. Sin repetición: es una notificación
    puntual, no una insistencia."""
    regla = {
        "evento_plantilla": evento,
        "audiencia": "internal",
        "destinatario_tipo": "responsable_rol",
        "rol_clave": rol_clave,
        "disparador_tipo": "al_entrar",
    }
    if disparador_evento:
        regla["disparador_tipo"] = "al_ocurrir_evento"
        regla["disparador_evento"] = disparador_evento
    return regla


def reglas_para_nodo(nodo: dict, roles_disponibles: Optional[set[str]] = None) -> list[dict]:
    """Reglas por defecto de una tarjeta según su tipo. Pura.

    INVARIANTE: el `rol_clave` de una regla interna debe ser un rol de ESTA
    tarjeta. Si no, no hay a quién asignarle el correo (el canvas rechaza
    asignar un rol que no participa) y `validar_automatizacion` lo marca como
    `responsable_sin_email`, bloqueando la activación del ciclo.
    """
    tipo = nodo.get("tipo")
    roles_nodo = nodo.get("roles") or []

    if tipo == "autorizacion":
        # El correo inicial (`approval_requested`) lo manda listas.py de forma
        # imperativa; acá sólo corresponde el recordatorio, que es lo que el
        # scheduler programa a partir de una regla.
        return [{
            "evento_plantilla": "approval_reminder",
            "audiencia": "internal",
            "destinatario_tipo": "responsable_rol",
            "rol_clave": "autorizador",
            "disparador_tipo": "despues_demora",
            "demora_inicial_dias": DIAS_ENTRE_INSISTENCIAS,
            "repetir_cada_dias": DIAS_ENTRE_INSISTENCIAS,
            "max_intentos": MAX_INSISTENCIAS,
            # La cancelación real es imperativa (cancelar_recordatorios_
            # autorizacion) apenas hay decisión; esto declara el hecho de
            # negocio que cierra el loop.
            "evento_termino": "aprobado",
            "alcance_termino": "destinatario",
            "politica_agotamiento": "pausar",
        }]

    if tipo == "tarea_humana":
        # La tarjeta de cotización es la que dispara la RFQ a proveedores.
        return [
            {
                "evento_plantilla": "rfq_requested",
                "audiencia": "external",
                "destinatario_tipo": "proveedor",
                "disparador_tipo": "al_entrar",
                "rol_clave": "cotizador",
            },
            {**_loop_externo("rfq_followup", "rfq_respuesta_recibida"), "rol_clave": "cotizador"},
        ]

    if tipo == "homologacion":
        # `supplier_intake_started` se envía imperativamente al abrir el caso;
        # la regla sólo gobierna la insistencia por antecedentes faltantes.
        return [{
            **_loop_externo("supplier_intake_followup", "documentacion_completa"),
            "rol_clave": "homologador",
        }]

    if tipo == "emision_oc":
        # Los avisos internos van al rol de ESTA tarjeta. Sería más natural
        # avisarle del despacho a quien recibe la mercadería
        # (`receptor_facturas`), pero ese rol no participa de la tarjeta de OC:
        # asignarlo acá deja el correo sin destinatario. Reasignarlo es una
        # decisión explícita del usuario en el canvas.
        rol = roles_nodo[0] if roles_nodo else "comprador"
        return [
            _aviso_interno("purchase_order_internal_copy", rol),
            _loop_externo("purchase_order_ack_reminder", "oc_recepcion_confirmada"),
            _aviso_interno("purchase_order_acknowledged_internal", rol,
                           disparador_evento="oc_recepcion_confirmada"),
            _loop_externo("dispatch_status_request", "despacho_informado"),
            _aviso_interno("dispatch_notified_internal", rol,
                           disparador_evento="despacho_informado"),
        ]

    # revision y espera_documento no tienen ningún evento cableado todavía:
    # se dejan sin reglas en vez de inventar correos que no saldrían.
    return []


def reglas_por_defecto(nodos: list[dict]) -> list[dict]:
    """Reglas por defecto de todo el grafo, listas para insertar. Cada una
    trae `nodo_id`. Pura: no toca Supabase."""
    roles = {r for n in nodos for r in (n.get("roles") or [])}
    salida: list[dict] = []
    for nodo in nodos:
        nodo_id = nodo.get("id")
        if not nodo_id:
            continue
        for regla in reglas_para_nodo(nodo, roles):
            salida.append({"nodo_id": nodo_id, **regla})
    return salida
