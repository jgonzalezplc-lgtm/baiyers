-- Etapa 10: MCP Server tables

-- Active MCP connections (OAuth tokens)
CREATE TABLE IF NOT EXISTS mcp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL,
    scopes TEXT[] NOT NULL DEFAULT '{}',
    token_hash TEXT,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    UNIQUE (user_id, client_id)
);

ALTER TABLE mcp_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own MCP connections"
    ON mcp_connections FOR ALL
    USING (auth.uid() = user_id);

-- Audit log for all MCP tool calls
CREATE TABLE IF NOT EXISTS mcp_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    params JSONB,
    result_preview TEXT,
    called_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE mcp_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users view own MCP audit log"
    ON mcp_audit_log FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can insert audit logs
CREATE POLICY "Service role inserts audit logs"
    ON mcp_audit_log FOR INSERT
    WITH CHECK (true);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS mcp_audit_log_user_id_idx ON mcp_audit_log(user_id, called_at DESC);
CREATE INDEX IF NOT EXISTS mcp_connections_user_id_idx ON mcp_connections(user_id);
