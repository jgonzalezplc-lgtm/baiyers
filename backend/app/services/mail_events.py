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
    # ─── Internos: autorización dentro de la organización ──────────────────
    "approval_requested": EventoDef(
        audiencia="internal",
        descripcion="Se pide autorización de una compra",
        variables_permitidas=["nombre_autorizador", "nombre_solicitante", "item", "monto", "organizacion_nombre", "link_autorizacion"],
        asunto_default="Autorización requerida — {{item}}",
        cuerpo_default=(
            "Hola {{nombre_autorizador}},\n\n"
            "{{nombre_solicitante}} solicitó autorización para \"{{item}}\" por {{monto}} "
            "en {{organizacion_nombre}}.\n\n"
            "Revisa y decide acá: {{link_autorizacion}}"
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
        variables_permitidas=["proveedor_nombre", "items", "empresa_nombre", "plazo_respuesta"],
        asunto_default="Solicitud de cotización — {{empresa_nombre}}",
        cuerpo_default=(
            "Estimado/a {{proveedor_nombre}},\n\n"
            "Necesitamos cotización para: {{items}}.\n\n"
            "Agradecemos tu respuesta antes de {{plazo_respuesta}}.\n\nSaludos, {{empresa_nombre}}"
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
        variables_permitidas=["proveedor_nombre", "campos_faltantes"],
        asunto_default="Nos falta un dato para tu cotización",
        cuerpo_default=(
            "Estimado/a {{proveedor_nombre}},\n\n"
            "Gracias por tu respuesta. Nos falta que nos confirmes: {{campos_faltantes}}."
        ),
    ),
    "rfq_received_thanks": EventoDef(
        audiencia="external",
        descripcion="Agradecimiento al recibir la cotización completa",
        variables_permitidas=["proveedor_nombre"],
        asunto_default="Recibimos tu cotización — gracias",
        cuerpo_default="Estimado/a {{proveedor_nombre}},\n\nGracias, recibimos tu cotización completa. Te avisaremos si resultas seleccionado.",
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
        variables_permitidas=["proveedor_nombre", "numero_oc", "empresa_nombre"],
        asunto_default="Orden de Compra {{numero_oc}} — {{empresa_nombre}}",
        cuerpo_default="Estimado/a {{proveedor_nombre}},\n\nAdjuntamos la Orden de Compra {{numero_oc}}. Por favor confirma la recepción.",
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
}
