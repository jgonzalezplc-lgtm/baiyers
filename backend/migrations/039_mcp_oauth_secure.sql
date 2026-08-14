-- 039: Baiyer MCP Fase 2 — OAuth revocable, PKCE/resource binding y rotación.
-- IDEMPOTENTE. Ejecutar manualmente en Supabase SQL Editor después de desplegar
-- el código compatible. No elimina conexiones ni códigos legacy.

CREATE TABLE IF NOT EXISTS public.mcp_oauth_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash TEXT NOT NULL UNIQUE,
  token_type TEXT NOT NULL CHECK (token_type IN ('access', 'refresh')),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES public.organizaciones(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL REFERENCES public.mcp_registered_clients(client_id) ON DELETE CASCADE,
  scopes TEXT[] NOT NULL DEFAULT '{}',
  resource TEXT NOT NULL,
  family_id UUID NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  replaced_by_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS mcp_oauth_tokens_lookup_idx
  ON public.mcp_oauth_tokens(token_hash) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS mcp_oauth_tokens_family_idx
  ON public.mcp_oauth_tokens(family_id);
CREATE INDEX IF NOT EXISTS mcp_oauth_tokens_user_client_idx
  ON public.mcp_oauth_tokens(user_id, client_id, created_at DESC);

ALTER TABLE public.mcp_oauth_tokens ENABLE ROW LEVEL SECURITY;
-- Solo service_role. Los tokens nunca son legibles desde anon/authenticated.

ALTER TABLE public.mcp_auth_codes
  ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION public.mcp_consume_auth_code(p_key TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE v_data JSONB;
BEGIN
  UPDATE public.mcp_auth_codes
  SET consumed_at = now()
  WHERE key = p_key AND consumed_at IS NULL AND expires_at > now()
  RETURNING data INTO v_data;
  IF v_data IS NOT NULL THEN
    DELETE FROM public.mcp_auth_codes WHERE key = p_key;
  END IF;
  RETURN v_data;
END;
$$;

REVOKE ALL ON FUNCTION public.mcp_consume_auth_code(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.mcp_consume_auth_code(TEXT) TO service_role;

CREATE OR REPLACE FUNCTION public.mcp_rotate_refresh_token(
  p_old_hash TEXT,
  p_new_refresh_hash TEXT,
  p_new_access_hash TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE v_old public.mcp_oauth_tokens%ROWTYPE;
BEGIN
  SELECT * INTO v_old FROM public.mcp_oauth_tokens
  WHERE token_hash = p_old_hash AND token_type = 'refresh'
    AND revoked_at IS NULL AND expires_at > now()
  FOR UPDATE;
  IF v_old.id IS NULL THEN RETURN NULL; END IF;

  UPDATE public.mcp_oauth_tokens
  SET revoked_at = now(), replaced_by_hash = p_new_refresh_hash
  WHERE id = v_old.id;

  INSERT INTO public.mcp_oauth_tokens(
    token_hash, token_type, user_id, organization_id, client_id, scopes,
    resource, family_id, expires_at
  ) VALUES
  (p_new_access_hash, 'access', v_old.user_id, v_old.organization_id,
   v_old.client_id, v_old.scopes, v_old.resource, v_old.family_id, p_access_expires_at),
  (p_new_refresh_hash, 'refresh', v_old.user_id, v_old.organization_id,
   v_old.client_id, v_old.scopes, v_old.resource, v_old.family_id, p_refresh_expires_at);

  RETURN jsonb_build_object(
    'user_id', v_old.user_id, 'organization_id', v_old.organization_id,
    'client_id', v_old.client_id, 'scopes', to_jsonb(v_old.scopes),
    'resource', v_old.resource, 'family_id', v_old.family_id
  );
END;
$$;

REVOKE ALL ON FUNCTION public.mcp_rotate_refresh_token(TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.mcp_rotate_refresh_token(TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ) TO service_role;

CREATE OR REPLACE FUNCTION public.mcp_revoke_token_family(p_token_hash TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE v_family UUID;
BEGIN
  SELECT family_id INTO v_family FROM public.mcp_oauth_tokens WHERE token_hash = p_token_hash;
  IF v_family IS NULL THEN RETURN false; END IF;
  UPDATE public.mcp_oauth_tokens SET revoked_at = coalesce(revoked_at, now())
  WHERE family_id = v_family;
  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.mcp_revoke_token_family(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.mcp_revoke_token_family(TEXT) TO service_role;
