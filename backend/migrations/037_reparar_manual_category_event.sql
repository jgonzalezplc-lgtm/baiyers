-- 037: reparación de drift en producción.
-- La tabla existe, pero el CHECK desplegado no admite el evento que ya usa
-- Supplier Capability Intelligence para categorías confirmadas/importadas.

ALTER TABLE public.supplier_capability_events
  DROP CONSTRAINT IF EXISTS supplier_capability_events_tipo_evento_check;

ALTER TABLE public.supplier_capability_events
  ADD CONSTRAINT supplier_capability_events_tipo_evento_check
  CHECK (tipo_evento IN (
    'appeared_in_search', 'search_result_relevant', 'search_result_rejected',
    'supplier_selected_for_rfq', 'supplier_replied_can_supply', 'supplier_replied_cannot_supply',
    'valid_quote_received', 'supplier_selected', 'purchase_approved', 'purchase_completed',
    'user_corrected_category', 'no_satisfactory_results',
    'manual_category_assigned'
  ));
