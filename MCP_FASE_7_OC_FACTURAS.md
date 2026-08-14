# Baiyer MCP — Fase 7: órdenes de compra y facturas

Estado: **implementada en código y pruebas locales**
Fecha: 2026-08-14

## Órdenes de compra

Tools:

- `prepare_purchase_order(list_id, cotizacion_id)`
- `create_purchase_order(draft_id, confirmed, notes?)`
- `list_purchase_orders(status?, limit?)`
- `get_purchase_order(po_id)`
- `update_purchase_order(po_id, changes, confirmed)`
- `send_purchase_order(po_id, pdf_base64, confirmed)`
- `get_purchase_order_tracking(po_id)`

El preview deriva proveedor, resultado, precio, moneda, cantidad, plazo y
condiciones desde la oferta definitiva persistida. Crear y enviar son acciones
separadas. Si la organización tiene Workflow Builder activo, crear exige que
la lista esté aprobada sin observaciones.

El envío acepta únicamente PDF válido de hasta 15 MB, comprueba propiedad de
la OC y toma destinatario/número/monto desde la base de datos. El token público
de confirmación nunca se devuelve por MCP.

## Facturas

Tools:

- `preview_invoice_import(file_base64, file_name, file_mime)`
- `commit_invoice_import(draft_id, confirmed, oc_id?)`
- `list_invoices(status?, month?)`
- `get_invoice(invoice_id)`
- `reconcile_invoice_po(invoice_id, po_id)`
- `match_invoice_to_po(invoice_id, po_id, confirmed)`
- `mark_invoice_paid(invoice_id, confirmed, payment_date?)`
- `scan_invoice_inbox(confirmed)`

El preview usa Gemini sólo para extracción estructurada y trata el documento
como datos no confiables. Guarda el resultado y hash, no el archivo completo.
La conciliación compara monto, moneda y proveedor sin escribir; la vinculación
es una acción posterior confirmada.

## Endurecimiento del flujo web

El endpoint existente `/api/oc/enviar` ahora:

- valida que la OC pertenezca a la organización;
- rechaza OCs que ya no estén en borrador;
- valida base64;
- sólo marca `enviada` después de confirmar el envío;
- usa `delivery_uncertain` y HTTP 502 si Gmail no confirma, evitando reenvíos
  ciegos y estados falsos.

## Verificación

- 60 pruebas específicas MCP aprobadas.
- 237 pruebas generales aprobadas, salvo el test preexistente con Gemini vivo.
- 62 tools MCP totales.
- No se enviaron OCs ni se importaron facturas reales.
- No requiere migración SQL adicional.

## Pendientes

- Generación PDF de OC sigue siendo responsabilidad del cliente/UI; MCP recibe
  el PDF ya revisado para enviarlo.
- La extracción documental debe validarse end-to-end con facturas reales
  anonimizadas tras el despliegue.
