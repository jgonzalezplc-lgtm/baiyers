-- 022: campanita de notificaciones. Tabla genérica para eventos que el usuario
-- debe ver (aprobación de cotización, respuesta de proveedor por correo, y los
-- triggers que se vayan agregando después). `tipo` no tiene CHECK para no
-- migrar cada vez que se suma un trigger nuevo — el frontend decide ícono/label
-- por tipo y cae a un ícono genérico si no lo reconoce.
CREATE TABLE IF NOT EXISTS public.notificaciones (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  tipo        TEXT NOT NULL,        -- 'cotizacion_aprobada' | 'email_cotizacion' | ...
  titulo      TEXT NOT NULL,
  mensaje     TEXT NOT NULL,
  data        JSONB NOT NULL DEFAULT '{}'::jsonb,  -- lista_id, proveedor_nombre, item_nombre, etc.
  leido       BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notificaciones_user ON public.notificaciones(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notificaciones_user_no_leidas ON public.notificaciones(user_id) WHERE leido = false;

ALTER TABLE public.notificaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY "notificaciones_own" ON public.notificaciones FOR ALL USING (auth.uid() = user_id);
