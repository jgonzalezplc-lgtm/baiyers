-- 020: RUT + contactos múltiples en el directorio de proveedores existente, y
-- el link real del agente de Gmail hacia ese directorio (antes guardaba
-- proveedor_nombre/proveedor_email como texto libre). Ejecutar en el SQL
-- Editor de Supabase.

ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS rut TEXT;
CREATE INDEX IF NOT EXISTS idx_proveedores_rut ON public.proveedores(user_id, rut) WHERE rut IS NOT NULL;

-- Un proveedor puede tener varios contactos (ventas, logística, facturación...).
-- El email plano de `proveedores` se mantiene como campo legado/de conveniencia;
-- esta tabla es la fuente real para selección de destinatario y multi-contacto.
CREATE TABLE IF NOT EXISTS public.proveedor_contactos (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  proveedor_id  UUID NOT NULL REFERENCES public.proveedores(id) ON DELETE CASCADE,
  user_id       UUID NOT NULL,
  nombre        TEXT,
  email         TEXT NOT NULL,
  cargo         TEXT,
  es_principal  BOOLEAN NOT NULL DEFAULT false,
  origen        TEXT NOT NULL DEFAULT 'manual' CHECK (origen IN ('manual', 'excel', 'gmail_agent')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (proveedor_id, email)
);

CREATE INDEX IF NOT EXISTS idx_proveedor_contactos_proveedor ON public.proveedor_contactos(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_proveedor_contactos_email ON public.proveedor_contactos(user_id, email);

-- Backfill: cada proveedor con email plano existente obtiene su primer contacto.
INSERT INTO public.proveedor_contactos (proveedor_id, user_id, email, es_principal, origen)
SELECT id, user_id, email, true, 'manual'
FROM public.proveedores
WHERE email IS NOT NULL AND email <> ''
ON CONFLICT (proveedor_id, email) DO NOTHING;

-- Link real del agente de Gmail hacia el directorio (reemplaza el texto libre
-- proveedor_nombre/proveedor_email que ya existían en gmail_conversations).
ALTER TABLE public.gmail_conversations
  ADD COLUMN IF NOT EXISTS proveedor_id UUID REFERENCES public.proveedores(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS contacto_id  UUID REFERENCES public.proveedor_contactos(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_gmail_conversations_proveedor ON public.gmail_conversations(proveedor_id);
