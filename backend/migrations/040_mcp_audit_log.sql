-- 040: auditoría MCP mínima, organizacional y sin payloads sensibles.
-- IDEMPOTENTE. Ejecutar manualmente en Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS public.mcp_tool_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES public.organizaciones(id) ON DELETE CASCADE,
  actor_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  client_id TEXT,
  request_id TEXT,
  tool_name TEXT NOT NULL,
  scopes TEXT[] NOT NULL DEFAULT '{}',
  entity_type TEXT,
  entity_id TEXT,
  idempotency_key_hash TEXT,
  outcome TEXT NOT NULL,
  http_status INTEGER,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  confirmation_level TEXT NOT NULL DEFAULT 'none',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mcp_tool_audit_org_created_idx
  ON public.mcp_tool_audit_log(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS mcp_tool_audit_tool_created_idx
  ON public.mcp_tool_audit_log(tool_name, created_at DESC);

ALTER TABLE public.mcp_tool_audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_tool_audit_org_read ON public.mcp_tool_audit_log;
CREATE POLICY mcp_tool_audit_org_read ON public.mcp_tool_audit_log FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM public.membresias_organizacion m
    WHERE m.organizacion_id = mcp_tool_audit_log.organization_id
      AND m.user_id = auth.uid()
  )
);

REVOKE ALL ON public.mcp_tool_audit_log FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.mcp_tool_audit_log TO service_role;
