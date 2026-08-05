-- 032: Persistir el estado del flujo OAuth de MCP — bug real encontrado
-- probando la conexión de Claude Desktop en producción.
--
-- app/mcp/oauth.py guardaba `_auth_codes` y `_registered_clients` en
-- diccionarios EN MEMORIA del proceso Python. Railway corre el backend con
-- más de un worker/instancia — el GET /authorize que genera el estado
-- pendiente y el POST /consent que lo confirma pueden caer en procesos
-- distintos, sin memoria compartida. Resultado real: "Estado de
-- autorización inválido o expirado" al querer autorizar Claude.
--
-- Reemplaza los dos dicts por dos tablas simples. `mcp_auth_codes` es
-- genérica (clave de texto libre) para no tener que rediseñar las dos fases
-- del flujo (pendiente antes del consentimiento, código emitido después) —
-- mismo patrón que el dict original, solo que compartido entre procesos.
--
-- IDEMPOTENTE — se puede correr varias veces.

CREATE TABLE IF NOT EXISTS public.mcp_auth_codes (
    key         TEXT PRIMARY KEY,          -- "pending_<state>" o el código emitido
    data        JSONB NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcp_auth_codes_expires ON public.mcp_auth_codes(expires_at);

CREATE TABLE IF NOT EXISTS public.mcp_registered_clients (
    client_id                   TEXT PRIMARY KEY,
    client_name                 TEXT,
    redirect_uris                JSONB NOT NULL DEFAULT '[]'::jsonb,
    grant_types                  JSONB NOT NULL DEFAULT '["authorization_code","refresh_token"]'::jsonb,
    response_types               JSONB NOT NULL DEFAULT '["code"]'::jsonb,
    token_endpoint_auth_method   TEXT NOT NULL DEFAULT 'none',
    created_at                   TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: estas tablas solo las toca el backend con service key (bypassea RLS
-- igual). Se habilita por higiene, sin policies — nadie con anon key debe
-- poder leerlas directo, contienen tokens/estado de sesión OAuth.
ALTER TABLE public.mcp_auth_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mcp_registered_clients ENABLE ROW LEVEL SECURITY;
