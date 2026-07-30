-- 026: Fase 5 Supplier Capability Intelligence — RFQs agrupadas.
-- Un correo por proveedor puede contener varios ítems/resultados y enlazarse
-- a una única conversación Gmail. Todo es aditivo y privado por usuario.

CREATE TABLE IF NOT EXISTS public.rfq_batches (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  lista_proyecto_id     UUID NOT NULL REFERENCES public.proyectos(id) ON DELETE CASCADE,
  proveedor_id          UUID NOT NULL REFERENCES public.proveedores(id) ON DELETE CASCADE,
  contacto_id           UUID REFERENCES public.proveedor_contactos(id) ON DELETE SET NULL,
  conversation_id       UUID UNIQUE REFERENCES public.gmail_conversations(id) ON DELETE SET NULL,
  destinatario_email    TEXT NOT NULL,
  subject               TEXT NOT NULL,
  body                  TEXT NOT NULL,
  estado                TEXT NOT NULL DEFAULT 'draft' CHECK (estado IN (
                          'draft', 'ready_to_send', 'sending', 'sent',
                          'failed', 'delivery_uncertain'
                        )),
  clave_idempotencia    TEXT NOT NULL,
  gmail_message_id      TEXT,
  gmail_thread_id       TEXT,
  error_detalle         TEXT,
  sent_at               TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, clave_idempotencia),
  UNIQUE (lista_proyecto_id, proveedor_id)
);

CREATE INDEX IF NOT EXISTS idx_rfq_batches_user ON public.rfq_batches(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rfq_batches_lista ON public.rfq_batches(lista_proyecto_id);
CREATE INDEX IF NOT EXISTS idx_rfq_batches_conversation ON public.rfq_batches(conversation_id);

ALTER TABLE public.rfq_batches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "rfq_batches_own" ON public.rfq_batches FOR ALL USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS public.rfq_batch_items (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rfq_batch_id        UUID NOT NULL REFERENCES public.rfq_batches(id) ON DELETE CASCADE,
  cotizacion_id       UUID NOT NULL REFERENCES public.cotizaciones(id) ON DELETE CASCADE,
  resultado_id        UUID NOT NULL REFERENCES public.resultados(id) ON DELETE CASCADE,
  cantidad            NUMERIC NOT NULL DEFAULT 1 CHECK (cantidad > 0),
  unidad              TEXT NOT NULL DEFAULT 'un',
  estado              TEXT NOT NULL DEFAULT 'pending' CHECK (estado IN ('pending', 'sent', 'responded', 'closed')),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (rfq_batch_id, cotizacion_id),
  UNIQUE (rfq_batch_id, resultado_id)
);

CREATE INDEX IF NOT EXISTS idx_rfq_batch_items_batch ON public.rfq_batch_items(rfq_batch_id);
CREATE INDEX IF NOT EXISTS idx_rfq_batch_items_resultado ON public.rfq_batch_items(resultado_id);

ALTER TABLE public.rfq_batch_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "rfq_batch_items_own" ON public.rfq_batch_items FOR ALL USING (
  auth.uid() = (SELECT user_id FROM public.rfq_batches WHERE id = rfq_batch_id)
);
