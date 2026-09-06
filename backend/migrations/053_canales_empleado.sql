-- 053 — Canales del empleado digital (F1)
--
-- Credenciales separadas de `user_integrations`: esa tabla representa una
-- cuenta personal de una persona; este canal representa la identidad continua
-- de la organización. En el caso transitorio de Juan, `cuenta_autorizada` es
-- Juan y `direccion_operativa` es compras@empresa.cl.

CREATE TABLE IF NOT EXISTS public.canales_empleado (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizacion_id       UUID NOT NULL REFERENCES public.organizaciones(id) ON DELETE CASCADE,
    canal                 TEXT NOT NULL CHECK (canal IN ('correo')),
    estado                TEXT NOT NULL DEFAULT 'borrador'
                          CHECK (estado IN ('borrador', 'activo', 'pausado', 'error')),
    direccion_operativa   TEXT NOT NULL,
    cuenta_autorizada     TEXT,
    etiqueta_gmail        TEXT NOT NULL,
    access_token          TEXT,
    refresh_token         TEXT,
    conectado_por         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    ultimo_error          TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (organizacion_id, canal),
    UNIQUE (canal, direccion_operativa)
);

CREATE INDEX IF NOT EXISTS canales_empleado_activos_idx
    ON public.canales_empleado(canal, estado)
    WHERE estado = 'activo';

ALTER TABLE public.canales_empleado ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS canales_empleado_por_organizacion ON public.canales_empleado;
CREATE POLICY canales_empleado_por_organizacion ON public.canales_empleado
    USING (EXISTS (
        SELECT 1 FROM public.membresias_organizacion m
        WHERE m.organizacion_id = canales_empleado.organizacion_id
          AND m.user_id = auth.uid()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.membresias_organizacion m
        WHERE m.organizacion_id = canales_empleado.organizacion_id
          AND m.user_id = auth.uid()
    ));

REVOKE ALL ON public.canales_empleado FROM PUBLIC, anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.canales_empleado TO authenticated, service_role;

COMMENT ON TABLE public.canales_empleado IS
    'Canales corporativos del empleado digital. Nunca reutiliza inboxes personales sin filtro.';
COMMENT ON COLUMN public.canales_empleado.etiqueta_gmail IS
    'Etiqueta Gmail exclusiva que limita qué mensajes puede procesar el empleado.';

-- Verificación:
-- SELECT direccion_operativa, cuenta_autorizada, etiqueta_gmail, estado
-- FROM public.canales_empleado;
