-- 019: Esquema base del agente de Gmail (Fase 1 — threading + lectura + propuestas).
-- No auto-envía respuestas ni auto-aplica cambios: todo queda como propuesta para
-- revisión humana (item_field_updates.estado = 'propuesta'). Ejecutar en el SQL
-- Editor de Supabase.

CREATE TABLE IF NOT EXISTS public.gmail_conversations (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL,
  gmail_thread_id     TEXT NOT NULL,
  proveedor_nombre    TEXT,
  proveedor_email     TEXT,
  lista_proyecto_id   UUID REFERENCES public.proyectos(id) ON DELETE SET NULL,
  cotizacion_id       UUID,
  resultado_id        UUID,
  subject             TEXT,
  estado              TEXT NOT NULL DEFAULT 'sent' CHECK (estado IN (
                         'draft', 'ready_to_send', 'sent', 'waiting_for_supplier',
                         'supplier_replied', 'partially_answered', 'clarification_required',
                         'complete', 'closed', 'human_review_required', 'failed'
                       )),
  last_message_at     TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, gmail_thread_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_conversations_user ON public.gmail_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_gmail_conversations_estado ON public.gmail_conversations(estado);
CREATE INDEX IF NOT EXISTS idx_gmail_conversations_cotizacion ON public.gmail_conversations(cotizacion_id);

CREATE TABLE IF NOT EXISTS public.gmail_messages (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id   UUID NOT NULL REFERENCES public.gmail_conversations(id) ON DELETE CASCADE,
  gmail_message_id  TEXT NOT NULL UNIQUE,
  gmail_thread_id   TEXT NOT NULL,
  direction         TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
  from_email        TEXT,
  to_email           TEXT,
  subject           TEXT,
  body_text         TEXT,
  received_at       TIMESTAMPTZ,
  procesado         BOOLEAN NOT NULL DEFAULT false,
  raw_headers       JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_conversation ON public.gmail_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_procesado ON public.gmail_messages(procesado) WHERE direction = 'inbound' AND procesado = false;

CREATE TABLE IF NOT EXISTS public.gmail_attachments (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id        UUID NOT NULL REFERENCES public.gmail_messages(id) ON DELETE CASCADE,
  filename          TEXT,
  mime_type         TEXT,
  gmail_attachment_id TEXT,
  hash              TEXT,
  texto_extraido    TEXT,
  entity_type       TEXT,
  entity_id         TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gmail_attachments_message ON public.gmail_attachments(message_id);

-- Audit log + cola de propuestas. 'propuesta' = detectado por el agente, pendiente
-- de revisión; 'aplicado' / 'descartado' = decisión humana ya tomada.
CREATE TABLE IF NOT EXISTS public.item_field_updates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL,
  entity_type     TEXT NOT NULL,   -- 'resultado' | 'cotizacion_item'
  entity_id       TEXT NOT NULL,
  field           TEXT NOT NULL,
  previous_value  JSONB,
  new_value       JSONB,
  currency        TEXT,
  source_type     TEXT NOT NULL,   -- 'gmail_message' | 'gmail_attachment'
  source_id       UUID,
  supplier_nombre TEXT,
  supplier_email  TEXT,
  confidence      NUMERIC,
  estado          TEXT NOT NULL DEFAULT 'propuesta' CHECK (estado IN ('propuesta', 'aplicado', 'descartado')),
  updated_by      TEXT NOT NULL DEFAULT 'gmail_agent',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at     TIMESTAMPTZ,
  reviewed_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_item_field_updates_entity ON public.item_field_updates(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_item_field_updates_estado ON public.item_field_updates(estado) WHERE estado = 'propuesta';
CREATE INDEX IF NOT EXISTS idx_item_field_updates_user ON public.item_field_updates(user_id);
