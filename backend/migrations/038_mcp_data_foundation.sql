-- 038: Baiyer MCP Fase 1 — jobs, drafts e importación atómica de listas.
-- IDEMPOTENTE. Ejecutar manualmente en Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS public.integration_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES public.organizaciones(id) ON DELETE CASCADE,
  actor_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
    'queued', 'running', 'awaiting_input', 'completed', 'failed', 'cancelled'
  )),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  input JSONB NOT NULL DEFAULT '{}'::jsonb,
  output JSONB,
  error JSONB,
  idempotency_key TEXT NOT NULL,
  request_id UUID,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS integration_jobs_org_created_idx
  ON public.integration_jobs(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS integration_jobs_status_idx
  ON public.integration_jobs(status) WHERE status IN ('queued', 'running', 'awaiting_input');

ALTER TABLE public.integration_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS integration_jobs_org ON public.integration_jobs;
CREATE POLICY integration_jobs_org ON public.integration_jobs FOR ALL USING (
  EXISTS (
    SELECT 1 FROM public.membresias_organizacion m
    WHERE m.organizacion_id = integration_jobs.organization_id
      AND m.user_id = auth.uid()
  )
) WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.membresias_organizacion m
    WHERE m.organizacion_id = integration_jobs.organization_id
      AND m.user_id = auth.uid()
  )
);

CREATE TABLE IF NOT EXISTS public.integration_drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES public.organizaciones(id) ON DELETE CASCADE,
  actor_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  draft_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'committed', 'discarded', 'expired')),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_name TEXT,
  source_mime TEXT,
  source_hash TEXT,
  committed_entity_type TEXT,
  committed_entity_id UUID,
  request_id UUID,
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS integration_drafts_org_created_idx
  ON public.integration_drafts(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS integration_drafts_active_idx
  ON public.integration_drafts(expires_at) WHERE status = 'active';

ALTER TABLE public.integration_drafts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS integration_drafts_org ON public.integration_drafts;
CREATE POLICY integration_drafts_org ON public.integration_drafts FOR ALL USING (
  EXISTS (
    SELECT 1 FROM public.membresias_organizacion m
    WHERE m.organizacion_id = integration_drafts.organization_id
      AND m.user_id = auth.uid()
  )
) WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.membresias_organizacion m
    WHERE m.organizacion_id = integration_drafts.organization_id
      AND m.user_id = auth.uid()
  )
);

-- Guarda N cotizaciones y su lista en una única transacción. La comprobación
-- de membresía evita que incluso una llamada backend defectuosa atribuya el
-- trabajo a una organización ajena. La idempotencia se materializa como job
-- completado para devolver el mismo resultado en reintentos.
CREATE OR REPLACE FUNCTION public.baiyer_create_list_from_items(
  p_actor_user_id UUID,
  p_organization_id UUID,
  p_name TEXT,
  p_source_description TEXT,
  p_items JSONB,
  p_idempotency_key TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_existing JSONB;
  v_project_id UUID;
  v_quote_id UUID;
  v_item JSONB;
  v_list_items JSONB := '[]'::jsonb;
  v_payload JSONB;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM public.membresias_organizacion
    WHERE organizacion_id = p_organization_id AND user_id = p_actor_user_id
  ) THEN
    RAISE EXCEPTION 'actor_not_in_organization';
  END IF;
  IF trim(coalesce(p_name, '')) = '' OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
    RAISE EXCEPTION 'invalid_list_input';
  END IF;

  SELECT output INTO v_existing
  FROM public.integration_jobs
  WHERE organization_id = p_organization_id AND idempotency_key = p_idempotency_key
    AND status = 'completed';
  IF v_existing IS NOT NULL THEN RETURN v_existing; END IF;

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_items)
  LOOP
    IF trim(coalesce(v_item->>'nombre_tecnico', '')) = ''
       OR coalesce((v_item->>'cantidad')::numeric, 1) <= 0 THEN
      RAISE EXCEPTION 'invalid_list_item';
    END IF;
    INSERT INTO public.cotizaciones (
      user_id, descripcion, nombre_identificado, marca, numero_parte,
      categoria, terminos_busqueda_es, terminos_busqueda_en, estado, confianza_ia
    ) VALUES (
      p_actor_user_id, p_source_description, v_item->>'nombre_tecnico',
      nullif(v_item->>'marca', ''), nullif(v_item->>'numero_parte', ''),
      coalesce(nullif(v_item->>'categoria', ''), 'otro'),
      ARRAY(SELECT jsonb_array_elements_text(coalesce(v_item->'terminos_busqueda_es', '[]'::jsonb))),
      ARRAY(SELECT jsonb_array_elements_text(coalesce(v_item->'terminos_busqueda_en', '[]'::jsonb))),
      'identificado', coalesce(nullif(v_item->>'confianza', ''), 'medio')
    ) RETURNING id INTO v_quote_id;
    v_list_items := v_list_items || jsonb_build_array(jsonb_build_object(
      'cotizacion_id', v_quote_id, 'nombre', v_item->>'nombre_tecnico',
      'cantidad', coalesce((v_item->>'cantidad')::numeric, 1),
      'unidad', coalesce(nullif(v_item->>'unidad', ''), 'unidad'),
      'partida', v_item->'partida', 'comparado', false,
      'categoria', coalesce(nullif(v_item->>'categoria', ''), 'otro')
    ));
  END LOOP;

  v_payload := jsonb_build_object('tipo', 'lista_cotizacion', 'items', v_list_items, 'definitivos', '{}'::jsonb);
  INSERT INTO public.proyectos(user_id, nombre, descripcion, estado, monto_total)
  VALUES (p_actor_user_id, trim(p_name), v_payload::text, 'borrador', 0)
  RETURNING id INTO v_project_id;
  v_existing := jsonb_build_object('id', v_project_id) || v_payload;

  INSERT INTO public.integration_jobs(
    organization_id, actor_user_id, client_id, job_type, status, progress,
    input, output, idempotency_key, finished_at
  ) VALUES (
    p_organization_id, p_actor_user_id, 'application-service', 'create_list_from_items',
    'completed', 100, jsonb_build_object('name', p_name), v_existing,
    p_idempotency_key, now()
  ) ON CONFLICT (organization_id, idempotency_key) DO UPDATE
    SET output = EXCLUDED.output, status = 'completed', progress = 100,
        finished_at = now(), updated_at = now();
  RETURN v_existing;
END;
$$;

REVOKE ALL ON FUNCTION public.baiyer_create_list_from_items(UUID, UUID, TEXT, TEXT, JSONB, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.baiyer_create_list_from_items(UUID, UUID, TEXT, TEXT, JSONB, TEXT) TO service_role;
