-- Etapa 11: API Publica para ERPs

-- API Keys (hash-only, nunca plaintext)
CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    nombre TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,           -- "claria_live_" o "claria_test_"
    activa BOOLEAN DEFAULT TRUE,
    plan TEXT DEFAULT 'pro',
    ultimo_uso_at TIMESTAMPTZ,
    expira_en TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON public.api_keys(key_hash);
CREATE INDEX IF NOT EXISTS api_keys_user_idx ON public.api_keys(user_id);

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "api_keys_own" ON public.api_keys FOR ALL USING (auth.uid() = user_id);

-- API Usage Log
CREATE TABLE IF NOT EXISTS public.api_usage_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    api_key_id UUID REFERENCES public.api_keys(id) ON DELETE SET NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    endpoint TEXT,
    metodo TEXT,
    status_code INTEGER,
    tiempo_respuesta_ms INTEGER,
    ip_origen TEXT,
    cotizacion_id UUID,
    oc_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS api_usage_user_idx ON public.api_usage_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS api_usage_key_idx ON public.api_usage_log(api_key_id, created_at DESC);

ALTER TABLE public.api_usage_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "api_usage_own" ON public.api_usage_log FOR ALL USING (auth.uid() = user_id);
-- Service role puede insertar
CREATE POLICY "api_usage_service_insert" ON public.api_usage_log FOR INSERT WITH CHECK (true);

-- Webhooks
CREATE TABLE IF NOT EXISTS public.webhooks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    url TEXT NOT NULL,
    eventos TEXT[] NOT NULL DEFAULT '{}',
    secret_hash TEXT,                   -- hash del secret, nunca plaintext
    activo BOOLEAN DEFAULT TRUE,
    ultimo_envio_at TIMESTAMPTZ,
    ultimo_status INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS webhooks_user_idx ON public.webhooks(user_id, activo);

ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "webhooks_own" ON public.webhooks FOR ALL USING (auth.uid() = user_id);

-- Webhook Logs
CREATE TABLE IF NOT EXISTS public.webhook_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    webhook_id UUID REFERENCES public.webhooks(id) ON DELETE CASCADE,
    evento TEXT,
    payload JSONB,
    status_code INTEGER,
    intentos INTEGER DEFAULT 1,
    exitoso BOOLEAN DEFAULT FALSE,
    enviado_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS webhook_logs_webhook_idx ON public.webhook_logs(webhook_id, enviado_at DESC);

ALTER TABLE public.webhook_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "webhook_logs_own" ON public.webhook_logs FOR SELECT USING (
    auth.uid() = (SELECT user_id FROM public.webhooks WHERE id = webhook_id)
);
CREATE POLICY "webhook_logs_service_insert" ON public.webhook_logs FOR INSERT WITH CHECK (true);

-- Campo referencia_erp en ordenes_compra (para correlacion con ERP externo)
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS referencia_erp TEXT;
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS confirmada_at TIMESTAMPTZ;
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS pdf_url TEXT;
CREATE INDEX IF NOT EXISTS oc_referencia_erp_idx ON public.ordenes_compra(user_id, referencia_erp);
