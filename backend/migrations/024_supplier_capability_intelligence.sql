-- 024: Supplier Capability Intelligence — Fase 1 (fundaciones).
-- Perfil de compra por usuario, sesiones de búsqueda auditables, feedback
-- explícito y evidencia inmutable de qué proveedor abastece qué categoría.
-- Todo nuevo: no toca `proveedores`, `resultados`, `cotizaciones` ni las
-- tablas del agente de Gmail. Nombres elegidos para NO colisionar con
-- `supplier_categories`/`procurement_ledger` (definidas en 014_smart_procurement.sql
-- pero nunca aplicadas en producción — confirmado contra el esquema real).

-- ─── Perfil de procurement ──────────────────────────────────────────────
-- Uno por usuario. Se genera al completar el onboarding y evoluciona con uso
-- real; nunca se sobreescribe sin dejar rastro en procurement_profile_categories.
CREATE TABLE IF NOT EXISTS public.procurement_profiles (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  empresa               TEXT,
  dominio               TEXT,
  industria             TEXT,
  pais                  TEXT,
  descripcion_actividad TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.procurement_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "procurement_profiles_own" ON public.procurement_profiles FOR ALL USING (auth.uid() = user_id);

-- Cada categoría sugerida/confirmada, con su propia confianza y evidencia —
-- nunca una lista plana. `origenes` acumula todas las señales que la tocaron
-- (ej: {'onboarding','industry_prior'} o luego + 'search_history').
CREATE TABLE IF NOT EXISTS public.procurement_profile_categories (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id             UUID NOT NULL REFERENCES public.procurement_profiles(id) ON DELETE CASCADE,
  categoria              TEXT NOT NULL,
  confianza              NUMERIC NOT NULL DEFAULT 0.5 CHECK (confianza >= 0 AND confianza <= 1),
  origenes               TEXT[] NOT NULL DEFAULT '{}',
  confirmado_por_usuario BOOLEAN NOT NULL DEFAULT false,
  evidencia_positiva     INT NOT NULL DEFAULT 0,
  evidencia_negativa     INT NOT NULL DEFAULT 0,
  ultima_evidencia_at    TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(profile_id, categoria)
);

CREATE INDEX IF NOT EXISTS idx_procurement_profile_categories_profile ON public.procurement_profile_categories(profile_id);

ALTER TABLE public.procurement_profile_categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "procurement_profile_categories_own" ON public.procurement_profile_categories FOR ALL USING (
  auth.uid() = (SELECT user_id FROM public.procurement_profiles WHERE id = profile_id)
);

-- ─── Sesiones de búsqueda ───────────────────────────────────────────────
-- Una fila por intento de búsqueda (directa o expandida). `session_padre_id`
-- encadena una expansión con la búsqueda original que la disparó.
CREATE TABLE IF NOT EXISTS public.search_sessions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  cotizacion_id       UUID REFERENCES public.cotizaciones(id) ON DELETE SET NULL,
  lista_proyecto_id   UUID REFERENCES public.proyectos(id) ON DELETE SET NULL,
  item_nombre         TEXT,
  categoria_predicha  TEXT,
  categorias_usadas   TEXT[] NOT NULL DEFAULT '{}',
  terminos            TEXT[] NOT NULL DEFAULT '{}',
  modo                TEXT NOT NULL DEFAULT 'directed' CHECK (modo IN ('directed', 'expanded')),
  session_padre_id    UUID REFERENCES public.search_sessions(id) ON DELETE SET NULL,
  n_resultados        INT NOT NULL DEFAULT 0,
  estado              TEXT NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'satisfactoria', 'insatisfactoria', 'expandida')),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_search_sessions_user ON public.search_sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_sessions_cotizacion ON public.search_sessions(cotizacion_id);

ALTER TABLE public.search_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "search_sessions_own" ON public.search_sessions FOR ALL USING (auth.uid() = user_id);

-- Feedback explícito del usuario sobre una sesión ("No encontré lo que
-- buscaba", corrección de categoría, expansión, o confirmación de que sí
-- sirvió). Es la señal fuerte que el spec pide priorizar.
CREATE TABLE IF NOT EXISTS public.search_feedback (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id          UUID NOT NULL REFERENCES public.search_sessions(id) ON DELETE CASCADE,
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo                TEXT NOT NULL CHECK (tipo IN ('wrong_products', 'missing_suppliers', 'wrong_category', 'expand_search', 'satisfactory')),
  categoria_predicha  TEXT,
  categoria_corregida TEXT,
  comentario          TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_search_feedback_session ON public.search_feedback(session_id);

ALTER TABLE public.search_feedback ENABLE ROW LEVEL SECURITY;
CREATE POLICY "search_feedback_own" ON public.search_feedback FOR ALL USING (auth.uid() = user_id);

-- ─── Evidencia y capacidad de proveedores ───────────────────────────────
-- Log inmutable de eventos. `clave_idempotencia` evita duplicar el mismo
-- evento en reintentos (ej: el cron de Gmail procesando el mismo mensaje
-- dos veces, o un usuario refrescando la página de resultados).
CREATE TABLE IF NOT EXISTS public.supplier_capability_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  proveedor_id          UUID NOT NULL REFERENCES public.proveedores(id) ON DELETE CASCADE,
  resultado_id          UUID REFERENCES public.resultados(id) ON DELETE SET NULL,
  cotizacion_id         UUID REFERENCES public.cotizaciones(id) ON DELETE SET NULL,
  session_id            UUID REFERENCES public.search_sessions(id) ON DELETE SET NULL,
  categoria_predicha    TEXT,
  categoria_confirmada  TEXT,
  concepto_normalizado  TEXT NOT NULL DEFAULT '',
  tipo_evento           TEXT NOT NULL CHECK (tipo_evento IN (
                          'appeared_in_search', 'search_result_relevant', 'search_result_rejected',
                          'supplier_selected_for_rfq', 'supplier_replied_can_supply', 'supplier_replied_cannot_supply',
                          'valid_quote_received', 'supplier_selected', 'purchase_approved', 'purchase_completed',
                          'user_corrected_category', 'no_satisfactory_results'
                        )),
  peso                  NUMERIC NOT NULL,
  clave_idempotencia    TEXT NOT NULL UNIQUE,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_capability_events_lookup ON public.supplier_capability_events(user_id, proveedor_id, categoria_confirmada);

ALTER TABLE public.supplier_capability_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "supplier_capability_events_own" ON public.supplier_capability_events FOR ALL USING (auth.uid() = user_id);

-- Capacidad calculada (derivada SIEMPRE recalculando desde los eventos, nunca
-- incrementada in-place — evita condiciones de carrera de "leer y luego
-- escribir" bajo escrituras concurrentes).
CREATE TABLE IF NOT EXISTS public.supplier_capabilities (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  proveedor_id         UUID NOT NULL REFERENCES public.proveedores(id) ON DELETE CASCADE,
  categoria            TEXT NOT NULL,
  concepto             TEXT NOT NULL DEFAULT '',
  confianza            NUMERIC NOT NULL DEFAULT 0 CHECK (confianza >= 0 AND confianza <= 1),
  evidencia_positiva   INT NOT NULL DEFAULT 0,
  evidencia_negativa   INT NOT NULL DEFAULT 0,
  cotizaciones_validas INT NOT NULL DEFAULT 0,
  compras              INT NOT NULL DEFAULT 0,
  estado               TEXT NOT NULL DEFAULT 'probable' CHECK (estado IN ('probable', 'confirmed', 'rejected')),
  ultima_evidencia_at  TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, proveedor_id, categoria, concepto)
);

CREATE INDEX IF NOT EXISTS idx_supplier_capabilities_ranking ON public.supplier_capabilities(user_id, categoria, confianza DESC);

ALTER TABLE public.supplier_capabilities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "supplier_capabilities_own" ON public.supplier_capabilities FOR ALL USING (auth.uid() = user_id);
