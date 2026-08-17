"""
Catálogo de eventos de correo — Fase 4 del proyecto de mailing organizacional.

El contenido default de cada evento vive ACÁ, en Python, no en la base de
datos: así una organización sin ningún override sigue recibiendo el correo
de siempre, sin necesidad de una migración de datos ni de crear filas
"default" — `mail_template_definitions` solo guarda overrides reales.

Cada plantilla usa placeholders `{{variable}}` (reemplazo por regex, sin
Jinja2 ni `eval` — ver `mail_template_service.py`). `variables_permitidas`
es el allowlist: una plantilla guardada nunca puede referenciar una
variable fuera de esta lista para ese evento.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class EventoDef:
    audiencia: str  # "internal" | "external"
    descripcion: str
    variables_permitidas: list[str]
    asunto_default: str
    cuerpo_default: str


EVENTOS: dict[str, EventoDef] = {
    "internal_task_assigned": EventoDef(
        audiencia="internal",
        descripcion="Se asignó una tarea interna del ciclo de compras",
        variables_permitidas=["nombre_responsable", "tarea", "lista_nombre", "link_baiyer"],
        asunto_default="Nueva tarea — {{tarea}}",
        cuerpo_default=(
            "Hola {{nombre_responsable}},\n\nTienes asignada la tarea \"{{tarea}}\" "
            "para {{lista_nombre}}.\n\nRevisa el proceso en Baiyer: {{link_baiyer}}"
        ),
    ),
    "internal_task_reminder": EventoDef(
        audiencia="internal",
        descripcion="Recordatorio de una tarea interna pendiente",
        variables_permitidas=["nombre_responsable", "tarea", "lista_nombre", "dias_pendiente", "link_baiyer"],
        asunto_default="Recordatorio: tarea pendiente — {{tarea}}",
        cuerpo_default=(
            "Hola {{nombre_responsable}},\n\nLa tarea \"{{tarea}}\" de {{lista_nombre}} "
            "sigue pendiente hace {{dias_pendiente}} días.\n\n{{link_baiyer}}"
        ),
    ),
    # ─── Internos: autorización dentro de la organización ──────────────────
    "approval_requested": EventoDef(
        audiencia="internal",
        descripcion="Se pide autorización de una compra",
        # Ampliado en Fase 6 al migrar los dos sitios reales (listas.py): el
        # correo real incluye el detalle ítem por ítem y la fecha de
        # expiración del enlace, que la versión inicial de Fase 4 no
        # contemplaba. Cambiar esto es seguro porque nadie lo personalizó
        # todavía en /settings/comunicaciones (recién se deployó).
        variables_permitidas=[
            "nombre_autorizador", "nombre_solicitante", "organizacion_nombre",
            "lista_nombre", "monto", "item_lines", "nodo_nombre",
            "link_autorizacion", "expira_at",
        ],
        asunto_default="Solicitud de aprobación — {{lista_nombre}}",
        cuerpo_default=(
            "Hola {{nombre_autorizador}},\n\n"
            "{{nombre_solicitante}} de {{organizacion_nombre}} solicita tu aprobación como "
            "{{nodo_nombre}} para la siguiente lista de compra:\n\n"
            "Lista: {{lista_nombre}}\nTotal: {{monto}}\n\n{{item_lines}}\n\n"
            "Revisa el detalle y aprueba o rechaza (puedes agregar comentarios) desde este enlace:\n"
            "{{link_autorizacion}}\n\n"
            "Este enlace expira el {{expira_at}}.\n\nBaiyer, Procurement Inteligente"
        ),
    ),
    "approval_reminder": EventoDef(
        audiencia="internal",
        descripcion="Recordatorio de una autorización pendiente",
        variables_permitidas=["nombre_autorizador", "item", "monto", "dias_pendiente", "link_autorizacion"],
        asunto_default="Recordatorio: autorización pendiente — {{item}}",
        cuerpo_default=(
            "Hola {{nombre_autorizador}},\n\n"
            "\"{{item}}\" ({{monto}}) sigue esperando tu autorización hace {{dias_pendiente}} días.\n\n"
            "Revisa y decide acá: {{link_autorizacion}}"
        ),
    ),
    "approval_approved": EventoDef(
        audiencia="internal",
        descripcion="Aviso de que una compra fue aprobada",
        variables_permitidas=["nombre_solicitante", "item", "aprobado_por"],
        asunto_default="Aprobado — {{item}}",
        cuerpo_default="Hola {{nombre_solicitante}},\n\n{{aprobado_por}} aprobó \"{{item}}\". Puedes continuar con la compra.",
    ),
    "approval_rejected": EventoDef(
        audiencia="internal",
        descripcion="Aviso de que una compra fue rechazada",
        variables_permitidas=["nombre_solicitante", "item", "rechazado_por", "motivo"],
        asunto_default="Rechazado — {{item}}",
        cuerpo_default="Hola {{nombre_solicitante}},\n\n{{rechazado_por}} rechazó \"{{item}}\".\n\nMotivo: {{motivo}}",
    ),
    "approval_returned": EventoDef(
        audiencia="internal",
        descripcion="La compra vuelve para corrección antes de decidir",
        variables_permitidas=["nombre_solicitante", "item", "devuelto_por", "motivo"],
        asunto_default="Necesita corrección — {{item}}",
        cuerpo_default="Hola {{nombre_solicitante}},\n\n{{devuelto_por}} devolvió \"{{item}}\" para corregir.\n\nDetalle: {{motivo}}",
    ),
    "approval_escalated": EventoDef(
        audiencia="internal",
        descripcion="La autorización se escaló a otra persona",
        variables_permitidas=["nombre_autorizador", "item", "monto", "link_autorizacion"],
        asunto_default="Escalado a ti — {{item}}",
        cuerpo_default=(
            "Hola {{nombre_autorizador}},\n\n"
            "\"{{item}}\" ({{monto}}) se escaló a ti para autorización.\n\n"
            "Revisa y decide acá: {{link_autorizacion}}"
        ),
    ),
    "workflow_assignment_invitation": EventoDef(
        audiencia="internal",
        descripcion="Invitación a un rol dentro del ciclo de compras",
        variables_permitidas=["nombre_invitado", "organizacion_nombre", "rol", "invitado_por_nombre", "link_invitacion"],
        asunto_default="Te invitaron a {{organizacion_nombre}} en Baiyer",
        cuerpo_default=(
            "Hola {{nombre_invitado}},\n\n"
            "{{invitado_por_nombre}} te invitó a {{organizacion_nombre}} como \"{{rol}}\" en el ciclo de compras.\n\n"
            "Acepta la invitación acá: {{link_invitacion}}"
        ),
    ),
    # ─── Externos: comunicación con proveedores ─────────────────────────────
    "rfq_requested": EventoDef(
        audiencia="external",
        descripcion="Solicitud de cotización a un proveedor",
        # "recurrencia_nombre" se agregó en Fase 6 al migrar
        # recurrencia_service.py — el asunto real usa el nombre de la
        # recurrencia, no el de la empresa. "plazo_respuesta" queda
        # disponible para quien lo quiera usar en su propia plantilla, pero
        # el default no lo necesita.
        variables_permitidas=["proveedor_nombre", "items", "empresa_nombre", "plazo_respuesta", "recurrencia_nombre"],
        asunto_default="Solicitud de cotización — {{recurrencia_nombre}}",
        cuerpo_default=(
            "Estimado/a {{proveedor_nombre}},\n\n"
            "Necesitamos cotización para los siguientes ítems:\n\n{{items}}\n\n"
            "Por favor envíanos precios, disponibilidad y plazo de entrega.\n\n"
            "Saludos,\n{{empresa_nombre}}"
        ),
    ),
    "rfq_followup": EventoDef(
        audiencia="external",
        descripcion="Seguimiento de una cotización sin respuesta",
        variables_permitidas=["proveedor_nombre", "items", "dias_transcurridos"],
        asunto_default="Seguimiento de cotización — {{items}}",
        cuerpo_default=(
            "Estimado/a {{proveedor_nombre}},\n\n"
            "Te escribimos hace {{dias_transcurridos}} días por: {{items}}. "
            "¿Podrías confirmarnos si tienes la cotización lista?"
        ),
    ),
    "rfq_missing_information": EventoDef(
        audiencia="external",
        descripcion="Faltan datos en la respuesta del proveedor",
        # Wording exacto de `gmail_conversation_agent.redactar_pedir_faltantes`
        # — ese correo lo dispara el agente automáticamente sin revisión
        # humana, así que migrarlo a Fase 6 debía preservar el texto
        # exacto, no solo el sentido.
        variables_permitidas=["proveedor_nombre", "campos_faltantes"],
        asunto_default="Nos falta un dato para tu cotización",
        cuerpo_default=(
            "Estimados {{proveedor_nombre}},\n\n"
            "Gracias por su respuesta, ya registramos lo que nos enviaron. "
            "Para completar la evaluación nos falta {{campos_faltantes}}.\n\n"
            "¿Podrían confirmarnos ese dato? Quedamos atentos.\n\nSaludos cordiales."
        ),
    ),
    "rfq_received_thanks": EventoDef(
        audiencia="external",
        descripcion="Agradecimiento al recibir la cotización completa",
        # Wording exacto de `gmail_conversation_agent.redactar_agradecimiento`
        # — mismo motivo que rfq_missing_information: es un correo
        # automático sin revisión humana.
        variables_permitidas=["proveedor_nombre"],
        asunto_default="Recibimos tu cotización — gracias",
        cuerpo_default=(
            "Estimados {{proveedor_nombre}},\n\n"
            "Muchas gracias por la información enviada, ya quedó registrada de nuestro lado. "
            "Quedamos en contacto para los siguientes pasos.\n\nSaludos cordiales."
        ),
    ),
    "supplier_intake_started": EventoDef(
        audiencia="external",
        descripcion="Solicitud inicial de antecedentes para homologación",
        variables_permitidas=["proveedor_nombre", "empresa_nombre", "requisitos"],
        asunto_default="Antecedentes para homologación como proveedor — {{empresa_nombre}}",
        cuerpo_default=(
            "Estimados {{proveedor_nombre}},\n\nPara continuar con el proceso de compra necesitamos "
            "homologarlos como proveedor. Por favor respondan este correo adjuntando o indicando:\n\n"
            "{{requisitos}}\n\nNo envíen claves, credenciales bancarias ni documentos personales no "
            "solicitados.\n\nSaludos,\n{{empresa_nombre}}"
        ),
    ),
    "supplier_intake_followup": EventoDef(
        audiencia="external",
        descripcion="Seguimiento de antecedentes de homologación pendientes",
        variables_permitidas=["proveedor_nombre", "requisitos_pendientes", "dias_transcurridos"],
        asunto_default="Seguimiento de homologación — antecedentes pendientes",
        cuerpo_default=(
            "Estimados {{proveedor_nombre}},\n\nHace {{dias_transcurridos}} días solicitamos antecedentes "
            "para su homologación. Aún necesitamos:\n\n{{requisitos_pendientes}}\n\n"
            "Pueden responder en este mismo hilo.\n\nSaludos cordiales."
        ),
    ),
    "supplier_intake_missing_information": EventoDef(
        audiencia="external",
        descripcion="Solicitud de antecedentes faltantes o corregidos",
        variables_permitidas=["proveedor_nombre", "requisitos_pendientes", "comentario"],
        asunto_default="Información pendiente para completar la homologación",
        cuerpo_default=(
            "Estimados {{proveedor_nombre}},\n\nGracias por los antecedentes enviados. Para completar "
            "la homologación necesitamos:\n\n{{requisitos_pendientes}}\n\n{{comentario}}\n\n"
            "Quedamos atentos.\n\nSaludos cordiales."
        ),
    ),
    "supplier_awarded": EventoDef(
        audiencia="external",
        descripcion="El proveedor fue seleccionado",
        variables_permitidas=["proveedor_nombre", "item", "numero_oc"],
        asunto_default="¡Fuiste seleccionado! — {{item}}",
        cuerpo_default="Estimado/a {{proveedor_nombre}},\n\nFuiste seleccionado para \"{{item}}\". En breve recibirás la Orden de Compra {{numero_oc}}.",
    ),
    "supplier_not_awarded": EventoDef(
        audiencia="external",
        descripcion="El proveedor no fue seleccionado",
        variables_permitidas=["proveedor_nombre", "item"],
        asunto_default="Resultado de tu cotización — {{item}}",
        cuerpo_default="Estimado/a {{proveedor_nombre}},\n\nGracias por cotizar \"{{item}}\". Esta vez elegimos otra propuesta, pero seguimos en contacto.",
    ),
    "purchase_order_sent": EventoDef(
        audiencia="external",
        descripcion="Envío de la Orden de Compra al proveedor",
        # Ampliado en Fase 6 al migrar oc.py: el correo real incluye monto,
        # moneda y el link de confirmación alternativo — sin migración
        # necesaria, nadie lo personalizó todavía.
        variables_permitidas=["proveedor_nombre", "numero_oc", "empresa_nombre", "monto", "moneda", "link_confirmacion"],
        asunto_default="Orden de Compra {{numero_oc}} — {{empresa_nombre}}",
        cuerpo_default=(
            "Estimado/a {{proveedor_nombre}},\n\n"
            "Adjuntamos la Orden de Compra {{numero_oc}} por {{monto}} {{moneda}}.\n\n"
            "Por favor confírmanos por este mismo correo la recepción de la orden, y avísanos cuando "
            "despaches el pedido. Si prefieres, también puedes confirmar la recepción acá:\n{{link_confirmacion}}\n\n"
            "Saludos,\n{{empresa_nombre}}"
        ),
    ),
    "purchase_order_internal_copy": EventoDef(
        audiencia="internal",
        descripcion="Aviso interno de que una OC fue emitida",
        variables_permitidas=["nombre_responsable", "numero_oc", "proveedor_nombre", "monto", "moneda"],
        asunto_default="OC emitida — {{numero_oc}}",
        cuerpo_default=(
            "Hola {{nombre_responsable}},\n\nLa Orden de Compra {{numero_oc}} fue enviada a "
            "{{proveedor_nombre}} por {{monto}} {{moneda}}."
        ),
    ),
    "purchase_order_acknowledged_internal": EventoDef(
        audiencia="internal",
        descripcion="Aviso interno de recepción confirmada de una OC",
        variables_permitidas=["nombre_responsable", "numero_oc", "proveedor_nombre"],
        asunto_default="Recepción confirmada — {{numero_oc}}",
        cuerpo_default=(
            "Hola {{nombre_responsable}},\n\n{{proveedor_nombre}} confirmó la recepción de la "
            "Orden de Compra {{numero_oc}}."
        ),
    ),
    "purchase_order_ack_reminder": EventoDef(
        audiencia="external",
        descripcion="Recordatorio de confirmar recepción de la OC",
        variables_permitidas=["proveedor_nombre", "numero_oc", "dias_transcurridos"],
        asunto_default="Pendiente confirmar recepción — {{numero_oc}}",
        cuerpo_default="Estimado/a {{proveedor_nombre}},\n\nHace {{dias_transcurridos}} días enviamos la OC {{numero_oc}} y aún no confirmas su recepción.",
    ),
    "dispatch_status_request": EventoDef(
        audiencia="external",
        descripcion="Consulta de estado de despacho de una OC",
        variables_permitidas=["proveedor_nombre", "numero_oc"],
        asunto_default="¿Cómo va el despacho de {{numero_oc}}?",
        cuerpo_default="Estimado/a {{proveedor_nombre}},\n\n¿Nos puedes contar el estado del despacho de la Orden de Compra {{numero_oc}}?",
    ),
    "dispatch_notified_internal": EventoDef(
        audiencia="internal",
        descripcion="Aviso interno de despacho informado por el proveedor",
        variables_permitidas=["nombre_responsable", "numero_oc", "proveedor_nombre", "detalle_despacho"],
        asunto_default="Despacho informado — {{numero_oc}}",
        cuerpo_default=(
            "Hola {{nombre_responsable}},\n\n{{proveedor_nombre}} informó el despacho de la OC "
            "{{numero_oc}}.\n\nDetalle: {{detalle_despacho}}"
        ),
    ),
}
