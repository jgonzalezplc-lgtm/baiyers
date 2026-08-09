-- 034: Perfil organizacional canónico + sesión de onboarding conversacional
-- persistida (Fases 1-2 del rediseño de onboarding).
--
-- `organizaciones` (030) era bare-bones (id, nombre, owner_user_id). Este
-- perfil (rut, logo, industria, país, sitio web) hoy vive solo en
-- user_metadata, que es por-usuario, no por-organización, y no tiene
-- procedencia/confianza. Se agregan columnas nuevas, todas nullable, sin
-- tocar filas existentes.
--
-- `onboarding_sessions` reemplaza el estado que hoy vive únicamente en React
-- (OnboardingChat.tsx) por una sesión persistida y reanudable, con un
-- `draft` por campo (valor/confianza/origen/confirmado) — mismo patrón de
-- confianza/origen que ya usa /api/onboarding/investigar-empresa.
--
-- IDEMPOTENTE — se puede correr varias veces sin efectos duplicados.

-- ─── Perfil organizacional ──────────────────────────────────────────────────

ALTER TABLE public.organizaciones
    ADD COLUMN IF NOT EXISTS rut               TEXT,
    ADD COLUMN IF NOT EXISTS rut_confianza      TEXT
        CHECK (rut_confianza IN ('alta', 'media', 'baja', 'manual')),
    ADD COLUMN IF NOT EXISTS logo_url           TEXT,
    ADD COLUMN IF NOT EXISTS logo_storage_path  TEXT,
    ADD COLUMN IF NOT EXISTS logo_origen        TEXT
        CHECK (logo_origen IN ('investigado', 'subido', 'manual')),
    ADD COLUMN IF NOT EXISTS sitio_web          TEXT,
    ADD COLUMN IF NOT EXISTS industria          TEXT,
    ADD COLUMN IF NOT EXISTS pais               TEXT DEFAULT 'CL';

-- RUT único cuando está presente. Un RUT duplicado NO fusiona
-- organizaciones automáticamente: el backend debe capturar la violación
-- (23505) y devolver un estado de revisión manual, nunca un 500 ni un merge
-- silencioso.
CREATE UNIQUE INDEX IF NOT EXISTS ux_organizaciones_rut
    ON public.organizaciones (rut)
    WHERE rut IS NOT NULL;

-- ─── Sesión de onboarding conversacional ───────────────────────────────────

CREATE TABLE IF NOT EXISTS public.onboarding_sessions (
    id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id               UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    organizacion_id       UUID REFERENCES public.organizaciones(id) ON DELETE SET NULL,
    estado                TEXT NOT NULL DEFAULT 'en_progreso'
        CHECK (estado IN ('en_progreso', 'esperando_confirmacion', 'completado', 'abandonado')),
    version               INTEGER NOT NULL DEFAULT 1,
    -- draft: { "<campo>": { "valor": ..., "confianza": "alta|media|baja",
    --   "origen": "usuario|investigado|inferido", "confirmado": bool,
    --   "evidencia": "..." } }
    draft                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- mensajes: [{ "rol": "usuario|asistente", "texto": "...", "ts": "..." }]
    mensajes              JSONB NOT NULL DEFAULT '[]'::jsonb,
    preguntas_pendientes  JSONB NOT NULL DEFAULT '[]'::jsonb,
    propuesta_workflow    JSONB,
    paso_actual           TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS onboarding_sessions_user_idx
    ON public.onboarding_sessions(user_id, created_at DESC);

ALTER TABLE public.onboarding_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS onboarding_sessions_own ON public.onboarding_sessions;
CREATE POLICY onboarding_sessions_own ON public.onboarding_sessions
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ─── Storage (paso manual en el dashboard de Supabase, no DDL) ─────────────
-- Crear bucket "company-logos" (público de lectura, escritura autenticada),
-- mismo patrón que "ordenes-compra"/"boletas". Path por organización:
-- "<organizacion_id>/<archivo>".

-- ─── Rollback lógico ────────────────────────────────────────────────────────
-- DROP TABLE IF EXISTS public.onboarding_sessions;
-- DROP INDEX IF EXISTS public.ux_organizaciones_rut;
-- ALTER TABLE public.organizaciones
--     DROP COLUMN IF EXISTS rut,
--     DROP COLUMN IF EXISTS rut_confianza,
--     DROP COLUMN IF EXISTS logo_url,
--     DROP COLUMN IF EXISTS logo_storage_path,
--     DROP COLUMN IF EXISTS logo_origen,
--     DROP COLUMN IF EXISTS sitio_web,
--     DROP COLUMN IF EXISTS industria,
--     DROP COLUMN IF EXISTS pais;
