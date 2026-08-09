-- 028: CapoDiTutti — identidad multiempresa y ledgers administrativos.
-- Todo es aditivo. No agrupa usuarios por el texto `empresa`: cada usuario
-- existente recibe primero una organización individual y puede migrarse luego
-- mediante una operación administrativa explícita y auditable.

CREATE TABLE IF NOT EXISTS public.organizations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre      TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  tipo        TEXT NOT NULL DEFAULT 'individual' CHECK (tipo IN ('individual', 'company', 'group')),
  estado      TEXT NOT NULL DEFAULT 'active' CHECK (estado IN ('active', 'trial', 'suspended', 'closed')),
  plan        TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'starter', 'trial', 'pro', 'business', 'enterprise')),
  metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.organization_memberships (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  rol               TEXT NOT NULL DEFAULT 'member' CHECK (rol IN ('owner', 'admin', 'member', 'billing')),
  estado            TEXT NOT NULL DEFAULT 'active' CHECK (estado IN ('invited', 'active', 'suspended', 'removed')),
  es_principal      BOOLEAN NOT NULL DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_membership_primary_user
  ON public.organization_memberships(user_id) WHERE es_principal AND estado = 'active';
CREATE INDEX IF NOT EXISTS idx_memberships_org ON public.organization_memberships(organization_id, estado);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON public.organization_memberships(user_id, estado);

CREATE TABLE IF NOT EXISTS public.admin_users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  rol         TEXT NOT NULL DEFAULT 'viewer' CHECK (rol IN ('viewer', 'operator', 'superadmin')),
  activo      BOOLEAN NOT NULL DEFAULT true,
  created_by  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.product_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
  user_id               UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  event_type            TEXT NOT NULL,
  entity_type           TEXT,
  entity_id             TEXT,
  correlation_id        UUID,
  status                TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'warning', 'error')),
  clave_idempotencia    TEXT UNIQUE,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_product_events_org_time ON public.product_events(organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_events_user_time ON public.product_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_events_type_time ON public.product_events(event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_events_correlation ON public.product_events(correlation_id);

CREATE TABLE IF NOT EXISTS public.ai_model_prices (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider              TEXT NOT NULL,
  model                 TEXT NOT NULL,
  input_usd_million     NUMERIC NOT NULL CHECK (input_usd_million >= 0),
  output_usd_million    NUMERIC NOT NULL CHECK (output_usd_million >= 0),
  currency              TEXT NOT NULL DEFAULT 'USD',
  valid_from            TIMESTAMPTZ NOT NULL,
  valid_to              TIMESTAMPTZ,
  source_url            TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(provider, model, valid_from)
);

CREATE TABLE IF NOT EXISTS public.ai_usage_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
  user_id               UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  product_event_id      UUID REFERENCES public.product_events(id) ON DELETE SET NULL,
  correlation_id        UUID,
  feature               TEXT NOT NULL,
  provider              TEXT NOT NULL,
  requested_model       TEXT NOT NULL,
  effective_model       TEXT NOT NULL,
  fallback_used         BOOLEAN NOT NULL DEFAULT false,
  input_tokens          BIGINT NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens         BIGINT NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  cached_tokens         BIGINT NOT NULL DEFAULT 0 CHECK (cached_tokens >= 0),
  latency_ms            INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
  estimated_cost_usd    NUMERIC(18,8) NOT NULL DEFAULT 0 CHECK (estimated_cost_usd >= 0),
  pricing_snapshot      JSONB NOT NULL DEFAULT '{}'::jsonb,
  status                TEXT NOT NULL CHECK (status IN ('success', 'fallback', 'error', 'timeout')),
  error_type            TEXT,
  error_message         TEXT,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_org_time ON public.ai_usage_events(organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user_time ON public.ai_usage_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_model_time ON public.ai_usage_events(provider, effective_model, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_feature_time ON public.ai_usage_events(feature, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_correlation ON public.ai_usage_events(correlation_id);

CREATE TABLE IF NOT EXISTS public.admin_audit_log (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_admin_id        UUID REFERENCES public.admin_users(id) ON DELETE SET NULL,
  target_organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
  target_user_id        UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  action                TEXT NOT NULL,
  entity_type           TEXT,
  entity_id             TEXT,
  reason                TEXT,
  previous_value        JSONB,
  new_value             JSONB,
  request_id            UUID,
  ip_hash               TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_time ON public.admin_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target_org ON public.admin_audit_log(target_organization_id, created_at DESC);

-- Resolver único para que los productores de eventos no repitan la lógica.
CREATE OR REPLACE FUNCTION public.primary_organization_for(p_user_id UUID)
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT organization_id
  FROM public.organization_memberships
  WHERE user_id = p_user_id AND estado = 'active'
  ORDER BY es_principal DESC, created_at ASC
  LIMIT 1;
$$;

REVOKE ALL ON FUNCTION public.primary_organization_for(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.primary_organization_for(UUID) TO service_role;

-- Backfill conservador: una organización aislada por usuario. El nombre de
-- empresa se usa solo como etiqueta, nunca para fusionar personas.
INSERT INTO public.organizations (nombre, slug, tipo, estado, plan, metadata)
SELECT
  COALESCE(NULLIF(u.raw_user_meta_data->>'empresa', ''), NULLIF(u.email, ''), 'Cuenta individual'),
  'user-' || u.id::text,
  'individual',
  'active',
  CASE
    WHEN COALESCE(u.raw_user_meta_data->>'plan', 'free') IN ('free','starter','trial','pro','business','enterprise')
      THEN COALESCE(u.raw_user_meta_data->>'plan', 'free')
    ELSE 'free'
  END,
  jsonb_build_object('backfill_source', 'auth.users', 'legacy_empresa', u.raw_user_meta_data->>'empresa')
FROM auth.users u
ON CONFLICT (slug) DO NOTHING;

INSERT INTO public.organization_memberships (organization_id, user_id, rol, estado, es_principal)
SELECT o.id, u.id, 'owner', 'active', true
FROM auth.users u
JOIN public.organizations o ON o.slug = 'user-' || u.id::text
ON CONFLICT (organization_id, user_id) DO NOTHING;

-- Los registros futuros también nacen aislados. La función no fusiona por
-- dominio ni empresa y puede ejecutarse repetidamente sin duplicar filas.
CREATE OR REPLACE FUNCTION public.create_personal_organization_for_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_org_id UUID;
  v_plan TEXT;
BEGIN
  v_plan := COALESCE(NEW.raw_user_meta_data->>'plan', 'free');
  IF v_plan NOT IN ('free','starter','trial','pro','business','enterprise') THEN
    v_plan := 'free';
  END IF;

  INSERT INTO public.organizations (nombre, slug, tipo, estado, plan, metadata)
  VALUES (
    COALESCE(NULLIF(NEW.raw_user_meta_data->>'empresa', ''), NULLIF(NEW.email, ''), 'Cuenta individual'),
    'user-' || NEW.id::text,
    'individual', 'active', v_plan,
    jsonb_build_object('backfill_source', 'auth.trigger', 'legacy_empresa', NEW.raw_user_meta_data->>'empresa')
  )
  ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug
  RETURNING id INTO v_org_id;

  INSERT INTO public.organization_memberships (organization_id, user_id, rol, estado, es_principal)
  VALUES (v_org_id, NEW.id, 'owner', 'active', true)
  ON CONFLICT (organization_id, user_id) DO NOTHING;
  RETURN NEW;
END;
$$;

-- No reemplazamos ni eliminamos triggers existentes. Si la migración se vuelve a
-- ejecutar, el trigger se conserva y esta sección queda como una operación nula.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'on_auth_user_created_create_personal_org'
      AND tgrelid = 'auth.users'::regclass
      AND NOT tgisinternal
  ) THEN
    CREATE TRIGGER on_auth_user_created_create_personal_org
      AFTER INSERT ON auth.users
      FOR EACH ROW
      EXECUTE FUNCTION public.create_personal_organization_for_new_user();
  END IF;
END;
$$;

-- Tarifas estándar vigentes al 2026-08-03. Se guarda el snapshot usado en
-- cada evento para que cambios futuros no reescriban el costo histórico.
INSERT INTO public.ai_model_prices
  (provider, model, input_usd_million, output_usd_million, valid_from, source_url)
VALUES
  ('google', 'gemini-3.5-flash-lite', 0.30, 2.50, '2026-08-03T00:00:00Z', 'https://ai.google.dev/gemini-api/docs/pricing'),
  ('google', 'gemini-2.5-flash', 0.30, 2.50, '2026-08-03T00:00:00Z', 'https://ai.google.dev/gemini-api/docs/pricing')
ON CONFLICT (provider, model, valid_from) DO NOTHING;

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_model_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "organizations_member_read" ON public.organizations FOR SELECT USING (
  EXISTS (SELECT 1 FROM public.organization_memberships m WHERE m.organization_id = id AND m.user_id = auth.uid() AND m.estado = 'active')
);
CREATE POLICY "memberships_own_read" ON public.organization_memberships FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "product_events_own_read" ON public.product_events FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "ai_usage_own_read" ON public.ai_usage_events FOR SELECT USING (user_id = auth.uid());

-- Sin políticas de escritura para usuarios autenticados. El backend service
-- role es el único productor y Capo accede siempre desde servidor.

-- Superficies administrativas. Nunca se conceden a anon/authenticated;
-- PostgREST solo puede leerlas usando la service role después de que el
-- backend haya verificado `admin_users`.
CREATE OR REPLACE VIEW public.capo_organization_overview
WITH (security_invoker = false)
AS
SELECT
  o.id,
  o.nombre,
  o.slug,
  o.tipo,
  o.estado,
  o.plan,
  o.created_at,
  count(m.id) FILTER (WHERE m.estado <> 'removed')::int AS members,
  count(m.id) FILTER (WHERE m.estado = 'active')::int AS active_members,
  (SELECT count(*)::int FROM public.search_sessions s
   WHERE s.user_id IN (SELECT om.user_id FROM public.organization_memberships om WHERE om.organization_id = o.id AND om.estado = 'active')
     AND s.created_at >= now() - interval '30 days') AS searches_30d,
  COALESCE((SELECT sum(a.estimated_cost_usd) FROM public.ai_usage_events a
            WHERE a.organization_id = o.id AND a.occurred_at >= now() - interval '30 days'), 0) AS ai_cost_30d
FROM public.organizations o
LEFT JOIN public.organization_memberships m ON m.organization_id = o.id
GROUP BY o.id;

CREATE OR REPLACE VIEW public.capo_user_overview
WITH (security_invoker = false)
AS
SELECT
  u.id,
  COALESCE(NULLIF(u.raw_user_meta_data->>'nombre_usuario', ''), split_part(COALESCE(u.email, ''), '@', 1), 'Usuario') AS name,
  u.email,
  o.id AS organization_id,
  o.nombre AS organization,
  m.rol AS membership_role,
  o.plan,
  u.last_sign_in_at,
  u.created_at,
  CASE WHEN u.banned_until IS NOT NULL AND u.banned_until > now() THEN 'suspended' ELSE 'active' END AS status,
  (SELECT count(*)::int FROM public.search_sessions s WHERE s.user_id = u.id AND s.created_at >= now() - interval '30 days') AS searches_30d,
  COALESCE((SELECT sum(a.estimated_cost_usd) FROM public.ai_usage_events a WHERE a.user_id = u.id AND a.occurred_at >= now() - interval '30 days'), 0) AS ai_cost_30d
FROM auth.users u
LEFT JOIN public.organization_memberships m ON m.user_id = u.id AND m.es_principal AND m.estado = 'active'
LEFT JOIN public.organizations o ON o.id = m.organization_id;

CREATE OR REPLACE FUNCTION public.capo_dashboard_metrics()
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT jsonb_build_object(
    'activeOrganizations', (SELECT count(*) FROM public.organizations WHERE estado IN ('active', 'trial')),
    'activeUsers30d', (SELECT count(*) FROM auth.users WHERE last_sign_in_at >= now() - interval '30 days'),
    'searches30d', (SELECT count(*) FROM public.search_sessions WHERE created_at >= now() - interval '30 days'),
    'aiCost30d', COALESCE((SELECT sum(estimated_cost_usd) FROM public.ai_usage_events WHERE occurred_at >= now() - interval '30 days'), 0),
    'aiCalls30d', (SELECT count(*) FROM public.ai_usage_events WHERE occurred_at >= now() - interval '30 days'),
    'errorRate', COALESCE((SELECT round(100.0 * count(*) FILTER (WHERE status IN ('error','timeout')) / NULLIF(count(*), 0), 2) FROM public.ai_usage_events WHERE occurred_at >= now() - interval '30 days'), 0)
  );
$$;

REVOKE ALL ON public.capo_organization_overview FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.capo_user_overview FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.capo_dashboard_metrics() FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.capo_organization_overview TO service_role;
GRANT SELECT ON public.capo_user_overview TO service_role;
GRANT EXECUTE ON FUNCTION public.capo_dashboard_metrics() TO service_role;
