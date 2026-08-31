"""Registro único de capacidades: qué hace cada tool y qué exige para correr.

Es el `registro único` de la §4.1 del `PRD_EMPLEADO_DIGITAL.md`: una sola tabla
que sirve al servidor MCP y al empleado digital, para no terminar manteniendo
dos catálogos con criterios distintos.

POR QUÉ EXISTE
--------------
Hoy la única señal de "un humano dijo que sí" es el argumento `confirmed: bool`
que llevan 28 de las 85 tools. Bajo MCP eso es tolerable: hay una persona
leyendo el cliente y el modelo transmite su respuesta. Bajo el empleado digital
—que corre solo sobre un buzón— no hay nadie en ese loop, y el modelo va a
mandar `confirmed=true` porque el propio schema se lo sugiere. Eso contradice la
regla dura 2 del PRD: la barrera vive en el código, no en el modelo.

Este módulo es el paso 1 y es DECLARATIVO: no bloquea nada todavía. Nadie lo
consulta para autorizar, así que el comportamiento de MCP es idéntico al de
antes de que existiera. Lo que aporta es:

  1. Que cada capacidad tenga su efecto escrito y versionado, en vez de que esté
     implícito en el nombre del scope y en si alguien se acordó de agregar
     `confirmed`.
  2. Que `exige_autorizacion_humana()` ya devuelva la respuesta correcta, para
     que el ejecutor de F1 la consulte en vez de inventar su propio criterio.
  3. Que `tests/test_tool_registry.py` haga fallar el CI cuando se agrega una
     tool y no se la clasifica. Igual que `tenant_guard`, donde el mecanismo real
     no es el guardia sino el test: una capacidad nueva nace clasificada.

LO QUE ESTE REGISTRO DEJA A LA VISTA
------------------------------------
Al escribirlo quedó claro que hoy `confirmed` se pide de forma despareja:
`create_supplier` y `set_supplier_categories` lo exigen, pero `create_list`,
`rename_list` y `add_list_items` no, y las tres son escrituras equivalentes.
`prepare_rfq` y `set_supplier_matrix` tampoco, aunque preparan un envío. No se
"arregló" nada de eso acá —cambiaría el comportamiento actual— pero queda
declarado, que era el punto: la política deja de ser folclore y pasa a ser dato.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Efecto(str, Enum):
    """Los cuatro escalones del eje 2 del PRD, de menor a mayor compromiso.

    El orden importa: `EFECTO_ORDEN` lo usa para comparar, y la regla es que el
    requisito nunca baja al subir de escalón.
    """

    LECTURA = "lectura"
    ESCRITURA = "escritura_interna"
    EXTERNO = "externo"
    DINERO = "dinero"


EFECTO_ORDEN = {
    Efecto.LECTURA: 0,
    Efecto.ESCRITURA: 1,
    Efecto.EXTERNO: 2,
    Efecto.DINERO: 3,
}


@dataclass(frozen=True)
class ToolSpec:
    """Qué es una capacidad y qué exige.

    `scope` se declara acá además de en el código porque el test compara los dos:
    si alguien cambia el scope de una tool y no toca el registro, el CI lo
    encuentra. Es la misma idea del test de `tenant_guard`.
    """

    efecto: Efecto
    scope: str
    # Regla dura 3: la tool trae adentro contenido que escribió un tercero
    # (correo de proveedor, PDF adjunto, página scrapeada). El ejecutor tiene
    # que tratar su salida como datos citados, jamás como instrucciones.
    ingiere_contenido_externo: bool = False
    # Rol del workflow (`workflow_engine.ROLES_BASE`) que debería respaldar la
    # acción cuando el ejecutor de F1 empiece a exigirlo. `None` = cualquier
    # miembro con el scope alcanza.
    rol_requerido: str | None = None
    nota: str | None = None


# ── El catálogo ──────────────────────────────────────────────────────────────
# Criterio de clasificación, para que el próximo que agregue una tool no tenga
# que adivinarlo:
#
#   lectura    — no persiste nada y no sale de la app.
#   escritura  — persiste en la base de la organización. Reversible por un
#                humano, no compromete plata ni expone a la empresa.
#   externo    — sale hacia afuera A NOMBRE DE LA EMPRESA (correo a un
#                proveedor). Es irreversible: un correo enviado no se
#                despacha. Ojo: buscar precios en la web NO es `externo`,
#                aunque haga requests salientes, porque nadie afuera se entera
#                de que la empresa está preguntando.
#   dinero     — compromete o mueve plata de la organización.
#
# Emitir una OC es `dinero` aunque no mueva un peso todavía: es el documento con
# el que la empresa se obliga a pagar. El PRD lo dice explícito al describir el
# nivel 3 de autonomía ("cubre *emitir la OC*, nunca *mover el dinero*"), o sea
# lo trata como el escalón donde ya hay compromiso económico.
TOOLS: dict[str, ToolSpec] = {
    # ── Lectura ──────────────────────────────────────────────────────────────
    "baiyer_status": ToolSpec(Efecto.LECTURA, "lists:read"),
    "get_list": ToolSpec(Efecto.LECTURA, "lists:read"),
    "list_lists": ToolSpec(Efecto.LECTURA, "lists:read"),
    "get_purchase_context": ToolSpec(Efecto.LECTURA, "lists:read"),
    "get_workflow": ToolSpec(Efecto.LECTURA, "lists:read"),
    "get_rollout_status": ToolSpec(Efecto.LECTURA, "lists:read"),
    "get_job": ToolSpec(Efecto.LECTURA, "jobs:read"),
    "list_jobs": ToolSpec(Efecto.LECTURA, "jobs:read"),
    "compare_item": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "compare_list": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "explain_quote_recommendation": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "get_item_quotes": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "get_list_coverage": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "get_quote_lines": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "get_web_quote": ToolSpec(Efecto.LECTURA, "quotes:read"),
    "get_supplier": ToolSpec(Efecto.LECTURA, "suppliers:read"),
    "get_supplier_history": ToolSpec(Efecto.LECTURA, "suppliers:read"),
    "search_suppliers": ToolSpec(Efecto.LECTURA, "suppliers:read"),
    "suggest_suppliers": ToolSpec(Efecto.LECTURA, "suppliers:read"),
    "get_supplier_matrix": ToolSpec(Efecto.LECTURA, "rfq:read"),
    "get_rfq_preview": ToolSpec(Efecto.LECTURA, "rfq:read"),
    "get_rfq_status": ToolSpec(Efecto.LECTURA, "rfq:read"),
    "get_purchase_order": ToolSpec(Efecto.LECTURA, "po:read"),
    "get_purchase_order_tracking": ToolSpec(Efecto.LECTURA, "po:read"),
    "list_purchase_orders": ToolSpec(Efecto.LECTURA, "po:read"),
    "prepare_purchase_order": ToolSpec(Efecto.LECTURA, "po:read", nota="Sólo arma el preview; crear la OC es create_purchase_order."),
    "get_invoice": ToolSpec(Efecto.LECTURA, "invoices:read"),
    "list_invoices": ToolSpec(Efecto.LECTURA, "invoices:read"),
    "reconcile_invoice_po": ToolSpec(Efecto.LECTURA, "invoices:read", nota="Compara y explica diferencias; no marca nada como pagado."),
    "get_approval_route": ToolSpec(Efecto.LECTURA, "approvals:read"),
    "get_approval_status": ToolSpec(Efecto.LECTURA, "approvals:read"),
    "list_workflow_events": ToolSpec(Efecto.LECTURA, "approvals:read"),
    "get_spend_metrics": ToolSpec(Efecto.LECTURA, "analytics:read"),
    "get_supplier_metrics": ToolSpec(Efecto.LECTURA, "analytics:read"),
    "describe_query_schema": ToolSpec(Efecto.LECTURA, "data:read"),
    "query_baiyer_data": ToolSpec(Efecto.LECTURA, "data:read", nota="Entidades/campos allowlisteados en semantic_query.py; no acepta SQL."),
    "generate_list_report": ToolSpec(
        Efecto.LECTURA, "reports:write",
        nota="El scope dice `write` pero la tool declara readOnlyHint y sólo compone un informe con datos ya persistidos. El scope quedó mal nombrado; renombrarlo rompería los tokens ya emitidos.",
    ),
    # Contenido de terceros: leen el buzón. Su salida es input hostil (regla dura 3).
    "get_supplier_reply": ToolSpec(Efecto.LECTURA, "mail:read", ingiere_contenido_externo=True),
    "list_supplier_replies": ToolSpec(Efecto.LECTURA, "mail:read", ingiere_contenido_externo=True),
    "research_supplier": ToolSpec(
        Efecto.LECTURA, "suppliers:read", ingiere_contenido_externo=True,
        nota="Scrapea el sitio del proveedor. No es `externo` porque nadie afuera se entera, pero lo que devuelve lo escribió un tercero.",
    ),

    # ── Escritura interna ────────────────────────────────────────────────────
    "create_list": ToolSpec(Efecto.ESCRITURA, "lists:write"),
    "rename_list": ToolSpec(Efecto.ESCRITURA, "lists:write"),
    "add_list_items": ToolSpec(Efecto.ESCRITURA, "lists:write"),
    "update_list_item": ToolSpec(Efecto.ESCRITURA, "lists:write"),
    "remove_list_item": ToolSpec(Efecto.ESCRITURA, "lists:write"),
    "commit_document_import": ToolSpec(Efecto.ESCRITURA, "lists:write", ingiere_contenido_externo=True),
    "commit_project_intake": ToolSpec(Efecto.ESCRITURA, "lists:write"),
    "start_project_intake": ToolSpec(Efecto.ESCRITURA, "projects:write"),
    "continue_project_intake": ToolSpec(Efecto.ESCRITURA, "projects:write"),
    "cancel_job": ToolSpec(Efecto.ESCRITURA, "jobs:write"),
    "preview_document_import": ToolSpec(Efecto.ESCRITURA, "documents:write", ingiere_contenido_externo=True, nota="Persiste un draft; el commit es aparte."),
    "preview_invoice_import": ToolSpec(Efecto.ESCRITURA, "invoices:write", ingiere_contenido_externo=True),
    "preview_supplier_import": ToolSpec(Efecto.ESCRITURA, "suppliers:write", ingiere_contenido_externo=True),
    "start_web_quote": ToolSpec(Efecto.ESCRITURA, "quotes:write", nota="Sale a buscar precios, pero no expone a la empresa: no es `externo`."),
    "quote_project": ToolSpec(Efecto.ESCRITURA, "quotes:write"),
    "quote_new_project": ToolSpec(Efecto.ESCRITURA, "quotes:write"),
    "search_alternatives": ToolSpec(Efecto.ESCRITURA, "quotes:write"),
    "select_quote_line": ToolSpec(Efecto.ESCRITURA, "quotes:write", rol_requerido="cotizador"),
    "discard_quote_line": ToolSpec(Efecto.ESCRITURA, "quotes:write", rol_requerido="cotizador"),
    "select_final_quote": ToolSpec(Efecto.ESCRITURA, "quotes:write", rol_requerido="cotizador"),
    "clear_final_quote": ToolSpec(Efecto.ESCRITURA, "quotes:write", rol_requerido="cotizador"),
    "apply_reply_proposal": ToolSpec(Efecto.ESCRITURA, "quotes:write", ingiere_contenido_externo=True, nota="Aplica al sistema un dato que escribió un proveedor."),
    "reject_reply_proposal": ToolSpec(Efecto.ESCRITURA, "quotes:write", ingiere_contenido_externo=True),
    "prepare_rfq": ToolSpec(Efecto.ESCRITURA, "rfq:write", nota="Arma el borrador; el que sale hacia afuera es send_rfq."),
    "update_rfq_draft": ToolSpec(Efecto.ESCRITURA, "rfq:write"),
    "set_supplier_matrix": ToolSpec(Efecto.ESCRITURA, "rfq:write"),
    "select_supplier_for_item": ToolSpec(Efecto.ESCRITURA, "rfq:write"),
    "create_supplier": ToolSpec(Efecto.ESCRITURA, "suppliers:write"),
    "update_supplier": ToolSpec(Efecto.ESCRITURA, "suppliers:write"),
    "commit_supplier_import": ToolSpec(Efecto.ESCRITURA, "suppliers:write"),
    "set_supplier_categories": ToolSpec(Efecto.ESCRITURA, "suppliers:write"),
    "block_supplier": ToolSpec(Efecto.ESCRITURA, "suppliers:block", rol_requerido="homologador"),
    "unblock_supplier": ToolSpec(Efecto.ESCRITURA, "suppliers:block", rol_requerido="homologador"),
    "commit_invoice_import": ToolSpec(Efecto.ESCRITURA, "invoices:write", ingiere_contenido_externo=True),
    "match_invoice_to_po": ToolSpec(Efecto.ESCRITURA, "invoices:write", rol_requerido="receptor_facturas"),
    # Traen correo de terceros al sistema y lo interpretan.
    "sync_supplier_replies": ToolSpec(Efecto.ESCRITURA, "mail:sync", ingiere_contenido_externo=True),
    "scan_invoice_inbox": ToolSpec(Efecto.ESCRITURA, "mail:sync", ingiere_contenido_externo=True),

    # ── Externo: sale a nombre de la empresa, no se puede deshacer ───────────
    "send_rfq": ToolSpec(Efecto.EXTERNO, "rfq:send", rol_requerido="cotizador"),
    "request_approval": ToolSpec(
        Efecto.EXTERNO, "approvals:request", rol_requerido="cotizador",
        nota="Manda correo a una persona real pidiéndole que autorice. Sale del sistema aunque el destinatario sea interno.",
    ),

    # ── Dinero: siempre autorización humana, sin monto mínimo (regla dura 1) ──
    "create_purchase_order": ToolSpec(
        Efecto.DINERO, "po:write", rol_requerido="comprador",
        nota="Emitir la OC es el acto con el que la empresa se obliga a pagar.",
    ),
    "update_purchase_order": ToolSpec(Efecto.DINERO, "po:write", rol_requerido="comprador", nota="Puede cambiar montos de una OC ya emitida."),
    "send_purchase_order": ToolSpec(Efecto.DINERO, "po:send", rol_requerido="comprador", nota="Externo Y dinero: le comunica al proveedor la obligación."),
    "mark_invoice_paid": ToolSpec(Efecto.DINERO, "invoices:pay", rol_requerido="receptor_facturas"),
    "approve_request": ToolSpec(
        Efecto.DINERO, "approvals:decide", rol_requerido="autorizador",
        nota="La autorización ES la decisión de comprometer plata. Ya tiene barrera real en comparison_approval_service._authorized_request().",
    ),
    "reject_request": ToolSpec(Efecto.DINERO, "approvals:decide", rol_requerido="autorizador"),
}


def spec(nombre: str) -> ToolSpec:
    """Spec de una tool. Lanza si no está declarada: una capacidad sin
    clasificar no puede ejecutarse a ciegas."""
    try:
        return TOOLS[nombre]
    except KeyError:
        raise KeyError(
            f"La tool '{nombre}' no está declarada en tool_registry.TOOLS. "
            "Declarala con su efecto antes de exponerla."
        ) from None


def exige_autorizacion_humana(nombre: str) -> bool:
    """¿Esta capacidad necesita el sí de una persona antes de ejecutarse?

    Hoy NADIE llama a esto: es la respuesta lista para que el ejecutor de F1 la
    consulte, en vez de que cada llamador invente su criterio. `dinero` siempre
    (regla dura 1, sin monto mínimo y sin modo confianza) y `externo` también,
    porque un correo enviado a un proveedor no se puede deshacer.
    """
    return EFECTO_ORDEN[spec(nombre).efecto] >= EFECTO_ORDEN[Efecto.EXTERNO]


def nombres_por_efecto(efecto: Efecto) -> list[str]:
    return sorted(n for n, s in TOOLS.items() if s.efecto == efecto)
