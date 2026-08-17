-- 043: Workflow unificado Fase E — expedientes mínimos de homologación.
-- Aplicación manual en Supabase. No implementa scoring de riesgo ni almacena
-- binarios; sólo orquesta solicitud, recepción y decisión humana auditable.

ALTER TABLE public.gmail_conversations
    DROP CONSTRAINT IF EXISTS gmail_conversations_tipo_check;
ALTER TABLE public.gmail_conversations
    ADD CONSTRAINT gmail_conversations_tipo_check
    CHECK (tipo IN ('cotizacion', 'compra', 'homologacion'));

CREATE TABLE IF NOT EXISTS public.supplier_homologation_cases (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizacion_id       UUID NOT NULL REFERENCES public.organizaciones(id) ON DELETE CASCADE,
    user_id               UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    proveedor_id          UUID NOT NULL REFERENCES public.proveedores(id) ON DELETE RESTRICT,
    lista_proyecto_id     UUID NOT NULL REFERENCES public.proyectos(id) ON DELETE CASCADE,
    workflow_instance_id  UUID NOT NULL REFERENCES public.workflow_instances(id) ON DELETE CASCADE,
    node_execution_id     UUID NOT NULL REFERENCES public.workflow_node_executions(id) ON DELETE CASCADE,
    responsable_id        UUID REFERENCES public.responsables(id) ON DELETE SET NULL,
    conversation_id       UUID REFERENCES public.gmail_conversations(id) ON DELETE SET NULL,
    estado                TEXT NOT NULL DEFAULT 'no_iniciado' CHECK (estado IN (
                              'no_iniciado', 'solicitado', 'recepcion_parcial',
                              'en_revision', 'requiere_aclaracion',
                              'homologado', 'rechazado'
                          )),
    requisitos            JSONB NOT NULL DEFAULT '[]'::jsonb,
    antecedentes_recibidos JSONB NOT NULL DEFAULT '[]'::jsonb,
    comentario_decision   TEXT,
    decidido_por_user_id  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    solicitado_at         TIMESTAMPTZ,
    recibido_at           TIMESTAMPTZ,
    decidido_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (node_execution_id, proveedor_id)
);

CREATE INDEX IF NOT EXISTS idx_supplier_homologation_cases_instance
    ON public.supplier_homologation_cases(workflow_instance_id, estado);
CREATE INDEX IF NOT EXISTS idx_supplier_homologation_cases_responsable
    ON public.supplier_homologation_cases(responsable_id, estado);
CREATE INDEX IF NOT EXISTS idx_supplier_homologation_cases_conversation
    ON public.supplier_homologation_cases(conversation_id);

ALTER TABLE public.supplier_homologation_cases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS supplier_homologation_cases_org ON public.supplier_homologation_cases;
CREATE POLICY supplier_homologation_cases_org ON public.supplier_homologation_cases
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
             WHERE m.organizacion_id = supplier_homologation_cases.organizacion_id
               AND m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS supplier_homologation_cases_admin_write ON public.supplier_homologation_cases;
CREATE POLICY supplier_homologation_cases_admin_write ON public.supplier_homologation_cases
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
             WHERE m.organizacion_id = supplier_homologation_cases.organizacion_id
               AND m.user_id = auth.uid()
               AND m.rol = 'admin'
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
             WHERE m.organizacion_id = supplier_homologation_cases.organizacion_id
               AND m.user_id = auth.uid()
               AND m.rol = 'admin'
        )
    );
