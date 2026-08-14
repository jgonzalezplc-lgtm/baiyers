-- 037: Agente de Outlook (Microsoft Graph) — espejo EXACTO del esquema del
-- agente de Gmail (019 + 020 [solo proveedor_id/contacto_id] + 021 [tipo +
-- estado ampliado] + 023 [oc_id]), pero con tablas propias
-- outlook_conversations / outlook_messages / outlook_attachments, usando
-- los identificadores nativos de Graph (graph_thread_id = conversationId,
-- graph_message_id = id de mensaje, graph_attachment_id = id de adjunto).
--
-- Alcance recortado a propósito: NO se replica rfq_batches/rfq_batch_items
-- (migración 026) — el agente de Outlook en esta primera versión sólo
-- soporta conversación 1:1 (una conversación = una cotización/resultado, o
-- el seguimiento de una OC vía oc_id). No se toca item_field_updates: ya es
-- genérica (source_type de texto libre) — para Outlook se usa
-- source_type='outlook_message'.
--
-- Ejecutar manualmente en el SQL Editor de Supabase (no hay DDL automático
-- en este proyecto).

CREATE TABLE IF NOT EXISTS public.outlook_conversations (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL,
  graph_thread_id     TEXT NOT NULL,
  proveedor_nombre    TEXT,
  proveedor_email     TEXT,
  proveedor_id        UUID REFERENCES public.proveedores(id) ON DELETE SET NULL,
  contacto_id         UUID REFERENCES public.proveedor_contactos(id) ON DELETE SET NULL,
  lista_proyecto_id   UUID REFERENCES public.proyectos(id) ON DELETE SET NULL,
  cotizacion_id       UUID,
  resultado_id        UUID,
  oc_id               UUID REFERENCES public.ordenes_compra(id) ON DELETE SET NULL,
  subject             TEXT,
  estado              TEXT NOT NULL DEFAULT 'sent' CHECK (estado IN (
                         'draft', 'ready_to_send', 'sent', 'waiting_for_supplier',
                         'supplier_replied', 'partially_answered', 'clarification_required',
                         'complete', 'closed', 'human_review_required', 'failed', 'compra_iniciada'
                       )),
  tipo                TEXT NOT NULL DEFAULT 'cotizacion' CHECK (tipo IN ('cotizacion', 'compra')),
  last_message_at     TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, graph_thread_id)
);

CREATE INDEX IF NOT EXISTS idx_outlook_conversations_user ON public.outlook_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_outlook_conversations_estado ON public.outlook_conversations(estado);
CREATE INDEX IF NOT EXISTS idx_outlook_conversations_cotizacion ON public.outlook_conversations(cotizacion_id);
CREATE INDEX IF NOT EXISTS idx_outlook_conversations_proveedor ON public.outlook_conversations(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_outlook_conversations_oc ON public.outlook_conversations(oc_id);

CREATE TABLE IF NOT EXISTS public.outlook_messages (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id   UUID NOT NULL REFERENCES public.outlook_conversations(id) ON DELETE CASCADE,
  graph_message_id  TEXT NOT NULL UNIQUE,
  graph_thread_id   TEXT NOT NULL,
  direction         TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
  from_email        TEXT,
  to_email          TEXT,
  subject           TEXT,
  body_text         TEXT,
  received_at       TIMESTAMPTZ,
  procesado         BOOLEAN NOT NULL DEFAULT false,
  raw_headers       JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outlook_messages_conversation ON public.outlook_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_outlook_messages_procesado ON public.outlook_messages(procesado) WHERE direction = 'inbound' AND procesado = false;

CREATE TABLE IF NOT EXISTS public.outlook_attachments (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id            UUID NOT NULL REFERENCES public.outlook_messages(id) ON DELETE CASCADE,
  filename              TEXT,
  mime_type             TEXT,
  graph_attachment_id   TEXT,
  hash                  TEXT,
  texto_extraido        TEXT,
  entity_type           TEXT,
  entity_id             TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outlook_attachments_message ON public.outlook_attachments(message_id);

-- ─── RLS ────────────────────────────────────────────────────────────────────
-- Las tablas equivalentes de Gmail (gmail_conversations/messages/attachments,
-- migración 019) nunca quedaron con RLS habilitado — gap preexistente que no
-- se replica acá. El backend usa el service key (bypassea RLS) para todo el
-- acceso real; esto es sólo defensa en profundidad si algún día se consulta
-- con el anon/authenticated key directo. Mismo patrón que 031_rls_organizacion.sql.

ALTER TABLE public.outlook_conversations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outlook_conversations_org ON public.outlook_conversations;
CREATE POLICY outlook_conversations_org ON public.outlook_conversations
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

ALTER TABLE public.outlook_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outlook_messages_org ON public.outlook_messages;
CREATE POLICY outlook_messages_org ON public.outlook_messages
    FOR ALL USING (EXISTS (
        SELECT 1 FROM public.outlook_conversations c
        WHERE c.id = outlook_messages.conversation_id
          AND public.es_miembro_de_organizacion(auth.uid(), c.user_id)
    ));

ALTER TABLE public.outlook_attachments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outlook_attachments_org ON public.outlook_attachments;
CREATE POLICY outlook_attachments_org ON public.outlook_attachments
    FOR ALL USING (EXISTS (
        SELECT 1 FROM public.outlook_messages m
        JOIN public.outlook_conversations c ON c.id = m.conversation_id
        WHERE m.id = outlook_attachments.message_id
          AND public.es_miembro_de_organizacion(auth.uid(), c.user_id)
    ));
