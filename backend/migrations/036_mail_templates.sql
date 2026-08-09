-- 036: Infraestructura de plantillas de correo versionadas (Fase 4 del
-- proyecto de mailing organizacional).
--
-- Hoy cada correo transaccional (RFQ, aprobación, OC, seguimientos) tiene
-- asunto/cuerpo hardcodeado con f-strings repartidos en varios archivos —
-- cambiar el texto de un correo requiere tocar código y redeployar, y no
-- hay override por organización. Estas tablas guardan SOLO los overrides:
-- el contenido default de cada evento vive en Python
-- (`app/services/mail_events.py`), así que una organización sin fila acá
-- sigue recibiendo el correo de siempre — ningún big-bang.
--
-- IDEMPOTENTE — se puede correr varias veces sin efectos duplicados.

-- ─── Definiciones (una por evento/canal/locale/organización, opcionalmente
-- acotada a un workflow o nodo específico) ─────────────────────────────────

CREATE TABLE IF NOT EXISTS public.mail_template_definitions (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    organizacion_id   UUID REFERENCES public.organizaciones(id) ON DELETE CASCADE NOT NULL,
    -- Acota el override a un workflow o nodo puntual. NULL en ambos = aplica
    -- a toda la organización para ese evento.
    workflow_id       UUID REFERENCES public.workflow_definitions(id) ON DELETE CASCADE,
    nodo_id           TEXT,
    evento            TEXT NOT NULL,
    audiencia         TEXT NOT NULL CHECK (audiencia IN ('internal', 'external')),
    canal             TEXT NOT NULL DEFAULT 'email',
    locale            TEXT NOT NULL DEFAULT 'es-CL',
    estado            TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'archivada')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organizacion_id, evento, canal, locale, workflow_id, nodo_id)
);

CREATE INDEX IF NOT EXISTS idx_mail_template_definitions_org
    ON public.mail_template_definitions(organizacion_id, evento);

-- ─── Versiones (nunca se borran — restaurar el default crea una versión
-- nueva, no elimina historial) ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.mail_template_versions (
    id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    definition_id         UUID REFERENCES public.mail_template_definitions(id) ON DELETE CASCADE NOT NULL,
    version               INTEGER NOT NULL,
    subject               TEXT NOT NULL,
    body_text             TEXT NOT NULL,
    variables_declaradas  TEXT[] NOT NULL DEFAULT '{}',
    origen                TEXT NOT NULL CHECK (origen IN ('default', 'ai_draft', 'user_edit')),
    autor_user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (definition_id, version)
);

CREATE INDEX IF NOT EXISTS idx_mail_template_versions_definition
    ON public.mail_template_versions(definition_id, version DESC);

ALTER TABLE public.mail_template_definitions
    ADD COLUMN IF NOT EXISTS version_activa_id UUID REFERENCES public.mail_template_versions(id) ON DELETE SET NULL;

-- ─── Auditoría de envíos (idempotente — un reintento con la misma clave
-- nunca duplica un correo) ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.mail_delivery_events (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    organizacion_id     UUID REFERENCES public.organizaciones(id) ON DELETE CASCADE NOT NULL,
    evento              TEXT NOT NULL,
    definition_id       UUID REFERENCES public.mail_template_definitions(id) ON DELETE SET NULL,
    version_id          UUID REFERENCES public.mail_template_versions(id) ON DELETE SET NULL,
    destinatario_email  TEXT NOT NULL,
    workflow_id         UUID REFERENCES public.workflow_definitions(id) ON DELETE SET NULL,
    workflow_nodo_id    TEXT,
    proveedor_id        UUID REFERENCES public.proveedores(id) ON DELETE SET NULL,
    responsable_id      UUID REFERENCES public.responsables(id) ON DELETE SET NULL,
    gmail_message_id    TEXT,
    gmail_thread_id     TEXT,
    estado              TEXT NOT NULL CHECK (estado IN ('pendiente', 'enviado', 'fallido')),
    error               TEXT,
    idempotency_key     TEXT NOT NULL UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mail_delivery_events_org
    ON public.mail_delivery_events(organizacion_id, evento, created_at DESC);

-- ─── RLS ────────────────────────────────────────────────────────────────────
-- Lectura para cualquier miembro de la organización. La escritura la
-- controla el backend (chequeo de ctx.es_admin), mismo criterio que ya usan
-- los endpoints de workflows — el service role bypassa RLS de todos modos.

ALTER TABLE public.mail_template_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mail_template_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mail_delivery_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mail_template_definitions_miembro ON public.mail_template_definitions;
CREATE POLICY mail_template_definitions_miembro ON public.mail_template_definitions
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
            WHERE m.organizacion_id = mail_template_definitions.organizacion_id
              AND m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS mail_template_versions_miembro ON public.mail_template_versions;
CREATE POLICY mail_template_versions_miembro ON public.mail_template_versions
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.mail_template_definitions d
            JOIN public.membresias_organizacion m ON m.organizacion_id = d.organizacion_id
            WHERE d.id = mail_template_versions.definition_id
              AND m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS mail_delivery_events_miembro ON public.mail_delivery_events;
CREATE POLICY mail_delivery_events_miembro ON public.mail_delivery_events
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
            WHERE m.organizacion_id = mail_delivery_events.organizacion_id
              AND m.user_id = auth.uid()
        )
    );

-- ─── Rollback lógico ────────────────────────────────────────────────────────
-- DROP TABLE IF EXISTS public.mail_delivery_events;
-- DROP TABLE IF EXISTS public.mail_template_versions;
-- DROP TABLE IF EXISTS public.mail_template_definitions;
