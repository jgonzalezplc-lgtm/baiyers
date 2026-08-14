# Baiyer MCP — Fase 5: proveedores, RFQ y respuestas por correo

Estado: **implementada en código y pruebas locales**
Fecha: 2026-08-14

## Alcance

Esta fase permite seleccionar proveedores por ítem, preparar y editar RFQ,
enviarlas por la integración Gmail del actor, verificar respuestas reales y
revisar los datos extraídos por el agente de correo. Reutiliza las tablas y
agentes productivos; no crea un flujo paralelo.

## Tools

### Proveedores y matriz

- `suggest_suppliers(list_id)`
- `get_supplier_matrix(list_id)`
- `set_supplier_matrix(list_id, selections)`

Las recomendaciones provienen del directorio privado y de
`supplier_capabilities`, excluyen proveedores bloqueados y explican por qué
un proveedor abastece una categoría.

### Preparación y envío

- `prepare_rfq(list_id)`: crea o retoma un borrador por proveedor.
- `get_rfq_preview(list_id)`: muestra destinatario, asunto, cuerpo e ítems.
- `update_rfq_draft(...)`: permite corregir los tres campos antes de enviar.
- `send_rfq(list_id, batch_id, confirmed)`: exige `confirmed=true`.
- `get_rfq_status(list_id)`: combina batches y conversaciones en un estado
  canónico: `draft`, `ready`, `sending`, `sent`, `partially_answered`,
  `answered`, `failed` o `delivery_uncertain`.

`send_rfq` conserva la idempotencia existente. Si el batch ya está `sent`, no
vuelve a enviar; si está `sending` o `delivery_uncertain`, bloquea el reintento
para evitar correos duplicados.

### Respuestas

- `sync_supplier_replies(confirmed)`: ejecuta manualmente el agente Gmail.
- `list_supplier_replies(list_id?)`
- `get_supplier_reply(conversation_id)`
- `apply_reply_proposal(proposal_id, confirmed)`
- `reject_reply_proposal(proposal_id, confirmed)`

Las respuestas se verifican desde mensajes persistidos. El agente puede
extraer precio, moneda, disponibilidad, plazo y condiciones de pago. Sólo las
propuestas todavía pendientes pueden aplicarse o rechazarse; una decisión ya
tomada no puede invertirse accidentalmente desde MCP.

## Flujo recomendado

```text
suggest_suppliers
get_supplier_matrix
set_supplier_matrix
prepare_rfq
get_rfq_preview
update_rfq_draft (si hace falta)
mostrar preview y pedir confirmación humana
send_rfq(..., confirmed=true)
get_rfq_status
sync_supplier_replies(..., confirmed=true) o esperar cron
list_supplier_replies / get_supplier_reply
confirmar apply_reply_proposal o reject_reply_proposal
```

## Seguridad

- El actor y organización vienen exclusivamente del token MCP.
- Scopes separados: `suppliers:read`, `rfq:read`, `rfq:write`, `rfq:send`,
  `mail:read`, `mail:sync` y `quotes:write`.
- Enviar, sincronizar y decidir propuestas exige confirmación explícita.
- Correos y adjuntos se consideran datos no confiables; sus instrucciones no
  pueden activar tools.
- La integración Gmail es personal: envía usando la cuenta conectada del
  actor, no la de otro miembro de la organización.

## Verificación

- 51 pruebas específicas de MCP aprobadas.
- 228 pruebas generales aprobadas, excluyendo únicamente el test preexistente
  que llama Gemini en vivo.
- 36 tools publicadas en el catálogo MCP total.
- No se envió ningún correo real durante las pruebas.
- No requiere migración SQL adicional.

## Pendientes del dominio

- `prepare_supplier_followup` y `send_supplier_followup` manuales siguen fuera
  de esta fase: el agente actual ya envía seguimientos automáticos cuando
  detecta campos faltantes. Se implementarán cuando exista un draft manual
  persistido para evitar dos seguimientos paralelos.
- El envío agrupado de RFQ usa actualmente Gmail. Outlook tiene agente de
  respuestas propio, pero el router agrupado aún no soporta seleccionar el
  proveedor de correo; no se simula soporte desde MCP hasta unificarlo.
