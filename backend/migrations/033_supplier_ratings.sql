-- 033: supplier_ratings + rating_pendiente — referenciadas en el código desde
-- hace tiempo (suppliers.py, supplier_intelligence.py, cron.py, estadisticas.py,
-- reportes.py) pero nunca aplicadas en producción. Hoy todo el código que las
-- usa está defendido con try/except, así que la app no se cae, pero la
-- funcionalidad de rating de proveedores está completamente muerta: el cron
-- de envío de emails de rating falla en silencio en cada corrida, y
-- POST /api/suppliers/rating siempre devuelve 500 si alguien llega al modal.

CREATE TABLE IF NOT EXISTS public.supplier_ratings (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  proveedor_id     UUID NOT NULL REFERENCES public.proveedores(id) ON DELETE CASCADE,
  resultado_id     UUID REFERENCES public.resultados(id) ON DELETE SET NULL,
  estrellas        INTEGER NOT NULL CHECK (estrellas BETWEEN 1 AND 5),
  precio_cumplido  BOOLEAN,
  plazo_cumplido   BOOLEAN,
  comentario       TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_ratings_proveedor ON public.supplier_ratings(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_supplier_ratings_user ON public.supplier_ratings(user_id, created_at DESC);

ALTER TABLE public.supplier_ratings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "supplier_ratings_own" ON public.supplier_ratings FOR ALL USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS public.rating_pendiente (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  oc_id         UUID NOT NULL REFERENCES public.ordenes_compra(id) ON DELETE CASCADE,
  proveedor_id  UUID REFERENCES public.proveedores(id) ON DELETE SET NULL,
  enviar_en     TIMESTAMPTZ NOT NULL,
  enviado       BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (oc_id)
);

CREATE INDEX IF NOT EXISTS idx_rating_pendiente_pendientes ON public.rating_pendiente(enviar_en) WHERE enviado = false;

ALTER TABLE public.rating_pendiente ENABLE ROW LEVEL SECURITY;
CREATE POLICY "rating_pendiente_own" ON public.rating_pendiente FOR ALL USING (auth.uid() = user_id);
