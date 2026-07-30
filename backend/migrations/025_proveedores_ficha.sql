-- 025: Fase 3 de Supplier Capability Intelligence — alta manual de proveedores,
-- investigación automática y ficha completa. Solo columnas nuevas en
-- `proveedores` (existente, con datos reales) y una ampliación del CHECK de
-- `supplier_capability_events.tipo_evento` para el nuevo tipo de evento
-- "asignación manual de categoría" — nada destructivo, nada se borra.

ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS sitio_web TEXT;
ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS telefono TEXT;
ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS notas_privadas TEXT;
ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS preferido BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.supplier_capability_events DROP CONSTRAINT IF EXISTS supplier_capability_events_tipo_evento_check;
ALTER TABLE public.supplier_capability_events ADD CONSTRAINT supplier_capability_events_tipo_evento_check CHECK (tipo_evento IN (
  'appeared_in_search', 'search_result_relevant', 'search_result_rejected',
  'supplier_selected_for_rfq', 'supplier_replied_can_supply', 'supplier_replied_cannot_supply',
  'valid_quote_received', 'supplier_selected', 'purchase_approved', 'purchase_completed',
  'user_corrected_category', 'no_satisfactory_results',
  'manual_category_assigned'
));
