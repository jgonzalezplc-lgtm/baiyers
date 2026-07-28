-- 021: agrega el estado 'compra_iniciada' y un tipo de conversación
-- (cotización vs. compra) para la etapa que arranca cuando un proveedor
-- queda seleccionado y autorizado. Ejecutar en el SQL Editor de Supabase.

ALTER TABLE public.gmail_conversations DROP CONSTRAINT IF EXISTS gmail_conversations_estado_check;
ALTER TABLE public.gmail_conversations ADD CONSTRAINT gmail_conversations_estado_check CHECK (estado IN (
  'draft', 'ready_to_send', 'sent', 'waiting_for_supplier',
  'supplier_replied', 'partially_answered', 'clarification_required',
  'complete', 'closed', 'human_review_required', 'failed', 'compra_iniciada'
));

ALTER TABLE public.gmail_conversations
  ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'cotizacion' CHECK (tipo IN ('cotizacion', 'compra'));
